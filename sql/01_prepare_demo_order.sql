\timing on

-- ============================================
-- LAB 05: Подготовка демо-заказа для cache-consistency сценария
-- ============================================
--
-- Скрипт опциональный, нужен для ручной проверки cache demo через API.
-- Можно создавать заказы и через frontend/API.

-- 1) Создать демо-пользователя
INSERT INTO users (email, name)
VALUES (
    'idempotency_demo_' || floor(extract(epoch from now()))::text || '@example.com',
    'Idempotency Demo User'
)
RETURNING id, email;

-- 2) Создать заказ для последующих cache consistency сценариев
WITH last_user AS (
    SELECT id
    FROM users
    ORDER BY created_at DESC
    LIMIT 1
)
INSERT INTO orders (user_id, status, total_amount)
SELECT id, 'created', 1000
FROM last_user
RETURNING id, user_id, status, total_amount, created_at;
