from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.schemas.common import ORMModel


class InventoryCreate(BaseModel):
    product_id: UUID | None = None
    ingredient_id: UUID | None = None
    location: str = Field(default="Main", min_length=1, max_length=120)
    reorder_point: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    unit_cost_average: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=4)
    expires_on: date | None = None
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    maximum_stock: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    safety_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)

    @model_validator(mode="after")
    def one_stock_item(self):
        if (self.product_id is None) == (self.ingredient_id is None):
            raise ValueError("Specify exactly one of product_id or ingredient_id")
        effective_minimum = (
            self.minimum_stock if "minimum_stock" in self.model_fields_set else self.reorder_point
        )
        if self.maximum_stock is not None and self.maximum_stock < effective_minimum:
            raise ValueError("maximum_stock must be at least minimum_stock")
        return self


class InventoryAdjust(BaseModel):
    quantity_delta: Decimal = Field(max_digits=14, decimal_places=3)
    reason: str = Field(min_length=2, max_length=80)
    reference: str | None = Field(default=None, max_length=120)
    unit_cost: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)

    @field_validator("quantity_delta")
    @classmethod
    def nonzero_delta(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("quantity_delta cannot be zero")
        return value


class InventoryWastage(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    reason: str = Field(default="wastage", min_length=2, max_length=80)
    reference: str | None = Field(default=None, max_length=120)


class InventoryThresholdUpdate(BaseModel):
    minimum_stock: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    maximum_stock: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    safety_stock: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class InventoryRead(ORMModel):
    id: UUID
    business_id: UUID
    product_id: UUID | None
    ingredient_id: UUID | None
    location: str
    quantity: Decimal
    unit_cost_average: Decimal
    reorder_point: Decimal
    minimum_stock: Decimal
    maximum_stock: Decimal | None
    safety_stock: Decimal
    expires_on: date | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def inventory_value(self) -> Decimal:
        return (self.quantity * self.unit_cost_average).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


class InventoryMovementRead(ORMModel):
    id: UUID
    inventory_id: UUID
    quantity_delta: Decimal
    reason: str
    reference: str | None
    actor_user_id: UUID | None
    created_at: datetime


class StockAlertRead(BaseModel):
    inventory_id: UUID
    item_id: UUID
    item_type: str
    item_name: str
    location: str
    quantity: Decimal
    state: str
    alert_kind: str
    source: str = "rule_based"
    ml_prediction: None = None
    message: str
    expires_on: date | None = None


class InventoryBatchRead(ORMModel):
    id: UUID
    inventory_id: UUID
    lot_code: str
    initial_quantity: Decimal
    quantity_remaining: Decimal
    unit_cost: Decimal
    expires_on: date | None
    created_at: datetime
