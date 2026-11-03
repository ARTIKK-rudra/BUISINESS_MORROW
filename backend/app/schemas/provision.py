from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProvisionCaseStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demo_mode: bool = False
    idempotency_key: str | None = Field(default=None, max_length=100)


class ProvisionQuantity(BaseModel):
    inventory_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class ProvisionManagerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(min_length=1, max_length=2000)
    quantities: list[ProvisionQuantity] = Field(default_factory=list, max_length=100)


class ProvisionOwnerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(min_length=1, max_length=2000)


class ProvisionConflictResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(min_length=1, max_length=2000)
    quantities: list[ProvisionQuantity] = Field(min_length=1, max_length=100)


class ProvisionQuoteItem(BaseModel):
    inventory_id: UUID
    available_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ProvisionSupplierResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(min_length=1, max_length=2000)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    delivery_days: int = Field(ge=0, le=365)
    items: list[ProvisionQuoteItem] = Field(min_length=1, max_length=100)


class ProvisionPurchaseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool
    transcript: str = Field(min_length=1, max_length=2000)
