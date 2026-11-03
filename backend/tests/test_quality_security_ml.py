from datetime import date, timedelta
from io import BytesIO
from math import sin
from time import perf_counter
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.errors import ConflictError, UnauthorizedError
from app.core.rate_limit import InMemoryRateLimitMiddleware
from app.core.security import ALGORITHM, create_access_token, decode_access_token
from app.db.models import Business, BusinessMembership
from app.ml.demand import (
    evaluate_and_fit,
    make_features,
    metric_set,
    predict_horizon,
    supervised,
)
from app.services.forecasting import stockout_probability
from app.services.ocr import MAX_IMAGE_BYTES, OCRService, extract_fields


def test_access_tokens_reject_tampered_expired_and_wrong_type_claims(monkeypatch):
    settings = get_settings()
    token = create_access_token(uuid4(), uuid4())
    assert decode_access_token(token)[0]
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(UnauthorizedError):
        decode_access_token(tampered)
    expired = jwt.encode(
        {"sub": str(uuid4()), "business_id": str(uuid4()), "type": "access", "exp": 1},
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(expired)
    wrong_type = jwt.encode(
        {
            "sub": str(uuid4()),
            "business_id": str(uuid4()),
            "type": "refresh",
            "exp": 4_000_000_000,
        },
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(wrong_type)


@pytest.mark.parametrize(
    "secret",
    [
        "dev-only-change-this-secret-key-before-deploying",
        "replace-with-a-random-secret-at-least-32-characters-long",
    ],
)
def test_production_rejects_development_or_example_secrets(secret):
    with pytest.raises(ValueError):
        Settings(app_env="production", secret_key=secret, _env_file=None)


def test_production_cors_requires_explicit_https_origins():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            secret_key="a-production-secret-with-enough-random-length-123456",
            cors_origins="http://localhost:3000",
            _env_file=None,
        )


def test_production_cors_rejects_non_origin_urls():
    with pytest.raises(ValueError):
        Settings(
            app_env="production",
            secret_key="a-production-secret-with-enough-random-length-123456",
            cors_origins="https://example.com/path",
            _env_file=None,
        )


@pytest.mark.asyncio
async def test_role_protected_routes_and_validation_errors_are_enforced(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Security Owner",
            "email": "security@example.com",
            "password": "secure-quality-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    invalid = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"sku": "", "name": "", "price": "-1", "unit": "kg"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.headers.get("x-request-id")
    assert invalid.headers.get("x-content-type-options") == "nosniff"
    assert invalid.headers.get("x-frame-options") == "DENY"
    assert invalid.headers.get("referrer-policy") == "no-referrer"
    voice_without_auth = await client.post(
        "/api/v1/voice/ask", json={"question": "Show today's sales."}
    )
    assert voice_without_auth.status_code == 401


@pytest.mark.asyncio
async def test_staff_cannot_read_or_write_financial_records_or_approve_purchases(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Role Owner",
            "email": "role-owner@example.com",
            "password": "secure-quality-test-password",
        },
    )
    body = registration.json()
    async with client.session_factory() as session:
        membership = await session.scalar(
            select(BusinessMembership).where(
                BusinessMembership.business_id == UUID(body["business_id"])
            )
        )
        membership.role = "staff"
        await session.commit()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert (await client.get("/api/v1/ledger", headers=headers)).status_code == 403
    assert (
        await client.post(
            "/api/v1/expenses",
            headers=headers,
            json={"category": "utilities", "description": "bill", "amount": "1.00"},
        )
    ).status_code == 403
    denied = await client.post(
        f"/api/v1/recommendations/{uuid4()}/approve",
        headers=headers,
        json={
            "supplier_product_id": str(uuid4()),
            "quantity": "1",
            "unit_cost": "1.00",
        },
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_inventory_object_ids_cannot_cross_business_boundaries(client):
    first = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Tenant A",
            "email": "tenant-a-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    first_headers = {"Authorization": f"Bearer {first.json()['access_token']}"}
    product = await client.post(
        "/api/v1/products",
        headers=first_headers,
        json={"sku": "TENANT-A", "name": "Tenant A item", "price": "1.00", "unit": "each"},
    )
    stock = await client.post(
        "/api/v1/inventory",
        headers=first_headers,
        json={"product_id": product.json()["id"]},
    )
    second = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Tenant B",
            "email": "tenant-b-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    second_headers = {"Authorization": f"Bearer {second.json()['access_token']}"}
    assert (await client.get("/api/v1/inventory", headers=second_headers)).json() == []
    cross_tenant = await client.get(
        f"/api/v1/inventory/{stock.json()['id']}/movements", headers=second_headers
    )
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_inactive_business_memberships_stop_authentication(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Disabled Business Owner",
            "email": "disabled-business@example.com",
            "password": "secure-quality-test-password",
        },
    )
    auth = registration.json()
    async with client.session_factory() as session:
        business = await session.get(Business, UUID(auth["business_id"]))
        business.is_active = False
        await session.commit()
    response = await client.get(
        "/api/v1/ledger",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_rate_limit_is_bounded_per_client_not_per_untrusted_path(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "app.core.rate_limit.get_settings",
        lambda: SimpleNamespace(
            rate_limit_per_minute=2,
            auth_rate_limit_per_minute=2,
            expensive_rate_limit_per_minute=1,
        ),
    )
    probe = FastAPI()

    @probe.get("/{path:path}")
    async def echo(path: str):
        return {"path": path}

    limiter = InMemoryRateLimitMiddleware(probe)
    async with AsyncClient(transport=ASGITransport(app=limiter), base_url="http://limits") as http:
        assert (await http.get("/random-id-one")).status_code == 200
        assert (await http.get("/random-id-two")).status_code == 200
        assert (await http.get("/random-id-three")).status_code == 429
        assert (await http.get("/voice/first")).status_code == 200
        assert (await http.get("/voice/second")).status_code == 429
    assert len(limiter._requests) == 2


@pytest.mark.asyncio
async def test_voice_transcript_is_stored_only_after_explicit_consent(client):
    from sqlalchemy import select

    from app.db.models import VoiceInteraction

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Voice Owner",
            "email": "voice-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    for consent in (False, True):
        answer = await client.post(
            "/api/v1/voice/ask",
            headers=headers,
            json={"question": "Show today's sales.", "consent_to_store_transcript": consent},
        )
        assert answer.status_code == 200
        assert answer.json()["grounded"] is True
    async with client.session_factory() as session:
        rows = list((await session.scalars(select(VoiceInteraction))).all())
    assert len(rows) == 1
    assert rows[0].consent_recorded is True


@pytest.mark.asyncio
async def test_ocr_upload_rejects_mismatched_image_media_type(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "OCR Owner",
            "email": "ocr-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    response = await client.post(
        "/api/v1/invoices/ocr-captures",
        headers=headers,
        files={"file": ("mislabelled.jpg", buffer.getvalue(), "image/jpeg")},
    )
    assert response.status_code == 409
    assert "does not match" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_ocr_size_limit_and_engine_timeout_fail_closed(monkeypatch):
    service = OCRService(None)
    with pytest.raises(ConflictError, match="smaller than 10 MB"):
        await service.capture(
            uuid4(), uuid4(), "large.png", "image/png", b"x" * (MAX_IMAGE_BYTES + 1)
        )

    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")

    def timeout(*_args, **_kwargs):
        raise RuntimeError("synthetic timeout")

    monkeypatch.setattr("app.services.ocr.pytesseract.image_to_string", timeout)
    with pytest.raises(ConflictError, match="time limit"):
        await service.capture(uuid4(), uuid4(), "invoice.png", "image/png", buffer.getvalue())


def test_ml_supervised_features_do_not_include_the_target_or_future_rows():
    values = [float(index) for index in range(80)]
    features, targets, days = supervised(values, date(2025, 1, 1))
    assert targets[0] == values[28]
    assert features[0][0] == values[27]
    assert features[0][1] == values[21]
    assert features[0][4] == pytest.approx(sum(values[:28]) / 28)
    assert days[0] == date(2025, 1, 29)
    changed_future = values[:28] + [9999.0] + values[29:]
    changed_features, _, _ = supervised(changed_future, date(2025, 1, 1))
    assert features[0].tolist() == changed_features[0].tolist()


def test_ml_temporal_holdout_baselines_metrics_and_reproducibility():
    start = date(2024, 1, 1)
    values = [
        10 + (index % 7 == 5) * 8 + 0.02 * index + 2 * sin(index / 17) for index in range(240)
    ]
    training_started = perf_counter()
    first = evaluate_and_fit(values, start)
    training_ms = (perf_counter() - training_started) * 1000
    second = evaluate_and_fit(values, start)
    assert first["status"] == "ready"
    assert {row["model"] for row in first["evaluations"]} >= {
        "naive_last_observation",
        "seasonal_naive_7_day",
        "random_forest_lag_features",
    }
    assert first["holdout_start"] == second["holdout_start"]
    assert first["evaluations"] == second["evaluations"]
    assert first["selected_model"] == second["selected_model"]
    selected = min(
        (row for row in first["evaluations"] if row["model"] == first["selected_model"]),
        key=lambda row: row["smape"],
    )
    assert first["bundle"].metrics == {
        key: selected[key]
        for key in ("mae", "rmse", "smape", "mape_nonzero_actual_pct")
        if key in selected
    }
    inference_started = perf_counter()
    horizon = predict_horizon(first["bundle"], values, start, 3, first["selected_model"])
    inference_ms = (perf_counter() - inference_started) * 1000
    assert len(horizon) == 3
    assert horizon[0]["day"] == start + timedelta(days=len(values))
    assert all(row["point"] >= 0 for row in horizon)
    holdout_day = date.fromisoformat(first["holdout_start"])
    assert holdout_day > start + timedelta(days=28)
    print(
        f"PERF ML train/evaluate: {training_ms:.2f} ms; "
        f"3-step inference: {inference_ms:.2f} ms (local CPU)"
    )


def test_ml_zero_values_insufficient_data_and_forecast_horizon_edges():
    assert "mape_nonzero_actual_pct" not in metric_set([0, 0], [0, 0])
    insufficient = evaluate_and_fit([0.0] * 60, date(2025, 1, 1))
    assert insufficient["status"] == "insufficient_data"
    assert stockout_probability(5, 0, 0) == 0
    assert stockout_probability(0, 0, 0) == 1
    bundle = insufficient["bundle"]
    assert bundle is None
    with pytest.raises(ValueError):
        make_features([1, 2], date(2025, 1, 1))


def test_ocr_extraction_never_marks_data_ready_to_commit():
    draft, confidence = extract_fields(
        "Northwind Supply\nInvoice No: INV-1234\n2025-02-03\nSubtotal: $10.00\n"
        "Tax: $1.00\nTotal: $11.00\nTea 1 $10.00"
    )
    assert confidence == draft["field_confidence"]
    assert draft["needs_manual_review"] is True


def test_security_rejects_bad_tokens_with_no_sensitive_exception_text():
    with pytest.raises(UnauthorizedError) as error:
        decode_access_token("not-a-jwt")
    assert str(error.value) == "Invalid or expired access token"
