-- ============================================
-- Схема базы данных маркетплейса (лаб. 1 + основа лаб. 2)
-- ============================================
-- Лаб. 2: триггер «нельзя оплатить дважды» на таблице orders НЕ добавляется —
-- иначе демонстрация race condition в приложении (pay_order_unsafe) не даст
-- двух записей paid в order_status_history. Инвариант оплаты обеспечивается
-- безопасным методом (REPEATABLE READ + FOR UPDATE) в коде.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE order_statuses (
    status TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO order_statuses (status, description) VALUES
    ('created', 'Заказ создан'),
    ('paid', 'Заказ оплачен'),
    ('cancelled', 'Заказ отменён'),
    ('shipped', 'Заказ отправлен'),
    ('completed', 'Заказ завершён');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_email_nonempty CHECK (char_length(trim(email)) > 0),
    CONSTRAINT users_email_format CHECK (
        email ~ '^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9._-]+$'
    ),
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status TEXT NOT NULL REFERENCES order_statuses (status),
    total_amount NUMERIC(18, 2) NOT NULL DEFAULT 0
        CONSTRAINT orders_total_nonnegative CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    price NUMERIC(18, 2) NOT NULL CONSTRAINT order_items_price_nonneg CHECK (price >= 0),
    quantity INTEGER NOT NULL CONSTRAINT order_items_qty_positive CHECK (quantity > 0),
    subtotal NUMERIC(18, 2) NOT NULL CONSTRAINT order_items_subtotal_nonneg CHECK (subtotal >= 0),
    CONSTRAINT order_items_product_nonempty CHECK (char_length(trim(product_name)) > 0)
);

CREATE TABLE order_status_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    status TEXT NOT NULL REFERENCES order_statuses (status),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION refresh_order_total_amount()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target UUID;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target := OLD.order_id;
    ELSE
        target := NEW.order_id;
    END IF;

    UPDATE orders o
    SET total_amount = COALESCE(
        (
            SELECT SUM(i.subtotal)::NUMERIC(18, 2)
            FROM order_items i
            WHERE i.order_id = target
        ),
        0::NUMERIC(18, 2)
    )
    WHERE o.id = target;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trigger_order_items_refresh_total
    AFTER INSERT OR UPDATE OR DELETE ON order_items
    FOR EACH ROW
    EXECUTE PROCEDURE refresh_order_total_amount();
