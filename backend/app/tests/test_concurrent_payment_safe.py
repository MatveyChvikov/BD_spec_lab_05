"""Демонстрация защиты pay_order_safe (PostgreSQL)."""

pytest_plugins = ("app.tests.conftest_concurrent",)

import asyncio

import pytest

from app.application.payment_service import PaymentService
from app.domain.exceptions import OrderAlreadyPaidError
from app.infrastructure.db import SessionLocal
from app.tests.conftest_concurrent import requires_postgres
from app.tests.db_seed import seed_order_in_created_status


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_payment_safe_prevents_race_condition():
    order_id = await seed_order_in_created_status()

    async def pay1():
        async with SessionLocal() as s1:
            return await PaymentService(s1).pay_order_safe(order_id)

    async def pay2():
        async with SessionLocal() as s2:
            return await PaymentService(s2).pay_order_safe(order_id)

    results = await asyncio.gather(pay1(), pay2(), return_exceptions=True)
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = sum(1 for r in results if isinstance(r, Exception))
    assert success_count == 1
    assert error_count == 1
    assert any(isinstance(r, OrderAlreadyPaidError) for r in results)

    async with SessionLocal() as s:
        hist = await PaymentService(s).get_payment_history(order_id)
    assert len(hist) == 1
    print("✅ RACE CONDITION PREVENTED!")
    print(f"  - {hist[0]['changed_at']}: status = {hist[0]['status']}")


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_payment_safe_with_explicit_timing():
    order_id = await seed_order_in_created_status()

    async def pay1():
        async with SessionLocal() as s1:
            return await PaymentService(s1).pay_order_safe(
                order_id, delay_after_row_lock_sec=0.15
            )

    async def pay2():
        await asyncio.sleep(0.02)
        async with SessionLocal() as s2:
            return await PaymentService(s2).pay_order_safe(order_id)

    results = await asyncio.gather(pay1(), pay2(), return_exceptions=True)
    assert sum(1 for r in results if not isinstance(r, Exception)) == 1

    async with SessionLocal() as s:
        hist = await PaymentService(s).get_payment_history(order_id)
    assert len(hist) == 1


@requires_postgres
@pytest.mark.asyncio
async def test_concurrent_payment_safe_multiple_orders():
    o1 = await seed_order_in_created_status()
    o2 = await seed_order_in_created_status()

    async def pay_a():
        async with SessionLocal() as s:
            return await PaymentService(s).pay_order_safe(o1)

    async def pay_b():
        async with SessionLocal() as s:
            return await PaymentService(s).pay_order_safe(o2)

    await asyncio.gather(pay_a(), pay_b())
    async with SessionLocal() as s:
        h1 = await PaymentService(s).get_payment_history(o1)
        h2 = await PaymentService(s).get_payment_history(o2)
    assert len(h1) == 1 and len(h2) == 1
