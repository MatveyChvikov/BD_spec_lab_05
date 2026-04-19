-- wrk: карточка заказа с кэшем (LAB 05)
--
-- UUID совпадает с sql/04_wrk_benchmark_order.sql — выполните перед wrk:
--   docker compose exec -T db psql -U postgres -d marketplace -f /sql/04_wrk_benchmark_order.sql
--
-- Другой заказ: замените ORDER_UUID ниже и wrk.path.
--
-- Для замера без кэша: ...?use_cache=false

local ORDER_UUID = "22222222-2222-4222-8222-222222222222"

wrk.method = "GET"
wrk.path = "/api/cache-demo/orders/" .. ORDER_UUID .. "/card?use_cache=true"
