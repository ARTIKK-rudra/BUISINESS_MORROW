from fastapi import APIRouter

from app.api.dependencies import PrincipalDep, SessionDep
from app.core.errors import NotFoundError
from app.repositories.businesses import BusinessRepository
from app.schemas.business import BusinessRead

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("/me", response_model=BusinessRead)
async def current_business(principal: PrincipalDep, session: SessionDep):
    business = await BusinessRepository(session).get_for_member(
        principal.user_id, principal.business_id
    )
    if business is None:
        raise NotFoundError("Business not found")
    return business
