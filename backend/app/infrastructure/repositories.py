"""Реализация репозиториев с использованием SQLAlchemy."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User
from app.domain.order import Order, OrderItem, OrderStatus, OrderStatusChange


def _parse_dt(value) -> datetime:
    if value is None:
        return datetime.utcnow()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


class UserRepository:
    """Репозиторий для User."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, user: User) -> None:
        await self.session.execute(
            text(
                """
                INSERT INTO users (id, email, name, created_at)
                VALUES (:id, :email, :name, :created_at)
                ON CONFLICT (id) DO UPDATE SET
                    email = excluded.email,
                    name = excluded.name,
                    created_at = excluded.created_at
                """
            ),
            {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at,
            },
        )

    async def find_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        result = await self.session.execute(
            text(
                "SELECT id, email, name, created_at FROM users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
        row = result.fetchone()
        if row is None:
            return None
        u = object.__new__(User)
        u.id = uuid.UUID(str(row[0]))
        u.email = row[1]
        u.name = row[2] or ""
        u.created_at = _parse_dt(row[3])
        return u

    async def find_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            text(
                "SELECT id, email, name, created_at FROM users WHERE email = :email"
            ),
            {"email": email.strip()},
        )
        row = result.fetchone()
        if row is None:
            return None
        u = object.__new__(User)
        u.id = uuid.UUID(str(row[0]))
        u.email = row[1]
        u.name = row[2] or ""
        u.created_at = _parse_dt(row[3])
        return u

    async def find_all(self) -> List[User]:
        result = await self.session.execute(
            text("SELECT id, email, name, created_at FROM users ORDER BY created_at")
        )
        users: List[User] = []
        for row in result.fetchall():
            u = object.__new__(User)
            u.id = uuid.UUID(str(row[0]))
            u.email = row[1]
            u.name = row[2] or ""
            u.created_at = _parse_dt(row[3])
            users.append(u)
        return users


class OrderRepository:
    """Репозиторий для Order."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, order: Order) -> None:
        exists = await self.session.execute(
            text("SELECT 1 FROM orders WHERE id = :id"),
            {"id": str(order.id)},
        )
        payload = {
            "id": str(order.id),
            "user_id": str(order.user_id),
            "status": order.status.value,
            "total_amount": str(order.total_amount),
            "created_at": order.created_at,
        }
        if exists.scalar():
            await self.session.execute(
                text(
                    """
                    UPDATE orders
                    SET user_id = :user_id,
                        status = :status,
                        total_amount = :total_amount
                    WHERE id = :id
                    """
                ),
                payload,
            )
        else:
            await self.session.execute(
                text(
                    """
                    INSERT INTO orders (id, user_id, status, total_amount, created_at)
                    VALUES (:id, :user_id, :status, :total_amount, :created_at)
                    """
                ),
                payload,
            )

        await self.session.execute(
            text("DELETE FROM order_items WHERE order_id = :oid"),
            {"oid": str(order.id)},
        )
        for item in order.items:
            await self.session.execute(
                text(
                    """
                    INSERT INTO order_items
                        (id, order_id, product_name, price, quantity, subtotal)
                    VALUES
                        (:id, :order_id, :product_name, :price, :quantity, :subtotal)
                    """
                ),
                {
                    "id": str(item.id),
                    "order_id": str(order.id),
                    "product_name": item.product_name,
                    "price": float(item.price),
                    "quantity": item.quantity,
                    "subtotal": float(item.subtotal),
                },
            )

        hist = await self.session.execute(
            text("SELECT id FROM order_status_history WHERE order_id = :oid"),
            {"oid": str(order.id)},
        )
        existing_hist_ids = {str(row[0]) for row in hist.fetchall()}
        for h in order.status_history:
            hid = str(h.id)
            if hid in existing_hist_ids:
                continue
            await self.session.execute(
                text(
                    """
                    INSERT INTO order_status_history (id, order_id, status, changed_at)
                    VALUES (:id, :order_id, :status, :changed_at)
                    """
                ),
                {
                    "id": hid,
                    "order_id": str(order.id),
                    "status": h.status.value,
                    "changed_at": h.changed_at,
                },
            )

    async def find_by_id(self, order_id: uuid.UUID) -> Optional[Order]:
        o_row = await self.session.execute(
            text(
                """
                SELECT id, user_id, status, total_amount, created_at
                FROM orders WHERE id = :id
                """
            ),
            {"id": str(order_id)},
        )
        orow = o_row.fetchone()
        if orow is None:
            return None

        order = object.__new__(Order)
        order.id = uuid.UUID(str(orow[0]))
        order.user_id = uuid.UUID(str(orow[1]))
        order.status = OrderStatus(orow[2])
        order.total_amount = Decimal(str(orow[3]))
        order.created_at = _parse_dt(orow[4])
        order.items = []
        order.status_history = []

        items = await self.session.execute(
            text(
                """
                SELECT id, order_id, product_name, price, quantity
                FROM order_items WHERE order_id = :oid
                ORDER BY id
                """
            ),
            {"oid": str(order_id)},
        )
        for row in items.fetchall():
            it = object.__new__(OrderItem)
            it.id = uuid.UUID(str(row[0]))
            it.order_id = uuid.UUID(str(row[1]))
            it.product_name = row[2]
            it.price = Decimal(str(row[3]))
            it.quantity = int(row[4])
            order.items.append(it)

        hist = await self.session.execute(
            text(
                """
                SELECT id, order_id, status, changed_at
                FROM order_status_history WHERE order_id = :oid
                ORDER BY changed_at
                """
            ),
            {"oid": str(order_id)},
        )
        for row in hist.fetchall():
            ch = object.__new__(OrderStatusChange)
            ch.id = uuid.UUID(str(row[0]))
            ch.order_id = uuid.UUID(str(row[1]))
            ch.status = OrderStatus(row[2])
            ch.changed_at = _parse_dt(row[3])
            order.status_history.append(ch)

        return order

    async def find_by_user(self, user_id: uuid.UUID) -> List[Order]:
        result = await self.session.execute(
            text(
                """
                SELECT id FROM orders WHERE user_id = :uid
                ORDER BY created_at
                """
            ),
            {"uid": str(user_id)},
        )
        orders: List[Order] = []
        for row in result.fetchall():
            oid = uuid.UUID(str(row[0]))
            loaded = await self.find_by_id(oid)
            if loaded is not None:
                orders.append(loaded)
        return orders

    async def find_all(self) -> List[Order]:
        result = await self.session.execute(
            text("SELECT id FROM orders ORDER BY created_at")
        )
        orders: List[Order] = []
        for row in result.fetchall():
            oid = uuid.UUID(str(row[0]))
            loaded = await self.find_by_id(oid)
            if loaded is not None:
                orders.append(loaded)
        return orders
