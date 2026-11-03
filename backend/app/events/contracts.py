from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    SALE_CREATED = "SALE_CREATED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    REFUND_CREATED = "REFUND_CREATED"
    PURCHASE_CREATED = "PURCHASE_CREATED"
    INVENTORY_UPDATED = "INVENTORY_UPDATED"
    STOCK_LOW = "STOCK_LOW"
    STOCK_CRITICAL = "STOCK_CRITICAL"
    STOCK_OUT_OF_STOCK = "STOCK_OUT_OF_STOCK"
    FORECAST_UPDATED = "FORECAST_UPDATED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    REORDER_RECOMMENDED = "REORDER_RECOMMENDED"
    NOTIFICATION_CREATED = "NOTIFICATION_CREATED"
    GOODS_RECEIVED = "GOODS_RECEIVED"


class BusinessEvent(BaseModel):
    """Versioned, tenant-scoped event envelope; payloads must not contain secrets/credentials."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: EventType
    schema_version: int = Field(ge=1)
    business_id: UUID
    aggregate_type: str = Field(min_length=1, max_length=80)
    aggregate_id: str = Field(min_length=1, max_length=100)
    occurred_at: datetime
    correlation_id: str | None = Field(default=None, max_length=100)
    payload: dict[str, Any]
