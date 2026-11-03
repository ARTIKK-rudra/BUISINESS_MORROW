from app.core.config import Settings
from app.services.gemini_voice import GeminiVoiceService


def test_gemini_voice_is_disabled_without_a_server_key():
    service = GeminiVoiceService(Settings(gemini_api_key=None))
    assert service.settings.gemini_configured is False


def test_gemini_voice_rejects_new_or_changed_numeric_facts():
    verified = "Rice: 18 kg. Quoted total: 12.50 USD."
    assert GeminiVoiceService._preserves_numeric_facts(
        verified, "Rice is 18 kg and the quoted total is 12.50 USD."
    )
    assert not GeminiVoiceService._preserves_numeric_facts(
        verified, "Rice is 20 kg and the quoted total is 12.50 USD."
    )
    assert not GeminiVoiceService._preserves_numeric_facts(
        verified, "Rice is 18 kg and delivery takes 2 days."
    )


async def test_gemini_failure_preserves_the_verified_voice_answer(monkeypatch):
    service = GeminiVoiceService(Settings(gemini_api_key="test-key"))

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(service, "_generate", unavailable)
    verified = "No completed sales are recorded for 2026-11-01."
    assert await service.spoken_answer("Show today's sales", verified) == verified


async def test_voice_answers_preserve_the_actual_unsupported_question(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Voice Question Owner",
            "email": "voice-question@example.com",
            "password": "a-secure-test-password",
        },
    )
    response = await client.post(
        "/api/v1/voice/ask",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
        json={"question": "Which staff member opens the restaurant?"},
    )
    assert response.status_code == 200
    assert "Which staff member opens the restaurant?" in response.json()["answer"]
    assert response.json()["intent"] == "unsupported"


async def test_gemini_audio_transcription_endpoint_is_explicitly_unavailable_without_key(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Voice Audio Owner",
            "email": "voice-audio@example.com",
            "password": "a-secure-test-password",
        },
    )
    response = await client.post(
        "/api/v1/voice/transcribe",
        headers={"Authorization": f"Bearer {registration.json()['access_token']}"},
        files={"audio": ("question.webm", b"test-audio", "audio/webm")},
    )
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_configured"


async def test_opted_in_voice_transcript_retains_only_a_safe_session_identifier(client):
    from sqlalchemy import select
    from app.db.models import VoiceInteraction

    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Voice Session Owner",
            "email": "voice-session@example.com",
            "password": "a-secure-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    response = await client.post(
        "/api/v1/voice/ask",
        headers=headers,
        json={
            "question": "What is this website?",
            "consent_to_store_transcript": True,
            "conversation_session": "browser-session-01",
        },
    )
    assert response.status_code == 200
    async with client.session_factory() as session:
        interaction = await session.scalar(select(VoiceInteraction))
    assert interaction is not None
    assert interaction.provider_session == "browser-session-01"


async def test_owner_can_manage_consent_based_indian_voice_contacts(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Voice Owner",
            "email": "voice-owner@example.com",
            "password": "a-secure-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    response = await client.post(
        "/api/v1/voice/contacts",
        headers=headers,
        json={
            "full_name": "Inventory Manager",
            "role": "manager",
            "phone": "+919666265238",
            "calling_consent": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["phone"] == "+919666265238"
    assert response.json()["calling_consent"] is True
    assert response.json()["consent_recorded_at"] is not None

    duplicate = await client.post(
        "/api/v1/voice/contacts",
        headers=headers,
        json={
            "full_name": "Duplicate",
            "role": "manager",
            "phone": "+919666265238",
        },
    )
    assert duplicate.status_code == 409

    invalid_phone = await client.post(
        "/api/v1/voice/contacts",
        headers=headers,
        json={
            "full_name": "Wrong format",
            "role": "supplier",
            "phone": "+12025550123",
        },
    )
    assert invalid_phone.status_code == 422


async def test_voice_test_mode_never_uses_a_telephony_provider(monkeypatch):
    from app.services import outbound_voice

    monkeypatch.setattr(
        outbound_voice,
        "get_settings",
        lambda: Settings(voice_test_mode=True, voice_live_calls_enabled=False),
    )
    result = await outbound_voice.start_call("+919666265238", "A test alert")
    assert result["sid"].startswith("TEST-")
    status = await outbound_voice.get_call(result["sid"])
    assert status["status"] == "completed"


async def test_mock_owner_call_records_explicit_supplier_contact_only(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Provision Owner",
            "email": "provision-owner@example.com",
            "password": "a-secure-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    product = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"sku": "RICE-01", "name": "Rice", "price": "10", "unit": "kg"},
    )
    assert product.status_code == 201
    inventory = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "product_id": product.json()["id"],
            "location": "Main",
            "reorder_point": "20",
            "minimum_stock": "20",
        },
    )
    assert inventory.status_code == 201
    contact = await client.post(
        "/api/v1/voice/contacts",
        headers=headers,
        json={
            "full_name": "Restaurant Owner",
            "role": "owner",
            "phone": "+918688310104",
            "calling_consent": True,
        },
    )
    assert contact.status_code == 201

    started = await client.post("/api/v1/voice/conversations/owner-shortage", headers=headers)
    assert started.status_code == 201
    opening = started.json()
    assert opening["status"] == "awaiting_owner_authorization"
    assert opening["shortage_snapshot"]["items"][0]["name"] == "Rice"
    assert "20" in opening["turns"][0]["transcript"]

    accepted = await client.post(
        f"/api/v1/voice/conversations/{opening['id']}/mock-response",
        headers=headers,
        json={"transcript": "Yes, you may contact suppliers for quotations."},
    )
    assert accepted.status_code == 200
    result = accepted.json()
    assert result["status"] == "supplier_contact_authorized"
    assert result["supplier_contact_authorized"] is True
    assert result["purchase_authorized"] is False
    assert "will not place an order" in result["agent_response"]
