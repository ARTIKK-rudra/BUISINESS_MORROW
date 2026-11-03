from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.db.models import ModelVersion
from app.schemas.ml import (
    ForecastGenerateRequest,
    ForecastRead,
    ModelVersionRead,
    StockoutPredictionRead,
)
from app.services.authorization import Permission
from app.services.forecasting import ForecastingService

router = APIRouter(prefix="/forecasting", tags=["forecasting"])


@router.get(
    "",
    response_model=list[ForecastRead],
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def list_forecasts(
    membership: MembershipDep,
    session: SessionDep,
    product_id: UUID | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
):
    return await ForecastingService(session).list_forecasts(
        membership.business_id, product_id, limit
    )


@router.post(
    "/generate",
    response_model=list[ForecastRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.INSIGHTS_WRITE))],
)
async def generate_forecast(
    payload: ForecastGenerateRequest,
    membership: MembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    return await ForecastingService(session).generate(
        membership.business_id, principal.user_id, payload
    )


@router.post(
    "/stockout-predictions",
    response_model=list[StockoutPredictionRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.INSIGHTS_WRITE))],
)
async def stockout_predictions(
    membership: MembershipDep, principal: PrincipalDep, session: SessionDep
):
    return await ForecastingService(session).predict_stockout(
        membership.business_id, principal.user_id
    )


@router.get(
    "/models",
    response_model=list[ModelVersionRead],
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def list_model_versions(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
):
    return list(
        await session.scalars(
            select(ModelVersion)
            .where(ModelVersion.business_id == membership.business_id)
            .order_by(ModelVersion.trained_at.desc())
            .limit(limit)
        )
    )
