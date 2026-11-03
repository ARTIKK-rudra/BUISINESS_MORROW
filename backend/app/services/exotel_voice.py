"""Minimal Exotel Connect Voice AI adapter, disabled unless explicitly configured.

The adapter is intentionally not attached to automated stock alerts.  It exists
to make a later, owner-authorized Indian telephone pilot auditable without
changing the established browser or Twilio paths.
"""

import asyncio
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.config import Settings, get_settings


class ExotelVoiceError(RuntimeError):
    """A safe, provider-neutral error suitable for a persisted call failure."""


def _base_url(settings: Settings) -> str:
    region = settings.exotel_region.strip().lower()
    if region in {"in", "india", "mumbai"}:
        return "https://api.in.exotel.com"
    if region in {"sg", "singapore"}:
        return "https://api.exotel.com"
    raise ExotelVoiceError("Exotel region must be India/Mumbai or Singapore")


def _request(
    settings: Settings, method: str, path: str, form: dict[str, str] | None = None
) -> dict:
    if not settings.exotel_configured:
        raise ExotelVoiceError("Exotel outbound voice is not configured or is disabled")
    assert settings.exotel_api_key and settings.exotel_api_token
    authorization = base64.b64encode(
        f"{settings.exotel_api_key}:{settings.exotel_api_token}".encode()
    ).decode()
    request = Request(
        f"{_base_url(settings)}{path}",
        data=urlencode(form).encode() if form is not None else None,
        headers={
            "Authorization": f"Basic {authorization}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise ExotelVoiceError(f"Exotel rejected the request (HTTP {exc.code})") from exc
    except TimeoutError as exc:
        raise ExotelVoiceError("Exotel request transport failure (TimeoutError)") from exc
    except URLError as exc:
        reason_type = type(exc.reason).__name__
        raise ExotelVoiceError(
            f"Exotel request transport failure (URLError:{reason_type})"
        ) from exc


async def start_connect_voice_ai(
    phone: str,
    stream_url: str,
    status_callback_url: str,
    *,
    custom_field: str,
    settings: Settings | None = None,
) -> dict:
    """Request one outbound bot-only call after higher layers authorize it.

    Exotel Connect Voice AI opens the configured WSS stream after the recipient
    answers. The calling workflow must separately verify consent and owner scope.
    """
    active_settings = settings or get_settings()
    if active_settings.voice_test_mode:
        return {"sid": f"TEST-EXOTEL-{uuid4()}", "status": "completed", "simulated": True}
    if not stream_url.startswith("wss://") or not status_callback_url.startswith("https://"):
        raise ExotelVoiceError("Exotel live calls require public WSS and HTTPS callback URLs")
    assert active_settings.exotel_account_sid and active_settings.exotel_exophone
    payload = {
        "From": phone,
        "CallerId": active_settings.exotel_exophone,
        "StreamUrl": stream_url,
        "StreamType": "bidirectional",
        "StatusCallback": status_callback_url,
        "StatusCallbackEvents[]": "terminal",
        "CustomField": custom_field[:128],
    }
    response = await asyncio.to_thread(
        _request,
        active_settings,
        "POST",
        f"/v1/Accounts/{active_settings.exotel_account_sid}/Calls/connect",
        payload,
    )
    call = response.get("Call") or response
    sid = call.get("Sid") or call.get("sid")
    if not sid:
        raise ExotelVoiceError("Exotel response did not include a call identifier")
    return {"sid": str(sid), "status": str(call.get("Status", "queued")).lower()}


async def get_call(call_sid: str, *, settings: Settings | None = None) -> dict:
    """Read a call's status; this endpoint never initiates a call."""
    if call_sid.startswith("TEST-EXOTEL-"):
        return {"sid": call_sid, "status": "completed", "simulated": True}
    active_settings = settings or get_settings()
    if not active_settings.exotel_configured:
        raise ExotelVoiceError("Exotel call status is unavailable because Exotel is disabled")
    assert active_settings.exotel_account_sid
    response = await asyncio.to_thread(
        _request,
        active_settings,
        "GET",
        f"/v1/Accounts/{active_settings.exotel_account_sid}/Calls/{call_sid}",
    )
    call = response.get("Call") or response
    return {
        "sid": str(call.get("Sid", call_sid)),
        "status": str(call.get("Status", "unknown")).lower(),
    }


async def get_account_balance(*, settings: Settings | None = None) -> dict:
    """Validate credentials through Exotel's documented read-only balance API.

    This operation cannot dial, charge, or change provider-account state. The
    caller should log only the returned response shape/status, not balance data
    or credentials, because billing information is sensitive.
    """
    active_settings = settings or get_settings()
    if not active_settings.exotel_account_sid:
        raise ExotelVoiceError("Exotel Account SID is not configured")
    # Read-only validation must work while voice test mode remains enabled, so
    # it deliberately requires credentials but not `exotel_configured`.
    if not active_settings.exotel_api_key or not active_settings.exotel_api_token:
        raise ExotelVoiceError("Exotel API credentials are not configured")
    response = await asyncio.to_thread(
        _read_only_request,
        active_settings,
        f"/v1/Accounts/{active_settings.exotel_account_sid}/Balance.json",
    )
    balance = response.get("Balance") or response
    return {"authenticated": True, "response_fields": sorted(str(key) for key in balance)}


async def inspect_recent_calls(*, settings: Settings | None = None) -> dict:
    """Use Exotel's documented bulk-call GET as a non-billable permission check.

    The result intentionally exposes only count and response keys, not telephone
    numbers, recordings, prices, or call transcripts. It is suitable for a
    configuration diagnostic but never for triggering a conversation.
    """
    active_settings = settings or get_settings()
    if not active_settings.exotel_account_sid:
        raise ExotelVoiceError("Exotel Account SID is not configured")
    if not active_settings.exotel_api_key or not active_settings.exotel_api_token:
        raise ExotelVoiceError("Exotel API credentials are not configured")
    response = await asyncio.to_thread(
        _read_only_request,
        active_settings,
        f"/v1/Accounts/{active_settings.exotel_account_sid}/Calls.json?PageSize=1",
    )
    calls = response.get("Calls", [])
    if not isinstance(calls, list):
        raise ExotelVoiceError("Exotel returned an unexpected bulk-call response")
    return {
        "authenticated": True,
        "call_records_accessible": True,
        "returned_count": len(calls),
        "response_fields": sorted(str(key) for key in response),
    }


def _read_only_request(settings: Settings, path: str) -> dict:
    """Execute a credentialed GET without requiring live-dial configuration."""
    assert settings.exotel_api_key and settings.exotel_api_token
    authorization = base64.b64encode(
        f"{settings.exotel_api_key}:{settings.exotel_api_token}".encode()
    ).decode()
    request = Request(
        f"{_base_url(settings)}{path}",
        headers={"Authorization": f"Basic {authorization}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        raise ExotelVoiceError(
            f"Exotel authentication/read-only request failed (HTTP {exc.code})"
        ) from exc
    except TimeoutError as exc:
        raise ExotelVoiceError("Exotel read-only transport failure (TimeoutError)") from exc
    except URLError as exc:
        reason_type = type(exc.reason).__name__
        raise ExotelVoiceError(
            f"Exotel read-only transport failure (URLError:{reason_type})"
        ) from exc
