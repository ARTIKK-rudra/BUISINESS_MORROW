from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.dependencies import (
    MembershipDep,
    PrincipalDep,
    SessionDep,
    require_permission,
)
from app.core.config import get_settings
from app.core.errors import ConflictError, ForbiddenError, NotConfiguredError, NotFoundError
from app.db.models import (
    AuditLog,
    BusinessMembership,
    ProvisionCase,
    VoiceAlertSettings,
    VoiceCallTask,
    VoiceContact,
    VoiceConversation,
    VoiceConversationTurn,
    VoiceInteraction,
)
from app.schemas.assistant import AssistantAnswer, VoiceQuestion
from app.schemas.provision import (
    ProvisionCaseStart,
    ProvisionConflictResolution,
    ProvisionManagerResponse,
    ProvisionOwnerDecision,
    ProvisionPurchaseDecision,
    ProvisionSupplierResponse,
)
from app.services.website_assistant import WebsiteAssistantService
from app.services.authorization import Permission
from app.services.gemini_voice import GeminiVoiceService
from app.services.local_provision import LocalProvisionService
from app.services.outbound_voice import start_conversation_call
from app.services.provision_voice import ProvisionVoiceService

router = APIRouter(prefix="/voice", tags=["voice"])


class VoiceAlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    enabled: bool


class VoiceContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=160)
    role: Literal["owner", "manager", "supplier"]
    phone: str = Field(pattern=r"^\+91[6-9]\d{9}$")
    is_active: bool = True
    calling_consent: bool = False


class VoiceContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: Literal["owner", "manager", "supplier"] | None = None
    phone: str | None = Field(default=None, pattern=r"^\+91[6-9]\d{9}$")
    is_active: bool | None = None
    calling_consent: bool | None = None


class MockOwnerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(default="", max_length=2000)
    digits: str | None = Field(default=None, pattern=r"^[123]$")


def require_owner(membership: MembershipDep) -> BusinessMembership:
    if membership.role != "owner":
        raise ForbiddenError("Only the business owner can configure automatic phone alerts")
    return membership


OwnerMembershipDep = Annotated[BusinessMembership, Depends(require_owner)]


def contact_payload(contact: VoiceContact) -> dict:
    return {
        "id": contact.id,
        "full_name": contact.full_name,
        "role": contact.role,
        "phone": contact.phone,
        "is_active": contact.is_active,
        "calling_consent": contact.calling_consent,
        "consent_recorded_at": contact.consent_recorded_at,
        "created_at": contact.created_at,
        "updated_at": contact.updated_at,
    }


def conversation_payload(
    conversation: VoiceConversation, turns: list[VoiceConversationTurn]
) -> dict:
    return {
        "id": conversation.id,
        "workflow": conversation.workflow,
        "status": conversation.status,
        "provider_call_sid": conversation.provider_call_sid,
        "shortage_snapshot": conversation.shortage_snapshot,
        "supplier_contact_authorized": conversation.supplier_contact_authorized,
        "purchase_authorized": conversation.purchase_authorized,
        "turn_count": conversation.turn_count,
        "last_error": conversation.last_error,
        "created_at": conversation.created_at,
        "completed_at": conversation.completed_at,
        "turns": [
            {
                "id": turn.id,
                "speaker": turn.speaker,
                "transcript": turn.transcript,
                "structured_data": turn.structured_data,
                "created_at": turn.created_at,
            }
            for turn in turns
        ],
    }


def provision_case_payload(case: ProvisionCase) -> dict:
    return {
        "id": case.id,
        "status": case.status,
        "demo_mode": case.demo_mode,
        "shortage_snapshot": case.shortage_snapshot,
        "manager_recommendations": case.manager_recommendations,
        "supplier_quote": case.supplier_quote,
        "approval": case.approval,
        "purchase_id": case.purchase_id,
        "created_at": case.created_at,
        "completed_at": case.completed_at,
    }


async def get_provision_case(
    session: SessionDep, business_id: UUID, case_id: UUID
) -> ProvisionCase:
    case = await session.scalar(
        select(ProvisionCase).where(
            ProvisionCase.id == case_id, ProvisionCase.business_id == business_id
        )
    )
    if case is None:
        raise NotFoundError("Provision case not found")
    return case


async def load_conversation_payload(session: SessionDep, conversation: VoiceConversation) -> dict:
    turns = list(
        await session.scalars(
            select(VoiceConversationTurn)
            .where(VoiceConversationTurn.conversation_id == conversation.id)
            .order_by(VoiceConversationTurn.created_at)
        )
    )
    return conversation_payload(conversation, turns)


