# Быстрый старт

Todo List приложение с балансировкой нагрузки.

## Запуск проекта

```bash
# Запустить все сервисы
docker compose up -d

# Проверить статус
docker compose ps

# Просмотреть логи
docker compose logs -f
```

## Доступ к системе

- **Frontend (через балансировщик)**: http://localhost
- **API (через балансировщик)**: http://localhost/api/info
- **Backend1 (напрямую)**: http://localhost:5000/api/info
- **Backend2 (напрямую)**: http://localhost:5001/api/info


## Проверка ограничений ресурсов

```bash
# Проверить ограничения для backend1
docker inspect load_balancer_backend1 | grep -A 10 "Resources"
```

