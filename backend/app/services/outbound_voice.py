"""Twilio Programmable Voice adapter. Calls contain a short spoken stock alert."""

import asyncio
import base64
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from xml.sax.saxutils import escape

from app.core.config import get_settings

logger = logging.getLogger("morrow.voice.calls")


def _twilio_request(method: str, path: str, form: dict[str, str] | None = None) -> dict:
    settings = get_settings()
    if not settings.outbound_voice_configured:
        raise RuntimeError("Outbound voice provider is not configured")
    sid = settings.twilio_account_sid
    token = settings.twilio_auth_token
    assert sid and token
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/{path}"
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    body = urlencode(form).encode() if form is not None else None
    request = Request(
        url,
        data=body,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:1000]
        logger.warning("Twilio API returned HTTP %s: %s", exc.code, detail)
        raise RuntimeError(f"Voice provider rejected the call (HTTP {exc.code})") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError("Voice provider request failed or timed out") from exc


async def start_call(phone: str, spoken_message: str) -> dict:
    settings = get_settings()
    if settings.voice_test_mode:
        logger.info("simulated voice call", extra={"recipient_phone": phone})
        return {"sid": f"TEST-{uuid4()}"}
    if not settings.twilio_from_number:
        raise RuntimeError("Outbound caller ID is not configured")
    escaped_message = escape(spoken_message)
    twiml = (
        f'<Response><Say>{escaped_message}</Say><Pause length="1"/>'
        f"<Say>{escaped_message}</Say></Response>"
    )
    return await asyncio.to_thread(
        _twilio_request,
        "POST",
        "Calls.json",
        {"To": phone, "From": settings.twilio_from_number, "Twiml": twiml},
    )


async def start_conversation_call(phone: str, answer_url: str, status_url: str) -> dict:
    """Start a call whose spoken input is handled by signed application webhooks."""
    settings = get_settings()
    if settings.voice_test_mode:
        logger.info("simulated provision conversation call", extra={"recipient_phone": phone})
        return {"sid": f"TEST-{uuid4()}"}
    if not settings.outbound_voice_configured:
        raise RuntimeError("Live outbound voice is not configured")
    return await asyncio.to_thread(
        _twilio_request,
        "POST",
        "Calls.json",
        {
            "To": phone,
            "From": settings.twilio_from_number or "",
            "Url": answer_url,
            "Method": "POST",
            "StatusCallback": status_url,
            "StatusCallbackMethod": "POST",
        },
    )


async def get_call(call_sid: str) -> dict:
    if call_sid.startswith("TEST-"):
        return {"sid": call_sid, "status": "completed"}
    return await asyncio.to_thread(_twilio_request, "GET", f"Calls/{call_sid}.json")
