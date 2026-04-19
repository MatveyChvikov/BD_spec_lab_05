"""Pydantic schemas for API request/response."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# User schemas
class CreateUser(BaseModel):
    email: EmailStr
    name: str = ""


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


# Order schemas
class CreateOrder(BaseModel):
    user_id: uuid.UUID


class AddOrderItem(BaseModel):
    product_name: str = Field(..., min_length=1)
    price: Decimal = Field(..., ge=0)
    quantity: int = Field(..., gt=0)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_name: str
    price: Decimal
    quantity: int
    subtotal: Decimal


class OrderStatusChangeResponse(BaseModel):
    id: uuid.UUID
    status: str
    changed_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    total_amount: Decimal
    created_at: datetime
    items: List[OrderItemResponse] = []


class OrderDetailResponse(OrderResponse):
    status_history: List[OrderStatusChangeResponse] = []


# Error response
class ErrorResponse(BaseModel):
    detail: str
