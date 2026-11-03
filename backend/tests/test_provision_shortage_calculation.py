from decimal import Decimal
from uuid import UUID

import pytest

from app.db.models import Order, OrderItem
from app.services.provision_voice import ProvisionVoiceService


@pytest.mark.asyncio
async def test_shortage_snapshot_assesses_pending_recipe_demand(client):
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Recipe Owner",
            "email": "recipe-provision@example.com",
            "password": "a-secure-test-password",
            "business_name": "Recipe shortage test",
        },
    )
    assert registered.status_code == 201
    auth = registered.json()
    headers = {"Authorization": f"Bearer {auth['access_token']}"}

    rice = await client.post(
        "/api/v1/ingredients",
        headers=headers,
        json={"sku": "RICE", "name": "Rice", "unit": "kg", "minimum_stock": "5"},
    )
    assert rice.status_code == 201
    meal = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"sku": "MEAL", "name": "Rice meal", "price": "12", "unit": "portion"},
    )
    assert meal.status_code == 201
    recipe = await client.post(
        "/api/v1/recipes",
        headers=headers,
        json={
            "product_id": meal.json()["id"],
            "yield_quantity": "1",
            "yield_unit": "portion",
            "ingredients": [{"ingredient_id": rice.json()["id"], "quantity": "2", "unit": "kg"}],
        },
    )
    assert recipe.status_code == 201
    inventory = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "ingredient_id": rice.json()["id"],
            "location": "Main",
            "reorder_point": "5",
            "minimum_stock": "5",
        },
    )
    assert inventory.status_code == 201
    stocked = await client.post(
        f"/api/v1/inventory/{inventory.json()['id']}/adjust",
        headers=headers,
        json={"quantity_delta": "1", "reason": "opening balance"},
    )
    assert stocked.status_code == 200

    async with client.session_factory() as session:
        order = Order(
            business_id=UUID(auth["business_id"]),
            status="pending",
            subtotal=Decimal("24"),
            discount=Decimal("0"),
            tax=Decimal("0"),
            total=Decimal("24"),
            currency="USD",
        )
        order.items.append(
            OrderItem(
                product_id=UUID(meal.json()["id"]),
                product_name="Rice meal",
                quantity=Decimal("2"),
                unit_price=Decimal("12"),
                unit_cost=Decimal("0"),
                line_total=Decimal("24"),
            )
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        snapshot = await ProvisionVoiceService(session).shortage_snapshot(UUID(auth["business_id"]))

    assert snapshot["affected_order_calculation"] == "recipe_and_inventory_assessed"
    assert snapshot["pending_order_count"] == 1
    assert snapshot["affected_order_count"] == 1
    assert snapshot["affected_order_ids"] == [str(order.id)]
    assert len(snapshot["items"]) == 1
    item = snapshot["items"][0]
    assert item["name"] == "Rice"
    assert item["available"] == "1.000"
    assert item["pending_demand"] == "4.000"
    assert item["shortage_to_minimum"] == "4.000"
    # Five kilograms must remain after covering the four kilograms committed to orders.
    assert item["replenishment_required"] == "8.000"
    assert item["committed_inbound"] == "0"
