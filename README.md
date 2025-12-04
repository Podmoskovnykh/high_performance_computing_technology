# Быстрый старт

Todo List приложение с балансировкой нагрузки.

## Запуск проекта

```bash
# Запустить все сервисы
docker compose up -d
```

## Доступ к системе

- **Frontend (через балансировщик)**: http://localhost
- **API (через балансировщик)**: http://localhost/api/info
- **Backend1 (напрямую)**: http://localhost:5000/api/info
- **Backend2 (напрямую)**: http://localhost:5001/api/info


## Проверка ограничений ресурсов

```bash
# Проверить ограничения для контейнера (удобный формат)
./show_resources.sh load_balancer_backend1

# Или для всех контейнеров
./show_resources.sh

# Альтернативный способ через jq
docker inspect load_balancer_backend1 | jq '.[0].HostConfig | {Memory, CpuShares, CpuQuota, CpuPeriod, CpusetCpus, CpusetMems, MemoryReservation, MemorySwap, NanoCpus}'
```

