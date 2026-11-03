from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, Timestamped


class ModelVersionRead(Timestamped):
    business_id: UUID
    model_type: str
    version: str
    status: str
    dataset_kind: str
    training_rows: int
    feature_names: list[str]
    metrics: dict[str, Any] | None
    metadata_json: dict[str, Any] | None
    artifact_uri: str | None
    trained_at: datetime
    evaluated_at: datetime | None


class ForecastRead(ORMModel):
    id: UUID
    business_id: UUID
    target_type: str
    target_id: str
    period_start: date
    period_end: date
    point_value: Decimal
    lower_value: Decimal | None
    upper_value: Decimal | None
    model_version: str
    provenance: dict[str, Any] | None
    generated_at: datetime


class ForecastTrainRequest(BaseModel):
    product_id: UUID


class ForecastGenerateRequest(BaseModel):
    product_id: UUID
    horizon_days: int = Field(default=14, ge=1, le=90)


class ForecastTrainResponse(BaseModel):
    product_id: UUID
    dataset_kind: str
    observations: int
    evaluations: list[dict[str, Any]]
    selected_model_version: str | None
    status: str
    message: str


class PredictionRead(ORMModel):
    id: UUID
    business_id: UUID
    prediction_type: str
    target_type: str
    target_id: str
    predicted_value: Decimal | None
    probability: Decimal | None
    model_version: str
    provenance: dict[str, Any] | None
    created_at: datetime


class AnomalyRead(ORMModel):
    id: UUID
    business_id: UUID
    entity_type: str
    entity_id: str
    severity: str
    score: Decimal | None
    summary: str
    status: str
    model_version: str
    provenance: dict[str, Any] | None
    created_at: datetime


class AnomalyDetectionResponse(BaseModel):
    dataset_kind: str
    inspected: dict[str, int]
    detected: int
    skipped: dict[str, str]


class StockoutPredictionRead(BaseModel):
    inventory_id: UUID
    item_id: UUID
    item_type: str
    on_hand: Decimal
    supplier_lead_time_days: int
    expected_demand_during_lead_time: Decimal
    expected_stockout_date: date | None
    remaining_stock_days: int | None
    stockout_probability: Decimal
    generated_at: datetime
    important_factors: list[str]
    uncertainty: str
    model_version: str
