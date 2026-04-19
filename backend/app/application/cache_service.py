"""Кэширование каталога и карточки заказа (LAB 05)."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.cache_keys import (
    DEFAULT_CACHE_TTL_SECONDS,
    catalog_key,
    order_card_key,
)
from app.infrastructure.redis_client import get_redis


class CacheService:
    """Redis-кэш для агрегата каталога и карточки заказа."""

    def __init__(self, session: AsyncSession, *, ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS):
        self.session = session
        self._redis = get_redis()
        self._ttl = ttl_seconds

    def _is_postgres(self) -> bool:
        return self.session.get_bind().dialect.name == "postgresql"

    async def get_catalog(self, *, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            raw = await self._redis.get(catalog_key())
            if raw is not None:
                return json.loads(raw)

        rows = await self._fetch_catalog_rows()
        if use_cache:
            await self._redis.set(catalog_key(), json.dumps(rows, ensure_ascii=False), ex=self._ttl)
        return rows

    async def _fetch_catalog_rows(self) -> list[dict[str, Any]]:
        """Каталог как агрегат по order_items.product_name."""
        result = await self.session.execute(
            text(
                """
                SELECT product_name,
                       COUNT(*) AS items_count,
                       COALESCE(SUM(subtotal), 0) AS revenue
                FROM order_items
                GROUP BY product_name
                ORDER BY product_name
                """
            )
        )
        out: list[dict[str, Any]] = []
        for row in result.fetchall():
            rev = row[2]
            out.append(
                {
                    "product_name": row[0],
                    "items_count": int(row[1]),
                    "revenue": float(rev) if rev is not None else 0.0,
                }
            )
        return out

    async def get_order_card(self, order_id: str, *, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            raw = await self._redis.get(order_card_key(order_id))
            if raw is not None:
                return json.loads(raw)

        card = await self._fetch_order_card_from_db(order_id)
        if use_cache:
            await self._redis.set(
                order_card_key(order_id),
                json.dumps(card, ensure_ascii=False),
                ex=self._ttl,
            )
        return card

    async def _fetch_order_card_from_db(self, order_id: str) -> dict[str, Any]:
        oid_sql = "CAST(:oid AS uuid)" if self._is_postgres() else ":oid"
        orow = await self.session.execute(
            text(
                f"""
                SELECT id, user_id, status, total_amount, created_at
                FROM orders WHERE id = {oid_sql}
                """
            ),
            {"oid": order_id},
        )
        row = orow.fetchone()
        if row is None:
            return {"error": "not_found", "order_id": order_id}

        items_res = await self.session.execute(
            text(
                f"""
                SELECT product_name, price, quantity, subtotal
                FROM order_items WHERE order_id = {oid_sql}
                ORDER BY id
                """
            ),
            {"oid": order_id},
        )
        items: list[dict[str, Any]] = []
        for ir in items_res.fetchall():
            items.append(
                {
                    "product_name": ir[0],
                    "price": float(ir[1]),
                    "quantity": int(ir[2]),
                    "subtotal": float(ir[3]),
                }
            )

        created = row[4]
        if hasattr(created, "isoformat"):
            created_s = created.isoformat()
        else:
            created_s = str(created)

        total = row[3]
        return {
            "order_id": str(row[0]),
            "user_id": str(row[1]),
            "status": row[2],
            "total_amount": float(total) if total is not None else 0.0,
            "created_at": created_s,
            "items": items,
            "source": "database",
        }

    async def invalidate_order_card(self, order_id: str) -> None:
        await self._redis.delete(order_card_key(order_id))

    async def invalidate_catalog(self) -> None:
        await self._redis.delete(catalog_key())
