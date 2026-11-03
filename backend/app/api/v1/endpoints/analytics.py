from datetime import date

from fastapi import APIRouter, Depends

from app.api.dependencies import MembershipDep, SessionDep, require_permission
from app.db.models import RealtimeBusinessMetric
from app.services.analytics import AnalyticsService
from app.services.authorization import Permission

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/realtime", dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))])
async def realtime_analytics(membership: MembershipDep, session: SessionDep):
    row = await session.get(RealtimeBusinessMetric, membership.business_id)
    if row is None:
        return {"event_count": 0, "event_counts": {}, "amount_totals": {}, "last_event_at": None}
    return {
        "event_count": row.event_count,
        "event_counts": row.event_counts,
        "amount_totals": row.amount_totals,
        "last_event_at": row.last_event_at,
    }


@router.get("", dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))])
async def analytics_overview(
    membership: MembershipDep,
    session: SessionDep,
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date and end_date and end_date < start_date:
        from app.core.errors import ConflictError

        raise ConflictError("end_date must be on or after start_date")
    return {
        "profit_and_loss": await AnalyticsService(session).profit_and_loss(
            membership.business_id, start_date, end_date
        )
    }
