"""Доменные сущности заказа."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List

from .exceptions import (
    OrderAlreadyPaidError,
    OrderCancelledError,
    InvalidQuantityError,
    InvalidPriceError,
)


class OrderStatus(str, Enum):
    """Статусы заказа (значения совпадают со справочником в БД)."""

    CREATED = "created"
    PAID = "paid"
    CANCELLED = "cancelled"
    SHIPPED = "shipped"
    COMPLETED = "completed"


@dataclass
class OrderItem:
    """Позиция заказа."""

    product_name: str
    price: Decimal
    quantity: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    order_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise InvalidQuantityError(self.quantity)
        if self.price < 0:
            raise InvalidPriceError(self.price)

    @property
    def subtotal(self) -> Decimal:
        return self.price * Decimal(self.quantity)


@dataclass
class OrderStatusChange:
    """Запись истории смены статуса заказа."""

    order_id: uuid.UUID
    status: OrderStatus
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Order:
    """Заказ пользователя."""

    user_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    status: OrderStatus = OrderStatus.CREATED
    total_amount: Decimal = field(default_factory=lambda: Decimal("0"))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    items: List[OrderItem] = field(default_factory=list)
    status_history: List[OrderStatusChange] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.status_history and self.status == OrderStatus.CREATED:
            self._append_history(OrderStatus.CREATED)

    def _recalculate_total(self) -> None:
        self.total_amount = sum((i.subtotal for i in self.items), Decimal("0"))

    def _append_history(self, status: OrderStatus) -> None:
        self.status_history.append(
            OrderStatusChange(order_id=self.id, status=status)
        )

    def add_item(self, product_name: str, price: Decimal, quantity: int) -> OrderItem:
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        if self.status != OrderStatus.CREATED:
            raise ValueError("Items can only be added while order is in created status")
        item = OrderItem(
            product_name=product_name,
            price=price,
            quantity=quantity,
            order_id=self.id,
        )
        self.items.append(item)
        self._recalculate_total()
        return item

    def pay(self) -> None:
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        if self.status != OrderStatus.CREATED:
            raise OrderAlreadyPaidError(self.id)
        self.status = OrderStatus.PAID
        self._append_history(OrderStatus.PAID)

    def cancel(self) -> None:
        if self.status == OrderStatus.CANCELLED:
            raise OrderCancelledError(self.id)
        if self.status != OrderStatus.CREATED:
            raise OrderAlreadyPaidError(self.id)
        self.status = OrderStatus.CANCELLED
        self._append_history(OrderStatus.CANCELLED)

    def ship(self) -> None:
        if self.status != OrderStatus.PAID:
            raise ValueError("Order must be paid before shipping")
        self.status = OrderStatus.SHIPPED
        self._append_history(OrderStatus.SHIPPED)

    def complete(self) -> None:
        if self.status != OrderStatus.SHIPPED:
            raise ValueError("Order must be shipped before completion")
        self.status = OrderStatus.COMPLETED
        self._append_history(OrderStatus.COMPLETED)
