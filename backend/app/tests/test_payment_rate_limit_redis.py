"""
LAB 05: Rate limiting endpoint оплаты через Redis.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_payment_endpoint_rate_limit(created_order_id):
    order_id = str(created_order_id)
    # Уникальный subject, чтобы не пересекаться с другими тестами.
    headers = {"X-Forwarded-For": f"203.0.113.{abs(hash(order_id)) % 200 + 1}"}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=headers
    ) as ac:
        for i in range(5):
            r = await ac.post(
                f"/api/orders/{order_id}/pay",
                headers=headers,
            )
            assert r.status_code != 429, f"iter {i}: {r.text}"
            assert r.headers.get("X-RateLimit-Limit") == "5"
            rem = r.headers.get("X-RateLimit-Remaining")
            assert rem is not None
            assert int(rem) >= 0

        r6 = await ac.post(
            f"/api/orders/{order_id}/pay",
            headers=headers,
        )
        assert r6.status_code == 429, r6.text
        assert r6.headers.get("X-RateLimit-Limit") == "5"
        assert r6.json().get("detail") == "Too Many Requests"
