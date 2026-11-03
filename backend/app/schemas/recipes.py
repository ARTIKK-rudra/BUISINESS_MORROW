from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.schemas.common import ORMModel, Timestamped

UnitCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class IngredientCreate(BaseModel):
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]
    unit: UnitCode
    minimum_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    maximum_stock: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    safety_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)


class IngredientRead(Timestamped):
    business_id: UUID
    sku: str
    name: str
    unit: str
    minimum_stock: Decimal
    maximum_stock: Decimal | None
    safety_stock: Decimal
    is_active: bool


class RecipeIngredientInput(BaseModel):
    ingredient_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: UnitCode


class RecipeCreate(BaseModel):
    product_id: UUID
    yield_quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    yield_unit: UnitCode
    ingredients: list[RecipeIngredientInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_ingredients(self):
        ids = [item.ingredient_id for item in self.ingredients]
        if len(ids) != len(set(ids)):
            raise ValueError("A recipe may include each ingredient only once")
        return self


class RecipeIngredientRead(ORMModel):
    ingredient_id: UUID
    quantity: Decimal
    unit: str


class RecipeRead(Timestamped):
    business_id: UUID
    product_id: UUID
    yield_quantity: Decimal
    yield_unit: str
    ingredients: list[RecipeIngredientRead]


class SupplierProductCreate(BaseModel):
    product_id: UUID | None = None
    ingredient_id: UUID | None = None
    unit_cost: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    lead_time_days: int = Field(default=0, ge=0, le=365)
    minimum_order_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=3
    )

    @model_validator(mode="after")
    def one_stock_item(self):
        if (self.product_id is None) == (self.ingredient_id is None):
            raise ValueError("Specify exactly one of product_id or ingredient_id")
        return self


class SupplierProductUpdate(BaseModel):
    unit_cost: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    lead_time_days: int = Field(default=0, ge=0, le=365)
    minimum_order_quantity: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=3
    )


class SupplierProductRead(Timestamped):
    business_id: UUID
    supplier_id: UUID
    product_id: UUID | None
    ingredient_id: UUID | None
    unit_cost: Decimal
    currency: str
    lead_time_days: int
    minimum_order_quantity: Decimal


class SupplierPriceHistoryRead(ORMModel):
    id: UUID
    unit_cost: Decimal
    currency: str
    effective_at: datetime
