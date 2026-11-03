from fastapi import APIRouter, Depends

from app.api.dependencies import MembershipDep, SessionDep, require_permission
from app.schemas.assistant import AssistantAnswer, AssistantQuestion
from app.services.website_assistant import WebsiteAssistantService
from app.services.authorization import Permission

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/ask",
    response_model=AssistantAnswer,
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def ask(payload: AssistantQuestion, membership: MembershipDep, session: SessionDep):
    return await WebsiteAssistantService(session).answer(
        membership.business_id, payload.question, payload.current_route, payload.conversation_history
    )
