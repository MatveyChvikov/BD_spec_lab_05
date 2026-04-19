\timing on

-- ============================================
-- LAB 05: Источник данных каталога (без Redis)
-- ============================================
--
-- Этот запрос можно использовать как "источник истины" для каталога,
-- а затем кэшировать его результат в Redis.

SELECT
    oi.product_name,
    count(*) AS order_lines,
    sum(oi.quantity) AS sold_qty,
    round(avg(oi.price)::numeric, 2) AS avg_price
FROM order_items oi
GROUP BY oi.product_name
ORDER BY sold_qty DESC
LIMIT 100;
