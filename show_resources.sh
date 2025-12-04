#!/bin/bash

# Скрипт для просмотра ресурсов Docker контейнеров в читаемом формате

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для конвертации байт в читаемый формат
bytes_to_human() {
    local bytes=$1
    if [ -z "$bytes" ] || [ "$bytes" = "null" ] || [ "$bytes" = "0" ]; then
        echo "не ограничено"
    else
        local mb=$((bytes / 1024 / 1024))
        local gb=$((mb / 1024))
        if [ $gb -gt 0 ]; then
            echo "${gb} GB (${mb} MB)"
        else
            echo "${mb} MB"
        fi
    fi
}

# Функция для конвертации наносекунд CPU в читаемый формат
nanocpus_to_human() {
    local nanocpus=$1
    if [ -z "$nanocpus" ] || [ "$nanocpus" = "null" ] || [ "$nanocpus" = "0" ]; then
        echo "не ограничено"
    else
        # Используем awk для вычислений с плавающей точкой
        local cpus=$(awk "BEGIN {printf \"%.2f\", $nanocpus / 1000000000}")
        echo "${cpus} CPU"
    fi
}

# Функция для отображения ресурсов контейнера
show_container_resources() {
    local container_name=$1
    
    if [ -z "$container_name" ]; then
        echo -e "${RED}Ошибка: не указано имя контейнера${NC}"
        echo "Использование: $0 <имя_контейнера>"
        exit 1
    fi
    
    # Проверяем существование контейнера
    if ! docker ps -a --format "{{.Names}}" | grep -q "^${container_name}$"; then
        echo -e "${RED}Ошибка: контейнер '${container_name}' не найден${NC}"
        exit 1
    fi
    
    # Получаем данные через jq
    local memory=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.Memory // "null"')
    local memory_reservation=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.MemoryReservation // "null"')
    local memory_swap=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.MemorySwap // "null"')
    local nanocpus=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.NanoCpus // "null"')
    local cpu_shares=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.CpuShares // "null"')
    local cpu_quota=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.CpuQuota // "null"')
    local cpu_period=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.CpuPeriod // "null"')
    local cpuset_cpus=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.CpusetCpus // "null"')
    local cpuset_mems=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].HostConfig.CpusetMems // "null"')
    
    # Получаем статус контейнера
    local status=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].State.Status')
    local running=$(docker inspect "$container_name" 2>/dev/null | jq -r '.[0].State.Running')
    
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}Ресурсы контейнера: ${YELLOW}${container_name}${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "Статус: ${running} (${status})"
    echo ""
    echo -e "${YELLOW}Память:${NC}"
    echo -e "  Лимит памяти:        $(bytes_to_human "$memory")"
    echo -e "  Резерв памяти:       $(bytes_to_human "$memory_reservation")"
    echo -e "  Swap:                $(bytes_to_human "$memory_swap")"
    echo ""
    echo -e "${YELLOW}CPU:${NC}"
    echo -e "  NanoCpus:            $(nanocpus_to_human "$nanocpus")"
    if [ "$cpu_shares" != "null" ] && [ "$cpu_shares" != "0" ]; then
        echo -e "  CPU Shares:          ${cpu_shares} (1024 = 1 CPU)"
    else
        echo -e "  CPU Shares:          не ограничено"
    fi
    if [ "$cpu_quota" != "null" ] && [ "$cpu_quota" != "0" ] && [ "$cpu_period" != "null" ] && [ "$cpu_period" != "0" ]; then
        local cpu_limit=$(awk "BEGIN {printf \"%.2f\", $cpu_quota / $cpu_period}")
        echo -e "  CPU Quota/Period:    ${cpu_limit} CPU (${cpu_quota}/${cpu_period})"
    else
        echo -e "  CPU Quota/Period:    не ограничено"
    fi
    if [ "$cpuset_cpus" != "null" ] && [ -n "$cpuset_cpus" ]; then
        echo -e "  CPU Set:             ${cpuset_cpus}"
    else
        echo -e "  CPU Set:             все доступные CPU"
    fi
    if [ "$cpuset_mems" != "null" ] && [ -n "$cpuset_mems" ]; then
        echo -e "  Memory Nodes:        ${cpuset_mems}"
    else
        echo -e "  Memory Nodes:        все доступные узлы"
    fi
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

# Если передан аргумент, показываем ресурсы для указанного контейнера
if [ $# -eq 0 ]; then
    echo -e "${YELLOW}Доступные контейнеры:${NC}"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    echo ""
    echo "Использование: $0 <имя_контейнера>"
    echo "Пример: $0 load_balancer_backend1"
else
    show_container_resources "$1"
fi

