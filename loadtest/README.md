# Load testing for LAB 05

## Цель
Сравнить RPS и latency до/после включения Redis-кэша.

## Вариант 1: wrk
```bash
wrk -t4 -c100 -d30s -s loadtest/wrk/catalog.lua http://localhost:8082
wrk -t4 -c100 -d30s -s loadtest/wrk/order_card.lua http://localhost:8082
```

## Вариант 2: locust
```bash
pip install -r loadtest/requirements.txt
locust -f loadtest/locustfile.py --host=http://localhost:8082
```

## Что сравнить в отчёте
1. RPS (requests/sec)
2. Latency (avg/p95)
3. Ошибки (если есть)

## Сценарий сравнения
1. Замер без кэша (`use_cache=false` или отключённая логика кэша).
2. Замер с кэшем (`use_cache=true`, прогретый Redis).
3. Сравнение чисел в `REPORT.md`.
