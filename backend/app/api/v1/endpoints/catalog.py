from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.catalog import CategoryCreate, CategoryRead, ProductCreate, ProductRead
from app.services.authorization import Permission
from app.services.catalog import CatalogService

router = APIRouter(tags=["catalog"])


@router.get(
    "/products",
    response_model=list[ProductRead],
    dependencies=[Depends(require_permission(Permission.CATALOG_READ))],
)
async def list_products(membership: MembershipDep, session: SessionDep):
    return await CatalogService(session).list_products(membership.business_id)


@router.post(
    "/products",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOG_WRITE))],
)
async def create_product(
    payload: ProductCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await CatalogService(session).create_product(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/categories",
    response_model=list[CategoryRead],
    dependencies=[Depends(require_permission(Permission.CATALOG_READ))],
)
async def list_categories(membership: MembershipDep, session: SessionDep):
    return await CatalogService(session).list_categories(membership.business_id)


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOG_WRITE))],
)
async def create_category(
    payload: CategoryCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await CatalogService(session).create_category(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )
