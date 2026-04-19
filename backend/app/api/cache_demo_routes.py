"""Cache consistency demo endpoints for LAB 05."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.cache_events import CacheInvalidationEventBus, OrderUpdatedEvent
from app.application.cache_service import CacheService
from app.infrastructure.db import get_db


router = APIRouter(prefix="/api/cache-demo", tags=["cache-demo"])


class UpdateOrderRequest(BaseModel):
    """Payload для изменения заказа в demo-сценариях."""

    new_total_amount: float


def _event_bus() -> CacheInvalidationEventBus:
    return CacheInvalidationEventBus()


def _order_id_sql(session: AsyncSession) -> str:
    return "CAST(:oid AS uuid)" if session.get_bind().dialect.name == "postgresql" else ":oid"


@router.get("/catalog")
async def get_catalog(
    use_cache: bool = True,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Кэш каталога товаров в Redis."""
    cache = CacheService(db)
    try:
        return {"use_cache": use_cache, "catalog": await cache.get_catalog(use_cache=use_cache)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/orders/{order_id}/card")
async def get_order_card(
    order_id: uuid.UUID,
    use_cache: bool = True,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Кэш карточки заказа (ключ order_card:v1:{order_id})."""
    cache = CacheService(db)
    oid = str(order_id)
    try:
        data = await cache.get_order_card(oid, use_cache=use_cache)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if isinstance(data, dict) and data.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="Order not found")
    return {"use_cache": use_cache, "order_card": data}


@router.post("/orders/{order_id}/mutate-without-invalidation")
async def mutate_without_invalidation(
    order_id: uuid.UUID,
    payload: UpdateOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Намеренно сломанный сценарий: меняем total_amount в БД и НЕ трогаем Redis.
    """
    if payload.new_total_amount < 0:
        raise HTTPException(status_code=400, detail="total_amount must be >= 0")
    oid_sql = _order_id_sql(db)
    res = await db.execute(
        text(
            f"""
            UPDATE orders SET total_amount = :amt WHERE id = {oid_sql}
            """
        ),
        {"amt": payload.new_total_amount, "oid": str(order_id)},
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "status": "updated",
        "order_id": str(order_id),
        "new_total_amount": payload.new_total_amount,
        "cache_invalidation": False,
        "note": "Кэш не инвалидирован — возможны устаревшие данные.",
    }


@router.post("/orders/{order_id}/mutate-with-event-invalidation")
async def mutate_with_event_invalidation(
    order_id: uuid.UUID,
    payload: UpdateOrderRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Изменение заказа + событие OrderUpdated и инвалидизация ключей каталога/карточки."""
    if payload.new_total_amount < 0:
        raise HTTPException(status_code=400, detail="total_amount must be >= 0")
    oid_sql = _order_id_sql(db)
    res = await db.execute(
        text(
            f"""
            UPDATE orders SET total_amount = :amt WHERE id = {oid_sql}
            """
        ),
        {"amt": payload.new_total_amount, "oid": str(order_id)},
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Order not found")

    bus = _event_bus()
    await bus.publish_order_updated(OrderUpdatedEvent(order_id=str(order_id)))

    return {
        "status": "updated",
        "order_id": str(order_id),
        "new_total_amount": payload.new_total_amount,
        "cache_invalidation": True,
        "invalidated_keys": [
            f"order_card:v1:{order_id}",
            "catalog:v1",
        ],
    }
