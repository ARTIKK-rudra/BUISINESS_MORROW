from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.procurement import (
    SupplierCreate,
    SupplierIntelligenceRead,
    SupplierRead,
)
from app.schemas.recipes import (
    SupplierPriceHistoryRead,
    SupplierProductCreate,
    SupplierProductRead,
    SupplierProductUpdate,
)
from app.services.authorization import Permission
from app.services.operations import OperationsService
from app.services.supplier_intelligence import SupplierIntelligenceService
from app.services.supplier_products import SupplierProductService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "/intelligence",
    response_model=list[SupplierIntelligenceRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def supplier_intelligence(membership: MembershipDep, session: SessionDep):
    return await SupplierIntelligenceService(session).list(membership.business_id)


@router.get(
    "",
    response_model=list[SupplierRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def list_suppliers(membership: MembershipDep, session: SessionDep):
    return await OperationsService(session).list_suppliers(membership.business_id)


@router.post(
    "",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def create_supplier(
    payload: SupplierCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await OperationsService(session).create_supplier(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/{supplier_id}/products",
    response_model=list[SupplierProductRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def list_supplier_products(supplier_id: UUID, membership: MembershipDep, session: SessionDep):
    return await SupplierProductService(session).list(membership.business_id, supplier_id)


@router.post(
    "/{supplier_id}/products",
    response_model=SupplierProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def create_supplier_product(
    supplier_id: UUID,
    payload: SupplierProductCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await SupplierProductService(session).create(
        membership.business_id,
        supplier_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.put(
    "/{supplier_id}/products/{link_id}",
    response_model=SupplierProductRead,
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_WRITE))],
)
async def update_supplier_product(
    supplier_id: UUID,
    link_id: UUID,
    payload: SupplierProductUpdate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await SupplierProductService(session).update(
        membership.business_id,
        supplier_id,
        link_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/{supplier_id}/products/{link_id}/price-history",
    response_model=list[SupplierPriceHistoryRead],
    dependencies=[Depends(require_permission(Permission.PROCUREMENT_READ))],
)
async def supplier_product_price_history(
    supplier_id: UUID, link_id: UUID, membership: MembershipDep, session: SessionDep
):
    return await SupplierProductService(session).price_history(
        membership.business_id, supplier_id, link_id
    )
