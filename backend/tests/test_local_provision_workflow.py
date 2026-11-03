from sqlalchemy import select

from app.db.models import AuditLog, Purchase, VoiceConversationTurn


async def test_local_provision_workflow_records_auditable_purchase_without_calls(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Local Owner",
            "email": "local-provision@example.com",
            "password": "a-secure-test-password",
            "business_name": "Provision workflow test",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    contacts = []
    for name, role, phone in [
        ("Owner", "owner", "+918688310104"),
        ("Anji", "manager", "+919666265238"),
        ("Srinivas", "manager", "+917815914916"),
        ("Shiva", "supplier", "+917842583258"),
    ]:
        response = await client.post(
            "/api/v1/voice/contacts",
            headers=headers,
            json={"full_name": name, "role": role, "phone": phone, "calling_consent": False},
        )
        assert response.status_code == 201
        contacts.append(response.json())

    product = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"sku": "RICE-01", "name": "Rice", "price": "10", "unit": "kg"},
    )
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

    started = await client.post("/api/v1/voice/provision/cases", headers=headers, json={})
    assert started.status_code == 201
    case = started.json()
    assert case["demo_mode"] is False
    inventory_id = case["shortage_snapshot"]["items"][0]["inventory_id"]

    owner = await client.post(
        f"/api/v1/voice/provision/cases/{case['id']}/owner-decision",
        headers=headers,
        json={"transcript": "Yes, contact suppliers for quotations only."},
    )
    assert owner.status_code == 200
    assert owner.json()["status"] == "awaiting_manager_quantities"

    manager_contacts = [row for row in contacts if row["role"] == "manager"]
    for manager in manager_contacts:
        response = await client.post(
            f"/api/v1/voice/provision/cases/{case['id']}/managers/{manager['id']}/response",
            headers=headers,
            json={
                "transcript": "Rice 20 kilograms.",
                "quantities": [{"inventory_id": inventory_id, "quantity": "20"}],
            },
        )
        assert response.status_code == 200
    assert response.json()["status"] == "awaiting_supplier_quotation"

    quote = await client.post(
        f"/api/v1/voice/provision/cases/{case['id']}/supplier-response",
        headers=headers,
        json={
            "transcript": "Rice is available at ten dollars per kilogram, delivery tomorrow.",
            "currency": "USD",
            "delivery_days": 1,
            "items": [
                {"inventory_id": inventory_id, "available_quantity": "20", "unit_cost": "10"}
            ],
        },
    )
    assert quote.status_code == 200
    assert quote.json()["status"] == "awaiting_owner_purchase_approval"

    approved = await client.post(
        f"/api/v1/voice/provision/cases/{case['id']}/purchase-decision",
        headers=headers,
        json={"approve": True, "transcript": "I approve exactly 20 kilograms at ten dollars."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "purchase_order_created"
    assert approved.json()["purchase_id"]

    async with client.session_factory() as session:
        purchases = list(await session.scalars(select(Purchase)))
        turns = list(await session.scalars(select(VoiceConversationTurn)))
        audit = list(
            await session.scalars(select(AuditLog).where(AuditLog.action.like("provision.%")))
        )
    assert len(purchases) == 1
    assert purchases[0].status == "ordered"
    assert len(turns) >= 5
    assert len(audit) >= 4
