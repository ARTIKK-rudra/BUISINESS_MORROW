from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.schemas.common import ORMModel, Timestamped


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: EmailStr | None = None
    contact_name: str | None = Field(default=None, max_length=160)


class SupplierRead(Timestamped):
    business_id: UUID
    name: str
    email: str | None
    contact_name: str | None
    is_active: bool


class PurchaseCreate(BaseModel):
    supplier_id: UUID
    items: list["PurchaseItemCreate"] = Field(min_length=1, max_length=100)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def no_duplicate_products(self) -> "PurchaseCreate":
        item_ids = [(item.product_id, item.ingredient_id) for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Each stock item may appear only once per purchase")
        return self


class PurchaseItemCreate(BaseModel):
    product_id: UUID | None = None
    ingredient_id: UUID | None = None
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def one_stock_item(self):
        if (self.product_id is None) == (self.ingredient_id is None):
            raise ValueError("Specify exactly one of product_id or ingredient_id")
        return self


class PurchaseRead(Timestamped):
    business_id: UUID
    supplier_id: UUID
    status: str
    total: Decimal
    currency: str
    items: list["PurchaseItemRead"]


class PurchaseItemRead(ORMModel):
    id: UUID
    product_id: UUID | None
    ingredient_id: UUID | None
    quantity: Decimal
    received_quantity: Decimal
    unit_cost: Decimal


class RefundRead(Timestamped):
    business_id: UUID
    payment_id: UUID
    amount: Decimal
    currency: str
    reason: str | None
    status: str


class GoodsReceiptItemCreate(BaseModel):
    purchase_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    lot_code: str | None = Field(default=None, min_length=1, max_length=100)
    expires_on: date | None = None


class GoodsReceiptCreate(BaseModel):
    items: list[GoodsReceiptItemCreate] = Field(min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique_purchase_items(self):
        ids = [item.purchase_item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each purchase line may appear once per receipt")
        return self


class GoodsReceiptRead(Timestamped):
    business_id: UUID
    purchase_id: UUID
    received_by: UUID | None
    received_at: datetime
    items: list["GoodsReceiptItemRead"]


class GoodsReceiptItemRead(ORMModel):
    purchase_item_id: UUID
    inventory_batch_id: UUID
    quantity: Decimal


class SupplierPriceHistoryRead(BaseModel):
    id: UUID
    unit_cost: Decimal
    currency: str
    effective_at: datetime


class SupplierPricePoint(BaseModel):
    unit_cost: Decimal
    currency: str
    effective_at: datetime


class SupplierOfferIntelligence(BaseModel):
    supplier_product_id: UUID
    item_id: UUID
    item_name: str
    item_type: str
    available: bool
    unit_cost: Decimal
    currency: str
    lead_time_days: int
    minimum_order_quantity: Decimal
    price_change_percent: Decimal | None
    price_observations: int
    price_history: list[SupplierPricePoint]
    purchase_quantity: Decimal
    purchase_count: int
    delivered_line_count: int
    on_time_line_count: int
    reliability_observation_count: int


class SupplierIntelligenceRead(BaseModel):
    id: UUID
    name: str
    email: str | None
    contact_name: str | None
    is_active: bool
    availability_count: int
    purchase_count: int
    purchase_spend: Decimal
    currency: str
    delivered_line_count: int
    reliability_observation_count: int
    on_time_rate: Decimal | None
    average_actual_lead_days: Decimal | None
    offers: list[SupplierOfferIntelligence]
