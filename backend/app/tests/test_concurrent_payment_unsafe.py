"""Демонстрация race condition при pay_order_unsafe (PostgreSQL)."""

import asyncio
import os

import pytest

from app.application.payment_service import PaymentService
from app.infrastructure.db import SessionLocal
from app.tests.db_seed import seed_order_in_created_status


requires_postgres = pytest.mark.skipif(
    "postgresql" not in os.environ.get("DATABASE_URL", ""),
    reason="Гонка unsafe оплаты воспроизводится на PostgreSQL",
)


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_payment_unsafe_demonstrates_race_condition():
    order_id = await seed_order_in_created_status()

    async def pay1():
        async with SessionLocal() as s1:
            return await PaymentService(s1).pay_order_unsafe(order_id)

    async def pay2():
        async with SessionLocal() as s2:
            return await PaymentService(s2).pay_order_unsafe(order_id)

    await asyncio.gather(pay1(), pay2(), return_exceptions=True)

    async with SessionLocal() as s:
        hist = await PaymentService(s).get_payment_history(order_id)

    assert len(hist) == 2, f"Ожидались 2 записи paid (race), получено {len(hist)}"
    print("⚠️  RACE CONDITION DETECTED!")
    for record in hist:
        print(f"  - {record['changed_at']}: status = {record['status']}")


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_payment_unsafe_both_succeed():
    order_id = await seed_order_in_created_status()

    async def pay1():
        async with SessionLocal() as s1:
            return await PaymentService(s1).pay_order_unsafe(order_id)

    async def pay2():
        async with SessionLocal() as s2:
            return await PaymentService(s2).pay_order_unsafe(order_id)

    results = await asyncio.gather(pay1(), pay2(), return_exceptions=True)
    success = sum(1 for r in results if not isinstance(r, Exception))
    assert success == 2

    async with SessionLocal() as s:
        hist = await PaymentService(s).get_payment_history(order_id)
    assert len(hist) == 2
