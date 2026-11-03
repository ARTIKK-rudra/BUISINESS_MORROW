from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.core.errors import ForbiddenError
from app.db.models import Recommendation
from app.schemas.assistant import ReorderApproval, ReorderPreview
from app.schemas.procurement import PurchaseRead
from app.services.authorization import Permission
from app.services.recommendations import RecommendationService

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))])
async def list_recommendations(
    membership: MembershipDep, session: SessionDep, limit: int = Query(50, ge=1, le=100)
):
    rows = await session.scalars(
        select(Recommendation)
        .where(Recommendation.business_id == membership.business_id)
        .order_by(Recommendation.id.desc())
        .limit(limit)
    )
    return list(rows)


@router.get(
    "/{recommendation_id}/preview",
    response_model=ReorderPreview,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def preview_reorder(
    recommendation_id: UUID,
    membership: MembershipDep,
    session: SessionDep,
):
    return await RecommendationService(session).preview_reorder(
        membership.business_id, recommendation_id
    )


@router.post(
    "/{recommendation_id}/approve",
    response_model=PurchaseRead,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def approve_reorder(
    recommendation_id: UUID,
    approval: ReorderApproval,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    if membership.role != "owner":
        raise ForbiddenError("Only a business owner can approve a recommended purchase")
    return await RecommendationService(session).approve_reorder(
        membership.business_id,
        recommendation_id,
        principal.user_id,
        getattr(request.state, "request_id", None),
        approval,
    )
