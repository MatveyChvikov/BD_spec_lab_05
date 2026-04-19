"""
LAB 04: Демонстрация проблемы retry без идемпотентности.
"""

import asyncio
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tests.db_seed import seed_order_in_created_status


@pytest.mark.asyncio
async def test_retry_without_idempotency_can_double_pay():
    """
    Две параллельные попытки POST /api/payments/retry-demo без Idempotency-Key
    в режиме unsafe могут привести к двум записям paid в истории.
    """
    if "postgresql" not in os.environ.get("DATABASE_URL", ""):
        pytest.skip("Двойная оплата в unsafe надёжно демонстрируется на PostgreSQL (MVCC).")

    # Как в ЛР2: гонка не гарантирована с первого раза — несколько раундов с новым заказом.
    n = 0
    order_id = None
    for _ in range(30):
        order_id = await seed_order_in_created_status()
        payload = {"order_id": str(order_id), "mode": "unsafe"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await asyncio.gather(
                client.post("/api/payments/retry-demo", json=payload),
                client.post("/api/payments/retry-demo", json=payload),
            )
            hist = await client.get(f"/api/payments/history/{order_id}")
            assert hist.status_code == 200
            data = hist.json()
            paid = [p for p in data["payments"] if p.get("status") == "paid"]
            n = len(paid)
        if n >= 2:
            break
        await asyncio.sleep(0.05)

    assert n >= 2, (
        f"Ожидалась двойная оплата (>=2 paid в истории) за ≤30 раундов, получено {n} "
        f"(order_id={order_id})."
    )
    print("\n⚠️  Повтор без Idempotency-Key: несколько записей paid в order_status_history")
    print(f"   paid_events={n}, попыток=2, ключ не передавался — бизнес-инвариант нарушен.")


@pytest.mark.asyncio
async def test_sequential_retry_without_key_still_single_history_on_sqlite(created_order_id):
    """Последовательные вызовы без ключа: вторая попытка не должна добавлять paid (уже оплачен)."""
    order_id = created_order_id
    payload = {"order_id": str(order_id), "mode": "unsafe"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/payments/retry-demo", json=payload)
        r2 = await client.post("/api/payments/retry-demo", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        hist = await client.get(f"/api/payments/history/{order_id}")
        paid = [p for p in hist.json()["payments"] if p.get("status") == "paid"]
        assert len(paid) == 1
