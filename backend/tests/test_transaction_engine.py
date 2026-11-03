import asyncio
from decimal import Decimal

import pytest

from app.db.models import LedgerEntry
from app.services import sales as sales_service


async def setup_business(client):
    auth = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Transaction Owner",
            "email": "transaction@example.com",
            "password": "secure-test-password",
        },
    )
    assert auth.status_code == 201
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    product = await client.post(
        "/api/v1/products",
        headers=headers,
        json={"sku": "TX-01", "name": "Widget", "price": "10.00", "unit": "each"},
    )
    assert product.status_code == 201
    product_id = product.json()["id"]
    inventory = await client.post(
        "/api/v1/inventory",
        headers=headers,
        json={
            "product_id": product_id,
            "location": "Main",
            "reorder_point": "2",
            "unit_cost_average": "2.0000",
        },
    )
    assert inventory.status_code == 201
    inventory_id = inventory.json()["id"]
    await client.post(
        f"/api/v1/inventory/{inventory_id}/adjust",
        headers=headers,
        json={"quantity_delta": "10", "reason": "opening balance"},
    )
    supplier = await client.post(
        "/api/v1/suppliers", headers=headers, json={"name": "Widget Supply"}
    )
    assert supplier.status_code == 201
    return headers, product_id, inventory_id, supplier.json()["id"]


@pytest.mark.asyncio
async def test_sale_purchase_refund_and_expense_post_atomically(client):
    headers, product_id, inventory_id, supplier_id = await setup_business(client)
    sale = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": "2"}],
            "payment_method": "cash",
            "idempotency_key": "sale-1",
        },
    )
    assert sale.status_code == 201
    # The sale creates its payment as part of the same database transaction.
    payment_response = await client.get("/api/v1/payments", headers=headers)
    assert payment_response.status_code == 200
    payment_id = payment_response.json()[0]["id"]

    purchase_payload = {
        "supplier_id": supplier_id,
        "items": [{"product_id": product_id, "quantity": "3", "unit_cost": "4.00"}],
        "currency": "USD",
        "idempotency_key": "purchase-1",
    }
    purchase = await client.post(
        "/api/v1/purchases",
        headers=headers,
        json=purchase_payload,
    )
    assert purchase.status_code == 201
    assert purchase.json()["total"] == "12.00"
    purchase_retry = await client.post("/api/v1/purchases", headers=headers, json=purchase_payload)
    assert purchase_retry.json()["id"] == purchase.json()["id"]
    purchase_item_id = purchase.json()["items"][0]["id"]
    receipt = await client.post(
        f"/api/v1/purchases/{purchase.json()['id']}/goods-received",
        headers=headers,
        json={"items": [{"purchase_item_id": purchase_item_id, "quantity": "3"}]},
    )
    assert receipt.status_code == 201
    after_purchase = await client.get("/api/v1/inventory", headers=headers)
    assert after_purchase.json()[0]["quantity"] == "11.000"

    refund_payload = {
        "payment_id": payment_id,
        "amount": "20.00",
        "reason": "return",
        "restock": True,
        "idempotency_key": "refund-1",
    }
    refund = await client.post(
        "/api/v1/refunds",
        headers=headers,
        json=refund_payload,
    )
    assert refund.status_code == 201
    refund_retry = await client.post("/api/v1/refunds", headers=headers, json=refund_payload)
    assert refund_retry.json()["id"] == refund.json()["id"]
    after_refund = await client.get("/api/v1/inventory", headers=headers)
    assert after_refund.json()[0]["quantity"] == "13.000"

    expense_payload = {
        "category": "utilities",
        "description": "Power bill",
        "amount": "5.25",
        "currency": "USD",
        "idempotency_key": "expense-1",
    }
    expense = await client.post(
        "/api/v1/expenses",
        headers=headers,
        json=expense_payload,
    )
    assert expense.status_code == 201
    expense_retry = await client.post("/api/v1/expenses", headers=headers, json=expense_payload)
    assert expense_retry.json()["id"] == expense.json()["id"]
    ledger = await client.get("/api/v1/ledger", headers=headers)
    assert ledger.status_code == 200
    assert len(ledger.json()) == 14
    assert {line["account"] for line in ledger.json()} >= {
        "Sales Revenue",
        "Cash",
        "Cost of Goods Sold",
        "Inventory Asset",
        "Accounts Payable",
        "Sales Returns",
        "Expense: utilities",
    }
    profit_loss = await client.get("/api/v1/analytics", headers=headers)
    assert profit_loss.status_code == 200
    assert profit_loss.json()["profit_and_loss"][0]["revenue"] == 20.0
    assert profit_loss.json()["profit_and_loss"][0]["refunds"] == 20.0
    assert profit_loss.json()["profit_and_loss"][0]["cost_of_goods_sold"] == 0.0
    assert profit_loss.json()["profit_and_loss"][0]["gross_profit"] == 0.0
    assert profit_loss.json()["profit_and_loss"][0]["net_profit"] == -5.25


@pytest.mark.asyncio
async def test_failed_sale_rolls_back_order_stock_and_journal(client, monkeypatch):
    headers, product_id, inventory_id, _ = await setup_business(client)

    def add_invalid_journal(session, **kwargs):
        session.add(
            LedgerEntry(
                business_id=kwargs["business_id"],
                account="invalid",
                source_type="sale",
                source_id=str(kwargs["source_id"]),
                debit=Decimal("-1"),
                credit=Decimal("0"),
                currency="USD",
            )
        )

    monkeypatch.setattr(sales_service, "add_journal", add_invalid_journal)
    result = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "items": [{"product_id": product_id, "quantity": "2"}],
            "idempotency_key": "rollback-1",
        },
    )
    assert result.status_code == 409
    inventory = await client.get("/api/v1/inventory", headers=headers)
    assert inventory.json()[0]["id"] == inventory_id
    assert inventory.json()[0]["quantity"] == "10.000"
    assert (await client.get("/api/v1/sales", headers=headers)).json() == []
    ledger = (await client.get("/api/v1/ledger", headers=headers)).json()
    assert len(ledger) == 2
    assert {line["source_type"] for line in ledger} == {"inventory_adjustment"}


@pytest.mark.asyncio
async def test_concurrent_sales_cannot_oversell_stock(client):
    headers, product_id, _, _ = await setup_business(client)

    async def sell(key):
        return await client.post(
            "/api/v1/sales",
            headers=headers,
            json={"items": [{"product_id": product_id, "quantity": "7"}], "idempotency_key": key},
        )

    first, second = await asyncio.gather(sell("concurrent-1"), sell("concurrent-2"))
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    inventory = await client.get("/api/v1/inventory", headers=headers)
    assert inventory.json()[0]["quantity"] == "3.000"
