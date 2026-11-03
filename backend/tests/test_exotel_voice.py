from urllib.error import URLError

import pytest

from app.core.config import Settings
from app.services import exotel_voice


@pytest.mark.asyncio
async def test_exotel_test_mode_is_simulated_and_never_requests_network(monkeypatch):
    def forbidden_request(*_args, **_kwargs):
        raise AssertionError("network must not be used in VOICE_TEST_MODE")

    monkeypatch.setattr(exotel_voice, "_request", forbidden_request)
    result = await exotel_voice.start_connect_voice_ai(
        "+919666265238",
        "wss://example.test/voice",
        "https://example.test/status",
        custom_field="provision-case",
        settings=Settings(voice_test_mode=True, voice_live_calls_enabled=False),
    )
    assert result["simulated"] is True
    assert result["sid"].startswith("TEST-EXOTEL-")
    status = await exotel_voice.get_call(result["sid"])
    assert status["status"] == "completed"


@pytest.mark.asyncio
async def test_exotel_connect_uses_india_connect_voice_endpoint(monkeypatch):
    seen: dict[str, object] = {}

    def mocked_request(settings, method, path, form):
        seen.update({"settings": settings, "method": method, "path": path, "form": form})
        return {"Call": {"Sid": "exo-call-1", "Status": "in-progress"}}

    monkeypatch.setattr(exotel_voice, "_request", mocked_request)
    settings = Settings(
        voice_test_mode=False,
        voice_live_calls_enabled=True,
        exotel_account_sid="account",
        exotel_api_key="key",
        exotel_api_token="token",
        exotel_exophone="08000000000",
        exotel_region="singapore",
    )
    result = await exotel_voice.start_connect_voice_ai(
        "+919666265238",
        "wss://voice.example.test/media",
        "https://voice.example.test/callback",
        custom_field="a" * 200,
        settings=settings,
    )
    assert result == {"sid": "exo-call-1", "status": "in-progress"}
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/Accounts/account/Calls/connect"
    form = seen["form"]
    assert isinstance(form, dict)
    assert form["From"] == "+919666265238"
    assert form["StreamType"] == "bidirectional"
    assert form["CustomField"] == "a" * 128


@pytest.mark.asyncio
async def test_exotel_refuses_non_public_callback_urls_before_request(monkeypatch):
    monkeypatch.setattr(exotel_voice, "_request", lambda *_args: pytest.fail("should not request"))
    settings = Settings(
        voice_test_mode=False,
        voice_live_calls_enabled=True,
        exotel_account_sid="account",
        exotel_api_key="key",
        exotel_api_token="token",
        exotel_exophone="08000000000",
    )
    with pytest.raises(exotel_voice.ExotelVoiceError, match="public WSS and HTTPS"):
        await exotel_voice.start_connect_voice_ai(
            "+919666265238",
            "ws://localhost:8000/media",
            "http://localhost:8000/status",
            custom_field="case",
            settings=settings,
        )


@pytest.mark.asyncio
async def test_exotel_balance_validation_is_read_only_and_available_in_test_mode(monkeypatch):
    seen: dict[str, object] = {}

    def mocked_read_only(settings, path):
        seen.update({"settings": settings, "path": path})
        return {"Balance": {"Amount": "10", "Currency": "INR"}}

    monkeypatch.setattr(exotel_voice, "_read_only_request", mocked_read_only)
    result = await exotel_voice.get_account_balance(
        settings=Settings(
            voice_test_mode=True,
            exotel_account_sid="account",
            exotel_api_key="key",
            exotel_api_token="token",
            exotel_region="singapore",
        )
    )
    assert result == {"authenticated": True, "response_fields": ["Amount", "Currency"]}
    assert seen["path"] == "/v1/Accounts/account/Balance.json"


@pytest.mark.asyncio
async def test_exotel_bulk_call_permission_check_is_read_only(monkeypatch):
    seen: dict[str, object] = {}

    def mocked_read_only(settings, path):
        seen.update({"settings": settings, "path": path})
        return {"Metadata": {"Total": 1}, "Calls": [{"Sid": "sensitive-call-id"}]}

    monkeypatch.setattr(exotel_voice, "_read_only_request", mocked_read_only)
    result = await exotel_voice.inspect_recent_calls(
        settings=Settings(
            voice_test_mode=True,
            exotel_account_sid="account",
            exotel_api_key="key",
            exotel_api_token="token",
        )
    )
    assert result == {
        "authenticated": True,
        "call_records_accessible": True,
        "returned_count": 1,
        "response_fields": ["Calls", "Metadata"],
    }
    assert seen["path"] == "/v1/Accounts/account/Calls.json?PageSize=1"


def test_exotel_sanitizes_transport_error_type(monkeypatch):
    def transport_failure(*_args, **_kwargs):
        raise URLError(ConnectionRefusedError("details must not be exposed"))

    monkeypatch.setattr(exotel_voice, "urlopen", transport_failure)
    settings = Settings(
        exotel_account_sid="account",
        exotel_api_key="key",
        exotel_api_token="token",
    )
    with pytest.raises(
        exotel_voice.ExotelVoiceError,
        match=r"URLError:ConnectionRefusedError",
    ):
        exotel_voice._read_only_request(settings, "/v1/Accounts/account/Calls.json?PageSize=1")
