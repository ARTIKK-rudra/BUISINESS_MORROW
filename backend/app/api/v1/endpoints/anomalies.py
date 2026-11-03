from fastapi import APIRouter, Depends, Query

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.ml import AnomalyDetectionResponse, AnomalyRead
from app.services.anomaly_detection import AnomalyDetectionService
from app.services.authorization import Permission

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get(
    "",
    response_model=list[AnomalyRead],
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def list_anomalies(
    membership: MembershipDep,
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return await AnomalyDetectionService(session).list(membership.business_id, limit)


@router.post(
    "/detect",
    response_model=AnomalyDetectionResponse,
    dependencies=[Depends(require_permission(Permission.INSIGHTS_WRITE))],
)
async def detect_anomalies(membership: MembershipDep, principal: PrincipalDep, session: SessionDep):
    return await AnomalyDetectionService(session).detect(membership.business_id, principal.user_id)
