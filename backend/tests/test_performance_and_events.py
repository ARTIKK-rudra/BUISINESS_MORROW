from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from app.db.models import (
    Business,
    EventConsumerReceipt,
    Notification,
    Product,
    Supplier,
    SupplierProduct,
)
from app.events.contracts import BusinessEvent, EventType
from app.services.supplier_intelligence import SupplierIntelligenceService


@pytest.mark.asyncio
async def test_event_consumer_is_idempotent_and_generates_notification(client, monkeypatch):
    from app.events import worker

    auth = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Events Owner",
            "email": "events-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    business_id = UUID(auth.json()["business_id"])
    event_id = uuid4()
    business_event = BusinessEvent(
        event_id=event_id,
        event_type=EventType.PURCHASE_CREATED,
        schema_version=1,
        business_id=business_id,
        aggregate_type="purchase",
        aggregate_id=str(uuid4()),
        occurred_at=datetime.now(UTC),
        payload={"purchase_id": str(uuid4()), "currency": "USD", "total": "21.50"},
    )
    monkeypatch.setattr(worker, "SessionFactory", client.session_factory)
    started = perf_counter()
    await worker.process_event("notifications", business_event)
    elapsed_ms = (perf_counter() - started) * 1000
    await worker.process_event("notifications", business_event)
    async with client.session_factory() as session:
        notices = list((await session.scalars(select(Notification))).all())
        receipt = await session.get(EventConsumerReceipt, (event_id, "notifications"))
    assert len(notices) == 1
    assert notices[0].title == "Purchase order created"
    assert receipt is not None and receipt.processed_at is not None
    print(f"PERF event notification transaction: {elapsed_ms:.2f} ms (SQLite test database)")


@pytest.mark.asyncio
async def test_supplier_intelligence_query_and_latency_profile(client):
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Supplier Perf Owner",
            "email": "supplier-perf@example.com",
            "password": "secure-quality-test-password",
        },
    )
    business_id = UUID(registration.json()["business_id"])
    async with client.session_factory() as session:
        business = await session.get(Business, business_id)
        products = [
            Product(
                business_id=business_id,
                sku=f"PERF-{index}",
                name=f"Profile item {index}",
                price=Decimal("1.00"),
                unit="each",
            )
            for index in range(2)
        ]
        suppliers = [
            Supplier(business_id=business_id, name=f"Profile supplier {index}")
            for index in range(4)
        ]
        session.add_all(products + suppliers)
        await session.flush()
        offers = [
            SupplierProduct(
                business_id=business_id,
                supplier_id=supplier.id,
                product_id=product.id,
                unit_cost=Decimal("2.00") + index,
                currency=business.base_currency,
                lead_time_days=2,
                minimum_order_quantity=Decimal("1"),
            )
            for index, supplier in enumerate(suppliers)
            for product in products
        ]
        session.add_all(offers)
        await session.commit()

    query_count = 0

    def count_query(*_args):
        nonlocal query_count
        query_count += 1

    bind = client.session_factory.kw["bind"].sync_engine
    event.listen(bind, "before_cursor_execute", count_query)
    try:
        async with client.session_factory() as session:
            started = perf_counter()
            rows = await SupplierIntelligenceService(session).list(business_id)
            elapsed_ms = (perf_counter() - started) * 1000
    finally:
        event.remove(bind, "before_cursor_execute", count_query)
    assert len(rows) == 4
    assert sum(len(row["offers"]) for row in rows) == 8
    print(
        "PERF supplier intelligence: "
        f"{elapsed_ms:.2f} ms, {query_count} SQL queries for 4 suppliers/8 offers (SQLite)"
    )


@pytest.mark.asyncio
async def test_api_latency_smoke_profile(client):
    auth = await client.post(
        "/api/v1/auth/register",
        json={
            "name": "Latency Owner",
            "email": "latency-quality@example.com",
            "password": "secure-quality-test-password",
        },
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    durations_ms = []
    for _ in range(20):
        started = perf_counter()
        response = await client.get("/api/v1/products", headers=headers)
        durations_ms.append((perf_counter() - started) * 1000)
        assert response.status_code == 200
    ordered = sorted(durations_ms)
    p50 = ordered[len(ordered) // 2]
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    print(f"PERF API GET /products: p50 {p50:.2f} ms, p95 {p95:.2f} ms (SQLite/ASGI)")
