"""Twilio-facing endpoints. These routes deliberately have no user JWT dependency."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect

from app.core.config import Settings, get_settings
from app.db.models import VoiceConversation
from app.db.session import SessionFactory
from app.services.provision_voice import ProvisionVoiceService

router = APIRouter(prefix="/voice/webhooks", tags=["voice webhooks"])


def _canonical_url(settings: Settings, path: str, query: str = "", websocket: bool = False) -> str:
    if not settings.voice_webhooks_configured or not settings.voice_public_base_url:
        raise HTTPException(status_code=503, detail="Voice webhook public URL is not configured")
    base = settings.voice_public_base_url.rstrip("/")
    if websocket:
        base = "wss://" + base.removeprefix("https://")
    return f"{base}{path}{'?' + query if query else ''}"


def _is_valid_signature(
    token: str | None, url: str, values: dict[str, str], signature: str | None
) -> bool:
    if not token or not signature:
        return False
    payload = url + "".join(key + values[key] for key in sorted(values))
    expected = base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, signature)


async def _require_twilio_http(request: Request, form: dict[str, str]) -> None:
    settings = get_settings()
    url = _canonical_url(settings, request.url.path, request.url.query)
    if not _is_valid_signature(
        settings.twilio_auth_token, url, form, request.headers.get("x-twilio-signature")
    ):
        raise HTTPException(status_code=403, detail="Invalid Twilio webhook signature")


def _gather_twiml(conversation_id: str, prompt: str) -> str:
    settings = get_settings()
    action = _canonical_url(settings, f"/api/v1/voice/webhooks/gather/{conversation_id}")
    escaped = escape(prompt)
    return (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="speech dtmf" action="{escape(action)}" method="POST" '
        'speechTimeout="auto" timeout="8" actionOnEmptyResult="true" '
        'language="en-IN" speechModel="googlev2_telephony" '
        'hints="supplier,quotation,authorize,authorise,inventory,replenishment">'
        f"<Say>{escaped}</Say></Gather>"
        "<Say>I did not receive a decision. No supplier will be contacted. Goodbye.</Say>"
        "</Response>"
    )


def _say_twiml(message: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><Response><Say>{escape(message)}</Say></Response>'
    )


@router.post("/owner/{conversation_id}")
async def owner_call_twiml(conversation_id: str, request: Request):
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    await _require_twilio_http(request, form)
    async with SessionFactory() as session:
        conversation = await session.get(VoiceConversation, conversation_id)
        if conversation is None or conversation.workflow != "owner_shortage_authorization":
            raise HTTPException(status_code=404, detail="Voice conversation not found")
        call_sid = form.get("CallSid")
        if call_sid:
            if conversation.provider_call_sid and conversation.provider_call_sid != call_sid:
                raise HTTPException(status_code=409, detail="Call does not match conversation")
            conversation.provider_call_sid = call_sid
            await session.commit()
        prompt = ProvisionVoiceService.owner_opening_prompt(conversation.shortage_snapshot)
    return Response(_gather_twiml(conversation_id, prompt), media_type="application/xml")


@router.post("/gather/{conversation_id}")
async def owner_call_gather(conversation_id: str, request: Request):
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    await _require_twilio_http(request, form)
    async with SessionFactory() as session:
        conversation = await session.get(VoiceConversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Voice conversation not found")
        call_sid = form.get("CallSid")
        if conversation.provider_call_sid and call_sid != conversation.provider_call_sid:
            raise HTTPException(status_code=409, detail="Call does not match conversation")
        if not conversation.provider_call_sid and call_sid:
            conversation.provider_call_sid = call_sid
        _, response = await ProvisionVoiceService(session).record_owner_response(
            conversation.id,
            conversation.business_id,
            form.get("SpeechResult", ""),
            form.get("Digits"),
        )
        await session.commit()
    return Response(_say_twiml(response), media_type="application/xml")


@router.post("/status/{conversation_id}")
async def owner_call_status(conversation_id: str, request: Request):
    form = {key: value for key, value in (await request.form()).items() if isinstance(value, str)}
    await _require_twilio_http(request, form)
    async with SessionFactory() as session:
        conversation = await session.get(VoiceConversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Voice conversation not found")
        call_sid, call_status = form.get("CallSid"), form.get("CallStatus", "unknown")
        if conversation.provider_call_sid and call_sid != conversation.provider_call_sid:
            raise HTTPException(status_code=409, detail="Call does not match conversation")
        if not conversation.provider_call_sid and call_sid:
            conversation.provider_call_sid = call_sid
        if call_status in {"busy", "failed", "no-answer", "canceled"}:
            conversation.status = "call_failed"
            conversation.last_error = f"Twilio call status: {call_status}"
            conversation.completed_at = datetime.now(UTC)
        elif call_status == "completed" and conversation.status == "awaiting_owner_authorization":
            conversation.status = "call_completed_without_decision"
            conversation.completed_at = datetime.now(UTC)
        await session.commit()
    return Response(status_code=204)


@router.websocket("/relay/{conversation_id}")
async def conversation_relay(websocket: WebSocket, conversation_id: str):
    """Optional ConversationRelay endpoint; requires public WSS and Twilio entitlement."""
    settings = get_settings()
    try:
        url = _canonical_url(settings, websocket.url.path, websocket.url.query, websocket=True)
    except HTTPException:
        await websocket.close(code=1013)
        return
    if not _is_valid_signature(
        settings.twilio_auth_token, url, {}, websocket.headers.get("x-twilio-signature")
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        async with SessionFactory() as session:
            conversation = await session.get(VoiceConversation, conversation_id)
            if conversation is None:
                await websocket.close(code=1008)
                return
            prompt = ProvisionVoiceService.owner_opening_prompt(conversation.shortage_snapshot)
        await websocket.send_json(
            {"type": "text", "token": prompt, "last": True, "interruptible": True}
        )
        while True:
            message = await websocket.receive_json()
            if message.get("type") not in {"prompt", "dtmf"}:
                continue
            transcript = (
                str(message.get("voicePrompt", "")) if message.get("type") == "prompt" else ""
            )
            digits = str(message.get("digit", "")) if message.get("type") == "dtmf" else None
            if message.get("type") == "prompt" and not message.get("last", False):
                continue
            async with SessionFactory() as session:
                conversation = await session.get(VoiceConversation, conversation_id)
                if conversation is None:
                    await websocket.close(code=1008)
                    return
                _, response = await ProvisionVoiceService(session).record_owner_response(
                    conversation.id, conversation.business_id, transcript, digits
                )
                await session.commit()
            await websocket.send_json(
                {"type": "text", "token": response, "last": True, "interruptible": True}
            )
    except WebSocketDisconnect:
        return
