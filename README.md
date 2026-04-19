# Лабораторная работа №5
## Redis-кэш, консистентность данных и rate limiting

## Важное уточнение
ЛР5 является **продолжением ЛР4/ЛР3/ЛР2** и выполняется на том же проекте.

В `lab_05` уже лежит кодовая база из предыдущей лабораторной:
- `backend/`
- `frontend/`
- Docker-инфраструктура
- ранее реализованные механизмы (включая сценарии оплаты)

## Цель работы
Реализовать и исследовать:
1. Redis-кэш для каталога товаров и карточки заказа.
2. Намеренно сломанный сценарий консистентности:
   - изменить заказ в БД,
   - не инвалидировать кэш,
   - показать stale data для пользователя.
3. Починку через корректную инвалидацию по событию.
4. Rate limiting endpoint оплаты через Redis
   (защита от DDoS и случайных двойных кликов).
5. Замеры RPS до/после кэша через `wrk` или `locust`.

## Что дано готовым
1. Redis в `docker-compose.yml`.
2. Шаблоны backend:
   - `backend/app/infrastructure/redis_client.py`
   - `backend/app/infrastructure/cache_keys.py`
   - `backend/app/middleware/rate_limit_middleware.py`
   - `backend/app/api/cache_demo_routes.py`
   - `backend/app/application/cache_service.py`
   - `backend/app/application/cache_events.py`
3. Шаблон миграции:
   - `backend/migrations/003_cache_invalidation_events.sql` (опционально)
4. Шаблоны тестов:
   - `backend/app/tests/test_cache_stale_consistency.py`
   - `backend/app/tests/test_cache_event_invalidation.py`
   - `backend/app/tests/test_payment_rate_limit_redis.py`
5. Шаблоны нагрузочного тестирования:
   - `loadtest/wrk/*.lua`
   - `loadtest/locustfile.py`

## Что нужно реализовать (TODO)

### 1) Redis-кэш каталога и карточки заказа
Файлы:
- `backend/app/api/cache_demo_routes.py`
- `backend/app/application/cache_service.py`

Требования:
- кэш `catalog`;
- кэш `order card` по `order_id`;
- TTL для кэша;
- поддержка режима `use_cache=true/false` для сравнения в бенчмарках.

### 2) Намеренно сломанная консистентность
Файл:
- `backend/app/api/cache_demo_routes.py` (`mutate-without-invalidation`)

Нужно показать:
1. кэш прогрет;
2. заказ изменён в БД;
3. кэш не инвалидирован;
4. клиент видит устаревшие данные.

### 3) Починка через событийную инвалидацию
Файлы:
- `backend/app/application/cache_events.py`
- `backend/app/api/cache_demo_routes.py` (`mutate-with-event-invalidation`)
- `backend/app/application/cache_service.py`
- (опционально) `backend/migrations/003_cache_invalidation_events.sql`

Требования:
- при событии изменения заказа инвалидировать связанные ключи:
  - `order_card:v1:{order_id}`
  - `catalog:v1` (если затрагивается агрегат каталога).

### 4) Rate limiting endpoint оплаты через Redis
Файл:
- `backend/app/middleware/rate_limit_middleware.py`

Требования:
- ограничение частоты на endpoint оплаты;
- при превышении — `429 Too Many Requests`;
- заголовки лимита (например `X-RateLimit-*`).

### 5) Замеры RPS до/после кэша
Файлы:
- `loadtest/wrk/catalog.lua` — `use_cache=true` (кэш);
- `loadtest/wrk/catalog_no_cache.lua` — `use_cache=false` (без кэша);
- `loadtest/wrk/order_card.lua` / `order_card_no_cache.lua` — то же для карточки;
- `loadtest/locustfile.py` — в UI Locust отдельные строки по `name` для cache on/off.

Нужно сравнить:
1. `use_cache=false` (или отключённый кэш);
2. `use_cache=true` (прогретый Redis: перед замером с `true` погоняйте сценарий или сделайте несколько GET вручную);
3. RPS / latency / error rate (wrk: четыре команды в шаге 5 внизу; locust: сравните столбцы по именам задач).

## Запуск
```bash
cd lab_05
docker compose down -v
docker compose up -d --build
```

Проверка (все команды из каталога репозитория `lab_05` после `docker compose up -d --build`):

```bash
curl -sS http://127.0.0.1:8082/health
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5174/
docker compose exec -T db pg_isready -U postgres
docker compose exec -T redis redis-cli ping
```

Порты на хосте (как в условии лабораторной):

- Backend: http://localhost:8082/health  
- Frontend: http://localhost:5174  
- PostgreSQL: `localhost:5434`  
- Redis: `localhost:6380`