@router.get("/contacts")
async def list_voice_contacts(membership: OwnerMembershipDep, session: SessionDep):
    rows = await session.scalars(
        select(VoiceContact)
        .where(VoiceContact.business_id == membership.business_id)
        .order_by(VoiceContact.role, VoiceContact.full_name)
    )
    return [contact_payload(row) for row in rows]


@router.post("/contacts", status_code=201)
async def create_voice_contact(
    payload: VoiceContactCreate,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    existing = await session.scalar(
        select(VoiceContact).where(
            VoiceContact.business_id == membership.business_id, VoiceContact.phone == payload.phone
        )
    )
    if existing:
        raise ConflictError("A voice contact with this phone number already exists")
    now = datetime.now(UTC)
    contact = VoiceContact(
        business_id=membership.business_id,
        full_name=payload.full_name.strip(),
        role=payload.role,
        phone=payload.phone,
        is_active=payload.is_active,
        calling_consent=payload.calling_consent,
        consent_recorded_at=now if payload.calling_consent else None,
    )
    session.add(contact)
    await session.flush()
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action="voice.contact.created",
            entity_type="voice_contact",
            entity_id=str(contact.id),
            metadata_json={"role": contact.role, "calling_consent": contact.calling_consent},
            created_at=now,
        )
    )
    await session.commit()
    await session.refresh(contact)
    return contact_payload(contact)


