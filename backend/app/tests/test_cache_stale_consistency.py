"""
LAB 05: Демонстрация неконсистентности кэша.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_stale_order_card_when_db_updated_without_invalidation():
    """
    1) Прогреть кэш карточки заказа.
    2) Изменить заказ в БД без инвалидизации кэша.
    3) Повторный GET с use_cache=true возвращает устаревшие данные.
    """
    email = f"stale_{uuid.uuid4().hex}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        u = await ac.post("/api/users", json={"email": email, "name": "Stale"})
        assert u.status_code == 201, u.text
        user_id = u.json()["id"]
        o = await ac.post("/api/orders", json={"user_id": user_id})
        assert o.status_code == 201, o.text
        order_id = o.json()["id"]

        warm = await ac.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")
        assert warm.status_code == 200, warm.text
        old_total = warm.json()["order_card"]["total_amount"]

        m = await ac.post(
            f"/api/cache-demo/orders/{order_id}/mutate-without-invalidation",
            json={"new_total_amount": 9999.5},
        )
        assert m.status_code == 200, m.text

        cached = await ac.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")
        assert cached.status_code == 200, cached.text
        assert cached.json()["order_card"]["total_amount"] == old_total

        fresh = await ac.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=false")
        assert fresh.status_code == 200, fresh.text
        assert abs(fresh.json()["order_card"]["total_amount"] - 9999.5) < 0.01
