from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import MembershipDep, PrincipalDep, SessionDep, require_permission
from app.schemas.recipes import (
    IngredientCreate,
    IngredientRead,
    RecipeCreate,
    RecipeRead,
)
from app.services.authorization import Permission
from app.services.inventory_catalog import InventoryCatalogService
from app.services.units import available_units

router = APIRouter(tags=["inventory catalog"])


@router.get("/units", dependencies=[Depends(require_permission(Permission.CATALOG_READ))])
async def list_units():
    return available_units()


@router.get(
    "/ingredients",
    response_model=list[IngredientRead],
    dependencies=[Depends(require_permission(Permission.CATALOG_READ))],
)
async def list_ingredients(membership: MembershipDep, session: SessionDep):
    return await InventoryCatalogService(session).list_ingredients(membership.business_id)


@router.post(
    "/ingredients",
    response_model=IngredientRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOG_WRITE))],
)
async def create_ingredient(
    payload: IngredientCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryCatalogService(session).create_ingredient(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.get(
    "/recipes",
    response_model=list[RecipeRead],
    dependencies=[Depends(require_permission(Permission.CATALOG_READ))],
)
async def list_recipes(membership: MembershipDep, session: SessionDep):
    return await InventoryCatalogService(session).list_recipes(membership.business_id)


@router.post(
    "/recipes",
    response_model=RecipeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission(Permission.CATALOG_WRITE))],
)
async def create_recipe(
    payload: RecipeCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryCatalogService(session).save_recipe(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
    )


@router.put(
    "/recipes/{recipe_id}",
    response_model=RecipeRead,
    dependencies=[Depends(require_permission(Permission.CATALOG_WRITE))],
)
async def update_recipe(
    recipe_id: UUID,
    payload: RecipeCreate,
    membership: MembershipDep,
    principal: PrincipalDep,
    request: Request,
    session: SessionDep,
):
    return await InventoryCatalogService(session).save_recipe(
        membership.business_id,
        principal.user_id,
        payload,
        getattr(request.state, "request_id", None),
        recipe_id,
    )
