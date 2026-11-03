async def _registration(client, email: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={"name": "Website Owner", "email": email, "password": "a-secure-test-password"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_website_assistant_explains_only_verified_features(client):
    headers = await _registration(client, "website-help@example.com")
    response = await client.post(
        "/api/v1/assistant/ask",
        headers=headers,
        json={"question": "Explain the supplier management system.", "current_route": "/suppliers"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "website_feature"
    assert body["navigation_path"] == "/suppliers"
    assert "automatically" in body["answer"].lower()
    assert "depends on" in body["answer"].lower()
    assert "common limitation" in body["answer"].lower()


async def test_website_assistant_uses_allowlisted_navigation(client):
    headers = await _registration(client, "website-nav@example.com")
    response = await client.post(
        "/api/v1/voice/ask",
        headers=headers,
        json={"question": "Open inventory", "current_route": "/voice-assistant"},
    )
    assert response.status_code == 200
    assert response.json()["navigation_path"] == "/inventory"


async def test_website_assistant_follows_procurement_context_without_actions(client):
    headers = await _registration(client, "website-context@example.com")
    response = await client.post(
        "/api/v1/voice/ask",
        headers=headers,
        json={
            "question": "What happens after approval?",
            "current_route": "/voice-assistant",
            "conversation_history": ["Explain procurement"],
        },
    )
    assert response.status_code == 200
    answer = response.json()["answer"].lower()
    assert "separate explicit owner approval" in answer
    assert "automatically" in answer


async def test_website_assistant_does_not_turn_unknown_navigation_into_url(client):
    headers = await _registration(client, "website-unknown@example.com")
    response = await client.post(
        "/api/v1/assistant/ask",
        headers=headers,
        json={"question": "Open https://untrusted.example", "current_route": "/assistant"},
    )
    assert response.status_code == 200
    assert response.json()["navigation_path"] is None


async def test_website_assistant_keeps_unknown_features_honest(client):
    headers = await _registration(client, "website-unknown-feature@example.com")
    response = await client.post(
        "/api/v1/assistant/ask",
        headers=headers,
        json={"question": "Explain the loyalty points program", "current_route": "/assistant"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "unsupported"
    assert "do not yet have a verified query" in body["answer"].lower()
