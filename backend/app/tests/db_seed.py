"""Вспомогательные функции для подготовки данных в тестах."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.infrastructure import db


async def seed_order_in_created_status() -> uuid.UUID:
    """Создаёт пользователя и заказ в статусе created (PostgreSQL или SQLite)."""
    user_id = uuid.uuid4()
    order_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    email = f"u{order_id.hex[:10]}@lab04.test"

    async with db.SessionLocal() as session:
        if db.engine.dialect.name == "postgresql":
            await session.execute(
                text(
                    """
                    INSERT INTO users (id, email, name, created_at)
                    VALUES (CAST(:id AS uuid), :email, :name, :ts)
                    """
                ),
                {"id": str(user_id), "email": email, "name": "lab", "ts": now},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO orders (id, user_id, status, total_amount, created_at)
                    VALUES (CAST(:oid AS uuid), CAST(:uid AS uuid), 'created', 0, :ts)
                    """
                ),
                {"oid": str(order_id), "uid": str(user_id), "ts": now},
            )
        else:
            await session.execute(
                text(
                    """
                    INSERT INTO users (id, email, name, created_at)
                    VALUES (:id, :email, :name, :ts)
                    """
                ),
                {"id": str(user_id), "email": email, "name": "lab", "ts": now},
            )
            await session.execute(
                text(
                    """
                    INSERT INTO orders (id, user_id, status, total_amount, created_at)
                    VALUES (:oid, :uid, 'created', 0, :ts)
                    """
                ),
                {"oid": str(order_id), "uid": str(user_id), "ts": now},
            )
        await session.commit()
    return order_id
