from decimal import Decimal

import pytest

from app.core.errors import ConflictError, ForbiddenError
from app.core.security import hash_password, verify_password
from app.services.authorization import Permission, ensure_permission
from app.services.inventory import calculate_adjusted_quantity


def test_password_hash_is_one_way_and_verifiable():
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)


def test_role_permissions_reject_staff_financial_access():
    ensure_permission("staff", Permission.SALES_WRITE)
    with pytest.raises(ForbiddenError):
        ensure_permission("staff", Permission.FINANCE_READ)


def test_inventory_adjustment_prevents_negative_stock():
    assert calculate_adjusted_quantity(Decimal("2.500"), Decimal("-0.500")) == Decimal("2.000")
    with pytest.raises(ConflictError):
        calculate_adjusted_quantity(Decimal("1"), Decimal("-1.001"))


@pytest.mark.asyncio
async def test_registration_assigns_owner_and_inventory_adjustment_is_audited(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Avery Owner",
            "email": "avery@example.com",
            "password": "a-secure-test-password",
            "role": "staff",
        },
    )
    assert registration.status_code == 201
    auth = registration.json()
    assert auth["business_id"]
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    product_response = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "sku": "BEAN-01",
            "name": "House blend",
            "price": "12.50",
            "unit": "kg",
        },
    )
    assert product_response.status_code == 201
    product_id = product_response.json()["id"]
    inventory_response = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "product_id": product_id,
            "location": "Main",
            "reorder_point": "2",
        },
    )
    assert inventory_response.status_code == 201
    inventory_id = inventory_response.json()["id"]

    adjust_response = await client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        headers=headers,
        json={
            "quantity_delta": "3.250",
            "reason": "opening balance",
        },
    )
    assert adjust_response.status_code == 200
    assert adjust_response.json()["quantity"] == "3.250"

    forbidden_stock = await client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        headers=headers,
        json={
            "quantity_delta": "-4",
            "reason": "invalid reduction",
        },
    )
    assert forbidden_stock.status_code == 409

    movement_response = await client.get(
        f"/api/v1/inventory/{inventory_id}/movements", headers=headers
    )
    assert movement_response.status_code == 200
    assert len(movement_response.json()) == 1


@pytest.mark.asyncio
async def test_tenant_isolation_and_bearer_auth_required(client):
    users = []
    for name, email in [("Owner One", "one@example.com"), ("Owner Two", "two@example.com")]:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "name": name,
                "email": email,
                "password": "a-secure-test-password",
            },
        )
        assert response.status_code == 201
        users.append(response.json())
    own = await client.get(
        "/api/v1/products", headers={"Authorization": f"Bearer {users[0]['access_token']}"}
    )
    other = await client.get(
        "/api/v1/products", headers={"Authorization": f"Bearer {users[1]['access_token']}"}
    )
    assert own.status_code == other.status_code == 200
    assert own.json() == other.json() == []
    missing_token = await client.get("/api/v1/products")
    assert missing_token.status_code == 401


@pytest.mark.asyncio
async def test_order_uses_decimal_totals_and_idempotency(client):
    auth_response = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Order Owner",
            "email": "orders@example.com",
            "password": "a-secure-test-password",
        },
    )
    assert auth_response.status_code == 201
    headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
    product_response = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "sku": "TEA-01",
            "name": "Tea tin",
            "price": "7.35",
            "unit": "tin",
        },
    )
    product_id = product_response.json()["id"]
    inventory = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={"product_id": product_id, "location": "Main", "reorder_point": "1"},
    )
    assert inventory.status_code == 201
    await client.post(
        f"/api/v1/inventory/{inventory.json()['id']}/adjust",
        headers=headers,
        json={"quantity_delta": "5", "reason": "opening stock"},
    )
    order_payload = {
        "items": [{"product_id": product_id, "quantity": "2.500"}],
        "discount": "1.00",
        "currency": "USD",
        "idempotency_key": "order-test-1",
    }
    first = await client.post("/api/v1/orders", headers=headers, json=order_payload)
    retry = await client.post("/api/v1/orders", headers=headers, json=order_payload)
    assert first.status_code == retry.status_code == 201
    assert first.json()["id"] == retry.json()["id"]
    assert first.json()["subtotal"] == "18.38"
    assert first.json()["total"] == "17.38"
    assert first.json()["status"] == "completed"
    remaining = await client.get("/api/v1/inventory", headers=headers)
    assert remaining.json()[0]["quantity"] == "2.500"
    ledger = await client.get("/api/v1/ledger", headers=headers)
    assert len(ledger.json()) == 2
    assert {line["account"] for line in ledger.json()} == {"Cash", "Sales Revenue"}
