# Быстрый старт — LAB 05 (Redis Cache + Rate Limiting)

## 1) Запуск окружения
```bash
cd lab_05
docker compose down -v
docker compose up -d --build
```

## 2) Подготовка demo-данных
```bash
docker compose exec -T db psql -U postgres -d marketplace -f /sql/01_prepare_demo_order.sql
```

## 3) Реализация кэша
Заполните TODO в:
- `backend/app/api/cache_demo_routes.py`
- `backend/app/application/cache_service.py`

Проверьте ручной сценарий:
1. Прогреть кэш `GET /api/cache-demo/orders/{id}/card?use_cache=true`
2. Изменить БД без инвалидации `POST /api/cache-demo/orders/{id}/mutate-without-invalidation`
3. Убедиться в stale data.

## 4) Починка через событийную инвалидацию
Заполните TODO в:
- `backend/app/application/cache_events.py`
- `backend/app/api/cache_demo_routes.py` (`mutate-with-event-invalidation`)

Повторите сценарий и покажите, что stale data исчезла.

## 5) Реализация rate limiting
Заполните TODO в:
- `backend/app/middleware/rate_limit_middleware.py`

Проверьте:
- допустимые запросы проходят;
- при превышении лимита приходит `429`.

## 6) Тесты LAB 05
```bash
docker compose exec -T backend pytest app/tests/test_cache_stale_consistency.py -v -s
docker compose exec -T backend pytest app/tests/test_cache_event_invalidation.py -v -s
docker compose exec -T backend pytest app/tests/test_payment_rate_limit_redis.py -v -s
```

## 7) Замеры RPS (wrk или locust)
```bash
wrk -t4 -c100 -d30s -s loadtest/wrk/catalog.lua http://localhost:8082
wrk -t4 -c100 -d30s -s loadtest/wrk/order_card.lua http://localhost:8082
```

Сравните результаты до/после кэша в `REPORT.md`.
