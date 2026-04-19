"""
LAB 05: Проверка починки через событийную инвалидацию.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_order_card_is_fresh_after_event_invalidation():
    email = f"ev_{uuid.uuid4().hex}@example.com"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        u = await ac.post("/api/users", json={"email": email, "name": "Event"})
        assert u.status_code == 201, u.text
        user_id = u.json()["id"]
        o = await ac.post("/api/orders", json={"user_id": user_id})
        assert o.status_code == 201, o.text
        order_id = o.json()["id"]

        await ac.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")

        m = await ac.post(
            f"/api/cache-demo/orders/{order_id}/mutate-with-event-invalidation",
            json={"new_total_amount": 777.25},
        )
        assert m.status_code == 200, m.text

        r2 = await ac.get(f"/api/cache-demo/orders/{order_id}/card?use_cache=true")
        assert r2.status_code == 200, r2.text
        assert abs(r2.json()["order_card"]["total_amount"] - 777.25) < 0.01
