from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.inventory import (
    InventoryAdjust,
    InventoryBatchRead,
    InventoryCreate,
    InventoryMovementRead,
    InventoryRead,
    InventoryThresholdUpdate,
    InventoryWastage,
    StockAlertRead,
)
from app.services.authorization import Permission
from app.services.inventory import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get(
    "",
    response_model=list[InventoryRead],
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def list_inventory(membership: MembershipDep, session: SessionDep):
    return await InventoryService(session).list_inventory(membership.business_id)


@router.get(
    "/alerts",
    response_model=list[StockAlertRead],
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def inventory_alerts(
    membership: MembershipDep,
    session: SessionDep,
    expiring_within_days: int = Query(default=30, ge=0, le=365),
):
    return await InventoryService(session).alerts(membership.business_id, expiring_within_days)


@router.post(
    "",
    response_model=InventoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.INVENTORY_WRITE))],
)
async def create_inventory(
    payload: InventoryCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryService(session).create(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.post(
    "/{inventory_id}/adjust",
    response_model=InventoryRead,
    dependencies=[Depends(require_permission(Permission.INVENTORY_WRITE))],
)
async def adjust_inventory(
    inventory_id: UUID,
    payload: InventoryAdjust,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryService(session).adjust(
        membership.business_id,
        principal.user_id,
        inventory_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/{inventory_id}/movements",
    response_model=list[InventoryMovementRead],
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def inventory_movements(inventory_id: UUID, membership: MembershipDep, session: SessionDep):
    return await InventoryService(session).movements(membership.business_id, inventory_id)


@router.get(
    "/{inventory_id}/batches",
    response_model=list[InventoryBatchRead],
    dependencies=[Depends(require_permission(Permission.INVENTORY_READ))],
)
async def inventory_batches(inventory_id: UUID, membership: MembershipDep, session: SessionDep):
    return await InventoryService(session).batches(membership.business_id, inventory_id)


@router.post(
    "/{inventory_id}/wastage",
    response_model=InventoryRead,
    dependencies=[Depends(require_permission(Permission.INVENTORY_WRITE))],
)
async def record_wastage(
    inventory_id: UUID,
    payload: InventoryWastage,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryService(session).wastage(
        membership.business_id,
        principal.user_id,
        inventory_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.patch(
    "/{inventory_id}/thresholds",
    response_model=InventoryRead,
    dependencies=[Depends(require_permission(Permission.INVENTORY_WRITE))],
)
async def update_inventory_thresholds(
    inventory_id: UUID,
    payload: InventoryThresholdUpdate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryService(session).update_thresholds(
        membership.business_id,
        principal.user_id,
        inventory_id,
        payload,
        getattr(request.state, "request_id", None),
    )
