from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.common import Timestamped

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)]


class CategoryCreate(BaseModel):
    name: ShortText
    description: str | None = Field(default=None, max_length=2000)
    parent_id: UUID | None = None


class CategoryRead(Timestamped):
    business_id: UUID
    name: str
    description: str | None
    parent_id: UUID | None


class ProductCreate(BaseModel):
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    name: ShortText
    description: str | None = Field(default=None, max_length=2000)
    category_id: UUID | None = None
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)] = (
        "each"
    )


class ProductRead(Timestamped):
    business_id: UUID
    category_id: UUID | None
    sku: str
    name: str
    description: str | None
    price: Decimal
    unit: str
    is_active: bool
