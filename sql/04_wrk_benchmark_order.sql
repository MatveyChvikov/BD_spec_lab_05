-- LAB 05: заказ с фиксированными UUID для wrk (loadtest/wrk/order_card.lua).
-- Запуск (после поднятого postgres): docker compose exec -T db psql -U postgres -d marketplace -f /sql/04_wrk_benchmark_order.sql

BEGIN;

INSERT INTO users (id, email, name, created_at)
VALUES (
    '11111111-1111-4111-8111-111111111111'::uuid,
    'wrk_benchmark@lab05.test',
    'WRK Benchmark',
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name;

INSERT INTO orders (id, user_id, status, total_amount, created_at)
VALUES (
    '22222222-2222-4222-8222-222222222222'::uuid,
    '11111111-1111-4111-8111-111111111111'::uuid,
    'created',
    1000,
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    user_id = EXCLUDED.user_id,
    status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount;

INSERT INTO order_status_history (order_id, status, changed_at)
SELECT '22222222-2222-4222-8222-222222222222'::uuid, 'created', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM order_status_history
    WHERE order_id = '22222222-2222-4222-8222-222222222222'::uuid
);

COMMIT;
