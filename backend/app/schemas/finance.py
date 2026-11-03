from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExpenseCreate(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="USD", pattern="^[A-Z]{3}$")
    occurred_at: datetime | None = None
    idempotency_key: str | None = Field(default=None, max_length=100)


class ExpenseRead(ORMModel):
    id: UUID
    business_id: UUID
    category: str
    description: str
    amount: Decimal
    currency: str
    occurred_at: datetime


class LedgerEntryRead(ORMModel):
    id: UUID
    business_id: UUID
    account: str
    source_type: str
    source_id: str
    debit: Decimal
    credit: Decimal
    currency: str
    occurred_at: datetime
