from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import PrincipalDep, SessionDep
from app.db.models import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    principal: PrincipalDep, session: SessionDep, limit: int = Query(50, ge=1, le=100)
):
    rows = await session.scalars(
        select(Notification)
        .where(Notification.business_id == principal.business_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return list(rows)
