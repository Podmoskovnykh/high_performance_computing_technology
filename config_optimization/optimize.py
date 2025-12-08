#!/usr/bin/env python3

import argparse
import json
import subprocess
import time
import csv
import re
import base64
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import pandas as pd
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ============================================================================
# УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ NGINX
# ============================================================================

def apply_nginx_config(config: Dict[str, Any], nginx_config_path: Path) -> bool:
    try:
        with open(nginx_config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if 'worker_connections' in config:
            content = re.sub(
                r'worker_connections\s+\d+;',
                f"worker_connections {config['worker_connections']};",
                content
            )
        
        if 'keepalive_timeout' in config:
            content = re.sub(
                r'keepalive_timeout\s+\d+;',
                f"keepalive_timeout {config['keepalive_timeout']};",
                content
            )
        
        if 'upstream_keepalive' in config:
            def _replace_keepalive(match: re.Match) -> str:
                prefix = match.group(1)
                suffix = match.group(2)
                return f"{prefix}{config['upstream_keepalive']}{suffix}"

            content = re.sub(
                r'(upstream backend \{[^}]*keepalive\s+)\d+(\s*;)',
                _replace_keepalive,
                content,
                flags=re.DOTALL
            )
        
        with open(nginx_config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        print(f"Ошибка при применении конфигурации: {e}")
        return False


def get_default_config() -> Dict[str, Any]:
    return {
        'nginx': {
            'worker_connections': 1024,
            'keepalive_timeout': 65,
            'upstream_keepalive': 32
        }
    }


# ============================================================================
# СБРОС СИСТЕМЫ
# ============================================================================

def reset_system(base_dir: Path, full_reset: bool = False) -> bool:
    print("Сброс состояния системы...")
    
    try:
        subprocess.run(['docker', 'compose', 'down'], cwd=base_dir, check=True, capture_output=True)
        time.sleep(2)
    except subprocess.CalledProcessError:
        return False
    
    if full_reset:
        try:
            subprocess.run(['docker', 'compose', 'down', '-v'], cwd=base_dir, check=True, capture_output=True)
            time.sleep(2)
        except subprocess.CalledProcessError:
            return False
    
    try:
        subprocess.run(['docker', 'compose', 'up', '-d'], cwd=base_dir, check=True, capture_output=True)
        print("Ожидание запуска сервисов...")
        time.sleep(15)
        
        db_config = {
            'host': 'localhost', 'database': 'testdb',
            'user': 'testuser', 'password': 'testpass', 'port': 5432
        }

        if HAS_PSYCOPG2:
            for _ in range(30):
                try:
                    conn = psycopg2.connect(**db_config)
                    conn.close()
                    print("База данных готова")
                    break
                except Exception:
                    time.sleep(2)

        truncated = False
        if HAS_PSYCOPG2:
            try:
                conn = psycopg2.connect(**db_config)
                cur = conn.cursor()
                cur.execute("TRUNCATE TABLE todos RESTART IDENTITY CASCADE;")
                conn.commit()
                cur.close()
                conn.close()
                truncated = True
            except Exception as e:
                print(f"Предупреждение: не удалось очистить БД через psycopg2: {e}")
        if not truncated:
            try:
                subprocess.run(
                    [
                        'docker', 'exec', '-i', 'load_balancer_db',
                        'psql', '-U', 'testuser', '-d', 'testdb',
                        '-c', 'TRUNCATE TABLE todos RESTART IDENTITY CASCADE;'
                    ],
                    check=True,
                    capture_output=True,
                )
                truncated = True
            except subprocess.CalledProcessError as e:
                print(f"Предупреждение: не удалось очистить БД через docker exec: {e.stderr.decode('utf-8', 'ignore')}")
        if not truncated:
            print("ВНИМАНИЕ: БД не очищена, данные могли сохраниться.")
        
        time.sleep(5)
        return True
    except subprocess.CalledProcessError:
        return False


def restart_nginx(base_dir: Path) -> bool:
    try:
        subprocess.run(['docker', 'compose', 'restart', 'nginx'], cwd=base_dir, check=True, capture_output=True)
        time.sleep(3)
        return True
    except subprocess.CalledProcessError:
        return False


# ============================================================================
# ЗАПУСК НАГРУЗОЧНЫХ ТЕСТОВ
# ============================================================================

def run_load_test(users: int, spawn_rate: int, duration: int, base_dir: Path) -> Dict[str, Any]:
    load_testing_dir = base_dir / "load_testing"
    test_script = load_testing_dir / "run_test_with_balancer.sh"
    
    print(f"Запуск теста: {users} пользователей, {duration} сек")
    
    try:
        subprocess.run(
            [str(test_script), str(users), str(spawn_rate), str(duration)],
            cwd=str(load_testing_dir),
            capture_output=True,
            timeout=duration + 120
        )
        
        results_dir = load_testing_dir / "results" / "with_balancer"
        if not results_dir.exists():
            return {'rps': 0.0, 'error': 'Директория результатов не найдена'}
        
        stats_files = sorted(
            results_dir.glob("test_*_stats.csv"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if not stats_files:
            return {'rps': 0.0, 'error': 'CSV файл результатов не найден'}
        
        return parse_locust_results(stats_files[0])
        
    except subprocess.TimeoutExpired:
        return {'rps': 0.0, 'error': 'Тест превысил максимальное время'}
    except Exception as e:
        return {'rps': 0.0, 'error': f'Ошибка: {e}'}


def parse_locust_results(stats_file: Path) -> Dict[str, Any]:
    metrics = {
        'rps': 0.0,
        'avg_response_time': 0.0,
        'total_requests': 0,
        'success_rate': 0.0
    }
    
    try:
        with open(stats_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Type') == 'Aggregated' or row.get('Name') == 'Aggregated':
                    metrics['rps'] = float(row.get('Requests/s', 0))
                    metrics['avg_response_time'] = float(row.get('Average Response Time', 0))
                    
                    total_requests = int(row.get('Request Count', 0))
                    total_failures = int(row.get('Failure Count', 0))
                    
                    if total_requests > 0:
                        metrics['total_requests'] = total_requests
                        metrics['success_rate'] = ((total_requests - total_failures) / total_requests) * 100
                    break
    except Exception as e:
        print(f"Предупреждение: не удалось распарсить результаты: {e}")
    
    return metrics


# ============================================================================
# АЛГОРИТМЫ ОПТИМИЗАЦИИ
# ============================================================================

def generate_grid_configs(grid_size: int = 3) -> List[Dict[str, Any]]:
    configs = []
    
    wc_values = [512, 1024, 1536, 2048][:grid_size] if grid_size <= 4 else \
                [512 + i * (2048 - 512) / (grid_size - 1) for i in range(grid_size)]
    kt_values = [30, 60, 90, 120][:grid_size] if grid_size <= 4 else \
                [30 + i * (120 - 30) / (grid_size - 1) for i in range(grid_size)]
    uk_values = [16, 32, 48, 64][:grid_size] if grid_size <= 4 else \
                [16 + i * (64 - 16) / (grid_size - 1) for i in range(grid_size)]
    
    for wc in wc_values:
        for kt in kt_values:
            for uk in uk_values:
                configs.append({
                    'nginx': {
                        'worker_connections': int(wc),
                        'keepalive_timeout': int(kt),
                        'upstream_keepalive': int(uk)
                    }
                })
    
    return configs


# ============================================================================
# ГЕНЕРАЦИЯ ОТЧЕТА
# ============================================================================

def generate_report(history: List[Dict[str, Any]], base_dir: Path, output_file: str = None) -> str:
    reports_dir = base_dir / "config_optimization" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = reports_dir / f"optimization_report_{timestamp}.html"
    else:
        output_file = Path(output_file)
    
    best_iter = max(history, key=lambda x: x['metrics'].get('rps', 0))
    best_config = best_iter['config']
    best_metrics = best_iter['metrics']
    best_rps = best_metrics.get('rps', 0)
    
    initial_metrics = history[0]['metrics'] if history else {}
    initial_rps = initial_metrics.get('rps', 0)
    
    improvement = 0
    if initial_rps > 0:
        improvement = ((best_rps - initial_rps) / initial_rps) * 100

    image_files: List[Tuple[str, str]] = []
    if HAS_PLOTTING and len(history) >= 1:
        try:
            df = pd.DataFrame([
                {
                    "iteration": item.get("iteration", 0),
                    "worker_connections": item.get("config", {}).get("nginx", {}).get("worker_connections"),
                    "keepalive_timeout": item.get("config", {}).get("nginx", {}).get("keepalive_timeout"),
                    "upstream_keepalive": item.get("config", {}).get("nginx", {}).get("upstream_keepalive"),
                    "rps": item.get("metrics", {}).get("rps", 0),
                    "avg_response_time": item.get("metrics", {}).get("avg_response_time", 0),
                    "success_rate": item.get("metrics", {}).get("success_rate", 0),
                }
                for item in history
            ])

            def save_fig(name: str, fig):
                img_path = reports_dir / f"{name}.png"
                fig.savefig(img_path, dpi=140, bbox_inches="tight")
                plt.close(fig)
                image_files.append((name, img_path.name))

            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(df["iteration"], df["rps"], marker="o")
            ax.set_xlabel("Итерация")
            ax.set_ylabel("RPS")
            ax.set_title("RPS по итерациям")
            ax.grid(alpha=0.3)
            save_fig("rps_over_iterations", fig)

            fig, axes = plt.subplots(1, 3, figsize=(12, 4))
            axes[0].scatter(df["worker_connections"], df["rps"], alpha=0.7)
            axes[0].set_xlabel("worker_connections")
            axes[0].set_ylabel("RPS")
            axes[0].grid(alpha=0.3)

            axes[1].scatter(df["keepalive_timeout"], df["rps"], alpha=0.7, color="orange")
            axes[1].set_xlabel("keepalive_timeout")
            axes[1].set_ylabel("RPS")
            axes[1].grid(alpha=0.3)

            axes[2].scatter(df["upstream_keepalive"], df["rps"], alpha=0.7, color="green")
            axes[2].set_xlabel("upstream_keepalive")
            axes[2].set_ylabel("RPS")
            axes[2].grid(alpha=0.3)
            fig.suptitle("RPS в зависимости от параметров")
            plt.tight_layout()
            save_fig("rps_vs_params", fig)
        except Exception as plot_err:
            print(f"Предупреждение: не удалось построить графики: {plot_err}")

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Отчет об оптимизации конфигурации</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 16px; background: #fafafa; color: #222; }}
        .container {{ max-width: 1100px; margin: 0 auto; background: #fff; padding: 20px; border: 1px solid #ddd; border-radius: 6px; }}
        h1 {{ font-size: 22px; margin-bottom: 8px; }}
        h2 {{ font-size: 18px; margin-top: 20px; }}
        .summary {{ padding: 10px 12px; border: 1px solid #ddd; border-radius: 4px; background: #f7f7f7; }}
        .metrics {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }}
        .metric {{ padding: 8px 10px; border: 1px solid #ddd; border-radius: 4px; background: #fff; min-width: 160px; }}
        .metric-title {{ font-size: 12px; color: #555; }}
        .metric-value {{ font-size: 18px; font-weight: 600; color: #111; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 13px; }}
        th {{ background: #f1f1f1; }}
        tr:nth-child(even) {{ background: #fbfbfb; }}
        .charts img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Отчет об автоматизированном поиске эффективной конфигурации</h1>
        
        <div class="summary">
            <h2>Сводка</h2>
            <div class="metrics">
                <div class="metric"><div class="metric-title">Начальный RPS</div><div class="metric-value">{initial_rps:.2f}</div></div>
                <div class="metric"><div class="metric-title">Лучший RPS</div><div class="metric-value">{best_rps:.2f}</div></div>
                <div class="metric"><div class="metric-title">Прирост</div><div class="metric-value">{improvement:+.2f}%</div></div>
                <div class="metric"><div class="metric-title">Итераций</div><div class="metric-value">{len(history)}</div></div>
            </div>
        </div>
        
        <h2>Лучшая конфигурация</h2>
        <table>
            <tr><th>Параметр</th><th>Значение</th></tr>
            <tr><td>worker_connections</td><td>{best_config.get('nginx', {}).get('worker_connections', 'N/A')}</td></tr>
            <tr><td>keepalive_timeout</td><td>{best_config.get('nginx', {}).get('keepalive_timeout', 'N/A')}</td></tr>
            <tr><td>upstream_keepalive</td><td>{best_config.get('nginx', {}).get('upstream_keepalive', 'N/A')}</td></tr>
        </table>
"""

    if image_files:
        html += "<h2>Графики</h2><div class=\"charts\">"
        for name, img_name in image_files:
            img_path = reports_dir / img_name
            img_data = ""
            try:
                with open(img_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
            if img_data:
                src = f"data:image/png;base64,{img_data}"
            else:
                src = img_name
            html += f'<div><div style="font-size:13px;margin:4px 0;">{name}</div><img src="{src}" alt="{name}"></div>'
        html += "</div>"

    html += """
        <h2>Результаты всех итераций</h2>
        <table>
            <tr>
                <th>Итерация</th>
                <th>worker_connections</th>
                <th>keepalive_timeout</th>
                <th>upstream_keepalive</th>
                <th>RPS</th>
                <th>Время отклика (мс)</th>
                <th>Успешность (%)</th>
            </tr>"""
    
    for item in history:
        config = item.get('config', {})
        metrics = item.get('metrics', {})
        nginx = config.get('nginx', {})
        
        html += f"""
            <tr>
                <td>{item.get('iteration', 0)}</td>
                <td>{nginx.get('worker_connections', 0)}</td>
                <td>{nginx.get('keepalive_timeout', 0)}</td>
                <td>{nginx.get('upstream_keepalive', 0)}</td>
                <td>{metrics.get('rps', 0):.2f}</td>
                <td>{metrics.get('avg_response_time', 0):.2f}</td>
                <td>{metrics.get('success_rate', 0):.2f}</td>
            </tr>"""
    
    html += """
        </table>
    </div>
</body>
</html>"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\nОтчет сохранен: {output_file}")
    return str(output_file)


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Автоматизированный поиск эффективных конфигураций')
    parser.add_argument('--iterations', type=int, default=9, help='Количество итераций')
    parser.add_argument('--grid-size', type=int, default=3, help='Размер сетки для grid search')
    parser.add_argument('--test-users', type=int, default=100, help='Количество пользователей в тесте')
    parser.add_argument('--test-spawn-rate', type=int, default=4, help='Скорость добавления пользователей')
    parser.add_argument('--test-duration', type=int, default=60, help='Длительность теста в секундах')
    parser.add_argument('--full-reset', action='store_true', help='Полный сброс (удаление volumes) перед началом')
    parser.add_argument('--output', type=str, default=None, help='Путь для сохранения отчета')
    
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent.parent
    nginx_config_path = base_dir / "nginx" / "nginx.conf"
    
    print("=" * 70)
    print("АВТОМАТИЗИРОВАННЫЙ ПОИСК ЭФФЕКТИВНЫХ КОНФИГУРАЦИЙ")
    print("=" * 70)
    print(f"Итераций: {args.iterations}")
    print(f"Параметры теста: {args.test_users} пользователей, {args.test_duration} сек")
    print()
    
    configs = generate_grid_configs(grid_size=args.grid_size)
    import random
    random.shuffle(configs)
    if len(configs) > args.iterations:
        configs = configs[:args.iterations]
    print(f"Сгенерировано {len(configs)} конфигураций для тестирования")
    
    history = []
    initial_config = get_default_config()
    
    try:
        print("\n" + "=" * 70)
        print("ШАГ 1: Сброс системы и применение начальной конфигурации")
        print("=" * 70)
        
        apply_nginx_config(initial_config.get('nginx', {}), nginx_config_path)
        if not reset_system(base_dir, full_reset=args.full_reset):
            print("ОШИБКА: Не удалось сбросить систему")
            return
        restart_nginx(base_dir)
        
        print("\n" + "=" * 70)
        print("ШАГ 2: Базовый нагрузочный тест (начальная конфигурация)")
        print("=" * 70)
        
        initial_metrics = run_load_test(args.test_users, args.test_spawn_rate, args.test_duration, base_dir)
        history.append({'iteration': 0, 'config': initial_config, 'metrics': initial_metrics})
        initial_rps = initial_metrics.get('rps', 0)
        print(f"\nБазовый RPS: {initial_rps:.2f}")
        
        print("\n" + "=" * 70)
        print("ШАГ 3: Автоматизированный поиск эффективных конфигураций")
        print("=" * 70)
        
        best_rps = initial_rps
        best_config = initial_config
        
        for iteration in range(1, args.iterations + 1):
            if iteration > len(configs):
                break
            
            print(f"\n--- Итерация {iteration}/{args.iterations} ---")
            config = configs[iteration - 1]
            nginx_config = config.get('nginx', {})
            
            print(f"Конфигурация: worker_connections={nginx_config.get('worker_connections')}, "
                  f"keepalive_timeout={nginx_config.get('keepalive_timeout')}, "
                  f"upstream_keepalive={nginx_config.get('upstream_keepalive')}")
            
            apply_nginx_config(nginx_config, nginx_config_path)
            
            if not reset_system(base_dir, full_reset=False):
                continue
            restart_nginx(base_dir)
            
            metrics = run_load_test(args.test_users, args.test_spawn_rate, args.test_duration, base_dir)
            rps = metrics.get('rps', 0)
            
            history.append({'iteration': iteration, 'config': config, 'metrics': metrics})
            print(f"Результат: RPS = {rps:.2f}")
            
            if rps > best_rps:
                best_rps = rps
                best_config = config
        
        print("\n" + "=" * 70)
        print("РЕЗУЛЬТАТЫ ОПТИМИЗАЦИИ")
        print("=" * 70)
        
        nginx_config = best_config.get('nginx', {})
        print(f"Лучшая конфигурация (RPS: {best_rps:.2f}):")
        print(f"  worker_connections: {nginx_config.get('worker_connections')}")
        print(f"  keepalive_timeout: {nginx_config.get('keepalive_timeout')}")
        print(f"  upstream_keepalive: {nginx_config.get('upstream_keepalive')}")
        
        improvement = 0
        if initial_rps > 0:
            improvement = ((best_rps - initial_rps) / initial_rps) * 100
        print(f"\nПрирост эффективности: {improvement:+.2f}%")
        
        print("\n" + "=" * 70)
        print("ШАГ 4: Генерация отчета")
        print("=" * 70)
        
        report_file = generate_report(history, base_dir, args.output)
        
        history_file = Path(__file__).parent / "optimization_history.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print(f"История сохранена: {history_file}")
        
        print("\n" + "=" * 70)
        print("ОПТИМИЗАЦИЯ ЗАВЕРШЕНА")
        print("=" * 70)
        print(f"Отчет: {report_file}")
        
    except KeyboardInterrupt:
        print("\n\nОптимизация прервана пользователем")
        if history:
            history_file = Path(__file__).parent / "optimization_history_partial.json"
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            print(f"Частичные результаты: {history_file}")
    except Exception as e:
        print(f"\nОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