@router.patch("/contacts/{contact_id}")
async def update_voice_contact(
    contact_id: UUID,
    payload: VoiceContactUpdate,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    contact = await session.scalar(
        select(VoiceContact).where(
            VoiceContact.id == contact_id, VoiceContact.business_id == membership.business_id
        )
    )
    if contact is None:
        raise NotFoundError("Voice contact not found")
    changes = payload.model_dump(exclude_unset=True)
    if "phone" in changes and changes["phone"] != contact.phone:
        duplicate = await session.scalar(
            select(VoiceContact).where(
                VoiceContact.business_id == membership.business_id,
                VoiceContact.phone == changes["phone"],
                VoiceContact.id != contact.id,
            )
        )
        if duplicate:
            raise ConflictError("A voice contact with this phone number already exists")
    for field, value in changes.items():
        if field == "full_name" and value is not None:
            value = value.strip()
        setattr(contact, field, value)
    if "calling_consent" in changes:
        contact.consent_recorded_at = datetime.now(UTC) if contact.calling_consent else None
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action="voice.contact.updated",
            entity_type="voice_contact",
            entity_id=str(contact.id),
            metadata_json={"changed_fields": sorted(changes)},
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(contact)
    return contact_payload(contact)


@router.post("/conversations/owner-shortage", status_code=201)
async def start_mock_owner_shortage_conversation(
    membership: OwnerMembershipDep, principal: PrincipalDep, session: SessionDep
):
    if not get_settings().voice_test_mode:
        raise ForbiddenError("Use the live call workflow when voice test mode is disabled")
    conversation = await ProvisionVoiceService(session).create_owner_shortage_conversation(
        membership.business_id
    )
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action="voice.owner_shortage_mock_started",
            entity_type="voice_conversation",
            entity_id=str(conversation.id),
            metadata_json={"mode": "test", "workflow": conversation.workflow},
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(conversation)
    return await load_conversation_payload(session, conversation)


@router.post("/conversations/{conversation_id}/mock-response")
async def mock_owner_conversation_response(
    conversation_id: UUID,
    payload: MockOwnerResponse,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    if not get_settings().voice_test_mode:
        raise ForbiddenError("Mock responses are disabled outside voice test mode")
    if not payload.transcript.strip() and not payload.digits:
        raise ConflictError("Provide a transcript or a supported DTMF digit")
    conversation, response = await ProvisionVoiceService(session).record_owner_response(
        conversation_id, membership.business_id, payload.transcript.strip(), payload.digits
    )
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action="voice.owner_shortage_mock_response",
            entity_type="voice_conversation",
            entity_id=str(conversation.id),
            metadata_json={
                "mode": "test",
                "status": conversation.status,
                "supplier_contact_authorized": conversation.supplier_contact_authorized,
            },
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(conversation)
    result = await load_conversation_payload(session, conversation)
    result["agent_response"] = response
    return result


@router.get("/conversations/{conversation_id}")
async def get_voice_conversation(
    conversation_id: UUID, membership: OwnerMembershipDep, session: SessionDep
):
    conversation = await session.scalar(
        select(VoiceConversation).where(
            VoiceConversation.id == conversation_id,
            VoiceConversation.business_id == membership.business_id,
        )
    )
    if conversation is None:
        raise NotFoundError("Voice conversation not found")
    return await load_conversation_payload(session, conversation)


@router.post("/conversations/{conversation_id}/dial")
async def dial_owner_conversation(
    conversation_id: UUID,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    """Explicit owner action only; no automatic supplier or purchase calls exist here."""
    settings = get_settings()
    if settings.voice_test_mode:
        raise ForbiddenError("Live dialing is disabled while VOICE_TEST_MODE is enabled")
    if not settings.outbound_voice_configured or not settings.voice_webhooks_configured:
        raise NotConfiguredError(
            "Live dialing requires Twilio credentials, VOICE_LIVE_CALLS_ENABLED=true, "
            "and a public HTTPS VOICE_PUBLIC_BASE_URL"
        )
    conversation = await session.scalar(
        select(VoiceConversation).where(
            VoiceConversation.id == conversation_id,
            VoiceConversation.business_id == membership.business_id,
            VoiceConversation.workflow == "owner_shortage_authorization",
        )
    )
    if conversation is None:
        raise NotFoundError("Owner provision conversation not found")
    if conversation.status != "awaiting_owner_authorization" or conversation.provider_call_sid:
        raise ConflictError("This conversation is not available for a new live call")
    contact = await session.scalar(
        select(VoiceContact).where(
            VoiceContact.id == conversation.contact_id,
            VoiceContact.business_id == membership.business_id,
            VoiceContact.role == "owner",
            VoiceContact.is_active.is_(True),
            VoiceContact.calling_consent.is_(True),
        )
    )
    if contact is None:
        raise ConflictError("The owner contact is inactive or lacks calling consent")
    base = (settings.voice_public_base_url or "").rstrip("/")
    result = await start_conversation_call(
        contact.phone,
        f"{base}/api/v1/voice/webhooks/owner/{conversation.id}",
        f"{base}/api/v1/voice/webhooks/status/{conversation.id}",
    )
    conversation.provider_call_sid = result.get("sid")
    conversation.status = "dialing"
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action="voice.owner_shortage_live_dial_requested",
            entity_type="voice_conversation",
            entity_id=str(conversation.id),
            metadata_json={"contact_id": str(contact.id)},
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    await session.refresh(conversation)
    return await load_conversation_payload(session, conversation)


@router.get("/provision/cases")
async def list_local_provision_cases(membership: OwnerMembershipDep, session: SessionDep):
    rows = await LocalProvisionService(session).list_cases(membership.business_id)
    return [provision_case_payload(row) for row in rows]


@router.post("/provision/cases", status_code=201)
async def start_local_provision_case(
    payload: ProvisionCaseStart,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    """Starts a browser-only workflow; it never dials or contacts any phone."""
    case = await LocalProvisionService(session).start(
        membership.business_id,
        principal.user_id,
        demo_mode=payload.demo_mode,
        idempotency_key=payload.idempotency_key,
    )
    return provision_case_payload(case)


@router.post("/provision/cases/{case_id}/owner-decision")
async def local_owner_decision(
    case_id: UUID,
    payload: ProvisionOwnerDecision,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    case = await get_provision_case(session, membership.business_id, case_id)
    case = await LocalProvisionService(session).owner_decision(
        case, principal.user_id, payload.transcript
    )
    return provision_case_payload(case)


@router.post("/provision/cases/{case_id}/managers/{contact_id}/response")
async def local_manager_response(
    case_id: UUID,
    contact_id: UUID,
    payload: ProvisionManagerResponse,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    case = await get_provision_case(session, membership.business_id, case_id)
    quantities = {str(row.inventory_id): row.quantity for row in payload.quantities}
    case = await LocalProvisionService(session).manager_response(
        case, contact_id, principal.user_id, payload.transcript, quantities
    )
    return provision_case_payload(case)


@router.post("/provision/cases/{case_id}/resolve-conflict")
async def local_owner_conflict_resolution(
    case_id: UUID,
    payload: ProvisionConflictResolution,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    case = await get_provision_case(session, membership.business_id, case_id)
    quantities = {str(row.inventory_id): row.quantity for row in payload.quantities}
    case = await LocalProvisionService(session).resolve_conflict(
        case, principal.user_id, payload.transcript, quantities
    )
    return provision_case_payload(case)


@router.post("/provision/cases/{case_id}/supplier-response")
async def local_supplier_response(
    case_id: UUID,
    payload: ProvisionSupplierResponse,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    case = await get_provision_case(session, membership.business_id, case_id)
    case = await LocalProvisionService(session).supplier_response(
        case,
        principal.user_id,
        payload.transcript,
        payload.currency,
        payload.delivery_days,
        [row.model_dump(mode="json") for row in payload.items],
    )
    return provision_case_payload(case)


@router.post("/provision/cases/{case_id}/purchase-decision")
async def local_owner_purchase_decision(
    case_id: UUID,
    payload: ProvisionPurchaseDecision,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    case = await get_provision_case(session, membership.business_id, case_id)
    case = await LocalProvisionService(session).purchase_decision(
        case, principal.user_id, payload.transcript, payload.approve
    )
    return provision_case_payload(case)


@router.get("/stock-alerts")
async def get_stock_alert_settings(membership: OwnerMembershipDep, session: SessionDep):
    config = await session.scalar(
        select(VoiceAlertSettings).where(VoiceAlertSettings.business_id == membership.business_id)
    )
    return {
        "recipient_phone": config.recipient_phone if config else None,
        "enabled": config.enabled if config else False,
        "provider_configured": get_settings().outbound_voice_configured,
        "test_mode": get_settings().voice_test_mode,
        "provider": "twilio",
        "events": ["STOCK_LOW", "STOCK_CRITICAL", "STOCK_OUT_OF_STOCK"],
    }


@router.put("/stock-alerts")
async def update_stock_alert_settings(
    payload: VoiceAlertUpdate,
    membership: OwnerMembershipDep,
    principal: PrincipalDep,
    session: SessionDep,
):
    settings = get_settings()
    if payload.enabled and not settings.voice_delivery_enabled:
        raise NotConfiguredError(
            "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER "
            "in the backend environment before enabling calls"
        )
    config = await session.scalar(
        select(VoiceAlertSettings).where(VoiceAlertSettings.business_id == membership.business_id)
    )
    if config is None:
        config = VoiceAlertSettings(
            business_id=membership.business_id,
            recipient_phone=payload.recipient_phone,
            enabled=payload.enabled,
        )
        session.add(config)
        await session.flush()
        action = (
            "voice.stock_alerts.enabled" if payload.enabled else "voice.stock_alerts.configured"
        )
    else:
        action = "voice.stock_alerts.enabled" if payload.enabled else "voice.stock_alerts.disabled"
        config.recipient_phone = payload.recipient_phone
        config.enabled = payload.enabled
    session.add(
        AuditLog(
            business_id=membership.business_id,
            actor_user_id=principal.user_id,
            action=action,
            entity_type="voice_alert_settings",
            entity_id=str(config.id),
            metadata_json={"enabled": payload.enabled, "recipient_phone": payload.recipient_phone},
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return {
        "recipient_phone": config.recipient_phone,
        "enabled": config.enabled,
        "provider_configured": settings.outbound_voice_configured,
        "test_mode": settings.voice_test_mode,
        "provider": "twilio",
    }


@router.get("/stock-alerts/calls")
async def list_stock_alert_calls(
    membership: OwnerMembershipDep,
    session: SessionDep,
):
    rows = await session.scalars(
        select(VoiceCallTask)
        .where(VoiceCallTask.business_id == membership.business_id)
        .order_by(VoiceCallTask.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": row.id,
            "status": row.status,
            "attempts": row.attempts,
            "provider_call_sid": row.provider_call_sid,
            "last_error": row.last_error,
            "created_at": row.created_at,
            "processed_at": row.processed_at,
        }
        for row in rows
    ]


@router.post(
    "/ask",
    response_model=AssistantAnswer,
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def voice_ask(
    payload: VoiceQuestion, membership: MembershipDep, principal: PrincipalDep, session: SessionDep
):
    result = await WebsiteAssistantService(session).answer(
        membership.business_id, payload.question, payload.current_route, payload.conversation_history
    )
    # Gemini only turns the already verified SQL response into concise speech.
    # It has no database, procurement, or authorization access.
    result["answer"] = await GeminiVoiceService(get_settings()).spoken_answer(
        payload.question, result["answer"]
    )
    if payload.consent_to_store_transcript:
        session.add(
            VoiceInteraction(
                business_id=membership.business_id,
                user_id=principal.user_id,
                provider_session=payload.conversation_session,
                transcript=payload.question,
                consent_recorded=True,
            )
        )
        await session.commit()
    return result


@router.post(
    "/transcribe",
    dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))],
)
async def transcribe_browser_audio(
    audio: UploadFile = File(...),
):
    """Optional browser-recording fallback for Web Speech network failures."""
    allowed_types = {"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"}
    if audio.content_type not in allowed_types:
        raise ConflictError("Use a WebM, OGG, MP4, MPEG, or WAV audio recording")
    data = await audio.read(8 * 1024 * 1024 + 1)
    if not data:
        raise ConflictError("The audio recording is empty")
    if len(data) > 8 * 1024 * 1024:
        raise ConflictError("The audio recording exceeds the 8 MB limit")
    settings = get_settings()
    if not settings.gemini_configured:
        raise NotConfiguredError(
            "Gemini audio transcription is not configured. Add GEMINI_API_KEY to the local API environment to enable this fallback."
        )
    try:
        transcript = await GeminiVoiceService(settings).transcribe_audio(data, audio.content_type)
    except RuntimeError as exc:
        raise ConflictError(str(exc)) from exc
    return {"transcript": transcript, "provider": "gemini"}
