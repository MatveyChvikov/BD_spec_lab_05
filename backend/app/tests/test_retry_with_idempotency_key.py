"""
LAB 04: Повтор с Idempotency-Key возвращает кэш без повторного списания.
"""

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.infrastructure.db import SessionLocal
from app.main import app
from app.middleware.idempotency_middleware import REPLAY_HEADER


@pytest.mark.asyncio
async def test_retry_with_same_key_returns_cached_response(created_order_id):
    order_id = created_order_id
    payload = {"order_id": str(order_id), "mode": "unsafe"}
    key = f"idem-{uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = {"Idempotency-Key": key}
        r1 = await client.post("/api/payments/retry-demo", json=payload, headers=h)
        assert r1.status_code == 200
        body1 = r1.json()

        r2 = await client.post("/api/payments/retry-demo", json=payload, headers=h)
        assert r2.status_code == 200
        assert (r2.headers.get("x-idempotency-replayed") or r2.headers.get(REPLAY_HEADER)) == "true"
        assert r2.json() == body1

        hist = await client.get(f"/api/payments/history/{order_id}")
        paid = [p for p in hist.json()["payments"] if p.get("status") == "paid"]
        assert len(paid) == 1

    async with SessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT status, status_code, response_body
                    FROM idempotency_keys
                    WHERE idempotency_key = :k
                      AND request_method = 'POST'
                      AND request_path = '/api/payments/retry-demo'
                    """
                ),
                {"k": key},
            )
        ).mappings().first()
        assert row is not None
        assert row["status"] == "completed"
        assert row["status_code"] == 200
        rb = row["response_body"]
        if isinstance(rb, str):
            rb = json.loads(rb)
        assert "body_b64" in rb


@pytest.mark.asyncio
async def test_same_key_different_payload_returns_conflict(created_order_id):
    oid1 = str(created_order_id)
    oid2 = str(uuid.uuid4())
    key = f"idem-conflict-{uuid.uuid4()}"
    headers = {"Idempotency-Key": key}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post(
            "/api/payments/retry-demo",
            json={"order_id": oid1, "mode": "unsafe"},
            headers=headers,
        )
        assert r1.status_code == 200

        r2 = await client.post(
            "/api/payments/retry-demo",
            json={"order_id": oid2, "mode": "unsafe"},
            headers=headers,
        )
        assert r2.status_code == 409
