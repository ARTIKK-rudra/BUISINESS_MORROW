from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class OrderCreate(BaseModel):
    customer_id: UUID | None = None
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    idempotency_key: str | None = Field(default=None, max_length=100)
    payment_method: str = Field(default="cash", pattern="^cash$")


class OrderItemRead(ORMModel):
    id: UUID
    order_id: UUID
    product_id: UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal
    line_total: Decimal


class OrderRead(ORMModel):
    id: UUID
    business_id: UUID
    customer_id: UUID | None
    status: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    placed_at: datetime
    items: list[OrderItemRead] = Field(default_factory=list)


class PaymentRead(ORMModel):
    id: UUID
    business_id: UUID
    order_id: UUID
    amount: Decimal
    currency: str
    status: str
    method: str | None
    created_at: datetime


class RefundCreate(BaseModel):
    payment_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(default=None, max_length=240)
    restock: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)
