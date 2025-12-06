#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Нагрузочное тестирование БЕЗ балансировщика"
echo "=========================================="
echo ""
echo "Целевой сервер: http://localhost:5000"
echo ""

if ! curl -s http://localhost:5000/health > /dev/null; then
    echo "ОШИБКА: Backend1 не доступен на http://localhost:5000"
    echo "Убедитесь, что сервис запущен: docker compose up -d backend1"
    exit 1
fi

USERS=${1:-10}
SPAWN_RATE=${2:-2}
DURATION=${3:-60}
HOST="http://localhost:5000"

echo "Параметры теста:"
echo "  - Пользователей: $USERS"
echo "  - Скорость добавления: $SPAWN_RATE пользователей/сек"
echo "  - Длительность: $DURATION секунд"
echo "  - Хост: $HOST"
echo ""

RESULTS_DIR="results/without_balancer"
mkdir -p "$RESULTS_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_FILE="$RESULTS_DIR/test_${TIMESTAMP}"

echo "Запуск теста..."
echo "Результаты будут сохранены в: $RESULTS_FILE"
echo ""

python3 -m locust \
    --headless \
    --host="$HOST" \
    --users="$USERS" \
    --spawn-rate="$SPAWN_RATE" \
    --run-time="${DURATION}s" \
    --html="$RESULTS_FILE.html" \
    --csv="$RESULTS_FILE" \
    --loglevel=INFO

echo ""
echo "=========================================="
echo "Тест завершен!"
echo "=========================================="
echo "HTML отчет: $RESULTS_FILE.html"
echo "CSV данные: $RESULTS_FILE_*.csv"
echo ""
