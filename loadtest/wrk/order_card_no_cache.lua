-- wrk: карточка заказа без кэша (use_cache=false). Тот же ORDER_UUID, что в order_card.lua.
-- Перед замером: sql/04_wrk_benchmark_order.sql

local ORDER_UUID = "22222222-2222-4222-8222-222222222222"

wrk.method = "GET"
wrk.path = "/api/cache-demo/orders/" .. ORDER_UUID .. "/card?use_cache=false"
