"""Событийная инвалидация кэша (LAB 05).

Вариант C из README: синхронная публикация события после изменения заказа
и прямая инвалидизация ключей Redis.
"""

from dataclasses import dataclass

from app.infrastructure.cache_keys import catalog_key, order_card_key
from app.infrastructure.redis_client import get_redis


@dataclass
class OrderUpdatedEvent:
    """Событие изменения заказа."""

    order_id: str


class CacheInvalidationEventBus:
    """Минимальный event bus: OrderUpdated → удаление ключей в Redis."""

    async def publish_order_updated(self, event: OrderUpdatedEvent) -> None:
        r = get_redis()
        await r.delete(order_card_key(event.order_id))
        await r.delete(catalog_key())