Если при `docker compose up` ошибка «Bind … port is already allocated» (другая лаба уже заняла порт), остановите лишний `docker compose` или задайте свои порты в файле `.env` в каталоге `lab_05`, например:

```
POSTGRES_HOST_PORT=54346
BACKEND_HOST_PORT=8092
REDIS_HOST_PORT=6381
FRONTEND_HOST_PORT=5175
```

## Рекомендуемый порядок выполнения
```bash
cd lab_05

# Сначала поднять все сервисы (включая backend). Без этого `docker compose exec backend …` выдаст
# «service backend is not running».
docker compose up -d --build
docker compose ps    # у сервиса backend должен быть статус Up

# 1) Данные для demo и для wrk order_card (фиксированный UUID — см. sql/04_wrk_benchmark_order.sql)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/01_prepare_demo_order.sql
docker compose exec -T db psql -U postgres -d marketplace -f /sql/04_wrk_benchmark_order.sql

# 2–3) Кэш, demo endpoints, rate limiting и тесты ЛР2–4 уже в репозитории
# (backend/app/api/cache_demo_routes.py, cache_service.py, rate_limit_middleware.py).

# 4) Тесты LAB 05 — в условии проверочные файлы задаются по одному:
# После изменений в backend всегда пересобирайте образ и перезапускайте контейнер,
# иначе exec попадёт в старый образ без актуальных pytest.ini/conftest/requirements:
#   docker compose build backend && docker compose up -d backend
docker compose exec -T backend pytest app/tests/test_cache_stale_consistency.py -v -s
docker compose exec -T backend pytest app/tests/test_cache_event_invalidation.py -v -s
docker compose exec -T backend pytest app/tests/test_payment_rate_limit_redis.py -v -s

# Все три файла одной командой (быстрая проверка):
docker compose exec -T backend pytest app/tests/test_cache_stale_consistency.py app/tests/test_cache_event_invalidation.py app/tests/test_payment_rate_limit_redis.py -v --tb=short

docker compose exec -T backend pytest app/tests/ -q --tb=short

# Альтернатива без постоянно работающего backend (одноразовый контейнер, db и redis уже должны быть Up):
# docker compose run --rm backend pytest app/tests/test_cache_stale_consistency.py app/tests/test_cache_event_invalidation.py app/tests/test_payment_rate_limit_redis.py -v --tb=short

# 5) Нагрузочные замеры RPS (wrk — на хосте; base URL без path)
# Если в WSL/Ubuntu нет wrk:  sudo apt update && sudo apt install -y wrk   (apt, не app)
# Перед order_card засейте заказ: см. шаг 1 и sql/04_wrk_benchmark_order.sql
#
# Только прогретый кэш (типовые две команды из условия):
wrk -t4 -c100 -d30s -s loadtest/wrk/catalog.lua http://localhost:8082
wrk -t4 -c100 -d30s -s loadtest/wrk/order_card.lua http://localhost:8082
#
# Сравнение с выключенным кэшем (те же параметры wrk; занесите RPS/latency в отчёт):
wrk -t4 -c100 -d30s -s loadtest/wrk/catalog_no_cache.lua http://localhost:8082
wrk -t4 -c100 -d30s -s loadtest/wrk/order_card_no_cache.lua http://localhost:8082
#
# Locust — on/off в одном прогоне по именам задач:
#   locust -f loadtest/locustfile.py --host=http://localhost:8082
#   (опционально LAB05_ORDER_ID=22222222-2222-4222-8222-222222222222)
```

## Структура LAB 05
```
lab_05/
├── backend/
│   ├── app/
│   │   ├── api/cache_demo_routes.py
│   │   ├── application/cache_service.py
│   │   ├── application/cache_events.py
│   │   ├── middleware/rate_limit_middleware.py
│   │   └── tests/
│   │       ├── test_cache_stale_consistency.py
│   │       ├── test_cache_event_invalidation.py
│   │       └── test_payment_rate_limit_redis.py
│   └── migrations/
│       └── 003_cache_invalidation_events.sql
├── loadtest/
│   ├── wrk/catalog.lua
│   ├── wrk/catalog_no_cache.lua
│   ├── wrk/order_card.lua
│   ├── wrk/order_card_no_cache.lua
│   └── locustfile.py
├── sql/
│   ├── 01_prepare_demo_order.sql
│   ├── 02_check_order_card_source.sql
│   ├── 03_catalog_source_query.sql
│   └── 04_wrk_benchmark_order.sql
├── REPORT.md
└── README.md
```

## Критерии оценки
- Реализация Redis-кэша и демонстрация stale data — 30%
- Починка через событийную инвалидацию — 25%
- Redis rate limiting на оплате — 20%
- Бенчмарки RPS до/после кэша — 15%
- Качество отчёта и выводов — 10%
