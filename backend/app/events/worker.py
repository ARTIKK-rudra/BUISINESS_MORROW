"""Outbox publisher and independent, at-least-once Redpanda consumer groups."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import and_, or_, select, text

from app.core.config import get_settings
from app.db.models import (
    AuditLog,
    EventConsumerReceipt,
    Inventory,
    MLEventTask,
    ModelVersion,
    Notification,
    Order,
    OrderItem,
    OutboxEvent,
    RealtimeBusinessMetric,
    RealtimeEvent,
    Recipe,
    RecipeIngredient,
    Recommendation,
)
from app.db.session import SessionFactory, engine
from app.events.contracts import BusinessEvent, EventType
from app.events.voice_calls import enqueue_stock_call, voice_call_loop

logger = logging.getLogger("morrow.events")
settings = get_settings()
MAX_BATCH = 100
MAX_CONSUMER_ATTEMPTS = settings.event_retry_limit


def envelope(row: OutboxEvent) -> BusinessEvent:
    return BusinessEvent(
        event_id=row.id,
        event_type=row.event_type,
        schema_version=row.schema_version,
        business_id=row.business_id,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        occurred_at=row.created_at or datetime.now(UTC),
        correlation_id=(row.payload or {}).get("request_id"),
        payload=row.payload,
    )


def encode(event: BusinessEvent) -> bytes:
    return event.model_dump_json().encode()


async def publish_dead_letter(producer: AIOKafkaProducer, body: dict) -> None:
    await producer.send_and_wait(
        settings.redpanda_dlq_topic,
        json.dumps(body, default=str).encode(),
        key=str(body.get("event_id", "unknown")).encode(),
    )


async def publish_outbox_batch(producer: AIOKafkaProducer) -> int:
    now = datetime.now(UTC)
    async with SessionFactory() as session:
        async with session.begin():
            rows = list(
                (
                    await session.scalars(
                        select(OutboxEvent)
                        .where(
                            OutboxEvent.published_at.is_(None),
                            OutboxEvent.dead_lettered_at.is_(None),
                            (
                                OutboxEvent.next_attempt_at.is_(None)
                                | (OutboxEvent.next_attempt_at <= now)
                            ),
                            (OutboxEvent.locked_until.is_(None) | (OutboxEvent.locked_until < now)),
                        )
                        .order_by(OutboxEvent.created_at, OutboxEvent.id)
                        .limit(MAX_BATCH)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            for row in rows:
                row.locked_until = now + timedelta(seconds=60)
    sent = 0
    for row in rows:
        key = f"{row.business_id}:{row.aggregate_type}:{row.aggregate_id}".encode()
        try:
            event = envelope(row)
            await producer.send_and_wait(
                settings.redpanda_events_topic,
                encode(event),
                key=key,
                headers=[
                    ("event-type", event.event_type.value.encode()),
                    ("schema-version", str(event.schema_version).encode()),
                ],
            )
            async with SessionFactory() as session, session.begin():
                current = await session.get(OutboxEvent, row.id)
                if current and current.published_at is None:
                    current.published_at = datetime.now(UTC)
                    current.locked_until = None
                    current.last_error = None
            sent += 1
        except Exception as exc:  # broker failures remain retryable from PostgreSQL
            logger.exception("outbox publish failed", extra={"event_id": str(row.id)})
            async with SessionFactory() as session, session.begin():
                current = await session.get(OutboxEvent, row.id)
                if current is None or current.published_at is not None:
                    continue
                current.attempts += 1
                current.last_error = str(exc)[:4000]
                current.locked_until = None
                if current.attempts >= settings.event_retry_limit:
                    try:
                        await publish_dead_letter(
                            producer,
                            {
                                "event_id": str(current.id),
                                "consumer": "outbox-publisher",
                                "error": current.last_error,
                                "event": envelope(current).model_dump(mode="json"),
                            },
                        )
                        current.dead_lettered_at = datetime.now(UTC)
                    except Exception:
                        current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                        logger.exception(
                            "outbox DLQ publish failed", extra={"event_id": str(row.id)}
                        )
                else:
                    delay = min(2**current.attempts, 300)
                    current.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
    return sent


async def publish_loop(producer: AIOKafkaProducer) -> None:
    while True:
        try:
            count = await publish_outbox_batch(producer)
            if not count:
                await asyncio.sleep(0.75)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("outbox publisher loop failed")
            await asyncio.sleep(2)


async def eligible_products(task: dict) -> set[UUID]:
    payload = task["payload"]
    business_id = task["business_id"]
    async with SessionFactory() as session:
        if task["event_type"] == EventType.SALE_CREATED.value:
            try:
                order_id = UUID(str(payload["order_id"]))
            except (KeyError, ValueError):
                return set()
            return set(
                await session.scalars(
                    select(OrderItem.product_id)
                    .join(Order, Order.id == OrderItem.order_id)
                    .where(Order.id == order_id, Order.business_id == business_id)
                )
            )
        if task["event_type"] == EventType.INVENTORY_UPDATED.value:
            try:
                inventory_id = UUID(str(payload["inventory_id"]))
            except (KeyError, ValueError):
                return set()
            item = await session.get(Inventory, inventory_id)
            if item is None or item.business_id != business_id:
                return set()
            if item.product_id:
                return {item.product_id}
            if item.ingredient_id:
                return set(
                    await session.scalars(
                        select(Recipe.product_id)
                        .join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
                        .where(
                            Recipe.business_id == business_id,
                            RecipeIngredient.ingredient_id == item.ingredient_id,
                        )
                    )
                )
        if task["event_type"] == EventType.FORECAST_UPDATED.value:
            product_id = payload.get("product_id")
            if product_id:
                try:
                    return {UUID(str(product_id))}
                except ValueError:
                    return set()
    return set()


async def train_product_if_due(business_id: UUID, product_id: UUID) -> dict:
    from app.services.forecasting import ForecastingService

    cutoff = datetime.now(UTC) - timedelta(minutes=15)
    lock_key = f"morrow-demand:{business_id}:{product_id}"
    async with engine.connect() as lock_connection:
        await lock_connection.execute(
            text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        try:
            async with SessionFactory() as session:
                models = await session.scalars(
                    select(ModelVersion).where(
                        ModelVersion.business_id == business_id,
                        ModelVersion.model_type == "demand_forecast",
                        ModelVersion.status == "selected",
                        ModelVersion.trained_at >= cutoff,
                    )
                )
                recent = next(
                    (
                        model
                        for model in models
                        if (model.metadata_json or {}).get("product_id") == str(product_id)
                    ),
                    None,
                )
                if recent:
                    return {
                        "product_id": str(product_id),
                        "status": "recent_model_reused",
                        "selected_model_version": recent.version,
                    }
            async with SessionFactory() as session:
                result = await ForecastingService(session).train(business_id, None, product_id)
                return json.loads(json.dumps(result, default=str))
        finally:
            await lock_connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                {"lock_key": lock_key},
            )


async def process_ml_tasks() -> int:
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        tasks = list(
            (
                await session.scalars(
                    select(MLEventTask)
                    .where(
                        or_(
                            and_(
                                MLEventTask.status == "pending",
                                or_(
                                    MLEventTask.next_attempt_at.is_(None),
                                    MLEventTask.next_attempt_at <= now,
                                ),
                            ),
                            and_(
                                MLEventTask.status == "processing",
                                MLEventTask.locked_until <= now,
                            ),
                        )
                    )
                    .order_by(MLEventTask.created_at)
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        claimed = []
        for task in tasks:
            task.status = "processing"
            task.attempts += 1
            task.locked_until = now + timedelta(minutes=15)
            claimed.append(
                {
                    "id": task.source_event_id,
                    "business_id": task.business_id,
                    "event_type": task.event_type,
                    "payload": task.payload,
                    "attempts": task.attempts,
                }
            )
    if not claimed:
        return 0

    product_tasks: dict[tuple[UUID, UUID], list[UUID]] = {}
    results: dict[UUID, dict] = {}
    failures: dict[UUID, str] = {}
    for task in claimed:
        try:
            products = await eligible_products(task)
            for product_id in products:
                product_tasks.setdefault((task["business_id"], product_id), []).append(task["id"])
            if not products:
                results[task["id"]] = {"status": "no_eligible_product"}
        except Exception as exc:
            failures[task["id"]] = str(exc)

    for (business_id, product_id), task_ids in product_tasks.items():
        try:
            result = await train_product_if_due(business_id, product_id)
            for task_id in task_ids:
                results.setdefault(task_id, {}).setdefault("products", []).append(result)
        except Exception as exc:
            for task_id in task_ids:
                failures[task_id] = str(exc)

    async with SessionFactory() as session, session.begin():
        for task in claimed:
            row = await session.get(MLEventTask, task["id"], with_for_update=True)
            if row is None or row.status != "processing":
                continue
            error = failures.get(task["id"])
            row.locked_until = None
            if error:
                row.last_error = error[:4000]
                if task["attempts"] >= settings.event_retry_limit:
                    row.status = "failed"
                else:
                    row.status = "pending"
                    row.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=min(2 ** task["attempts"], 300)
                    )
            else:
                row.status = "completed"
                row.processed_at = datetime.now(UTC)
                row.result_json = results.get(task["id"], {"status": "processed"})
                row.last_error = None
    return len(claimed)


async def ml_task_loop() -> None:
    while True:
        try:
            count = await process_ml_tasks()
            if not count:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ML event task processing failed")
            await asyncio.sleep(5)


async def process_event(consumer_name: str, event: BusinessEvent) -> None:
    async with SessionFactory() as session, session.begin():
        receipt = await session.get(
            EventConsumerReceipt, (event.event_id, consumer_name), with_for_update=True
        )
        if receipt and (receipt.processed_at or receipt.dead_lettered_at):
            return
        await apply_handler(consumer_name, event, session)
        if receipt is None:
            receipt = EventConsumerReceipt(event_id=event.event_id, consumer_name=consumer_name)
            session.add(receipt)
        receipt.processed_at = datetime.now(UTC)
        receipt.last_error = None


async def apply_handler(name: str, event: BusinessEvent, session) -> None:
    p = event.payload
    if name == "database":
        session.add(
            RealtimeEvent(
                source_event_id=event.event_id,
                business_id=event.business_id,
                event_type=event.event_type.value,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                payload=p,
                created_at=event.occurred_at,
            )
        )
    elif name == "analytics":
        metric = await session.get(RealtimeBusinessMetric, event.business_id, with_for_update=True)
        if metric is None:
            metric = RealtimeBusinessMetric(
                business_id=event.business_id,
                event_count=0,
                event_counts={},
                amount_totals={},
            )
            session.add(metric)
        metric.event_count += 1
        metric.last_event_at = event.occurred_at
        counts = dict(metric.event_counts or {})
        counts[event.event_type.value] = counts.get(event.event_type.value, 0) + 1
        metric.event_counts = counts
        try:
            value = Decimal(str(p.get("total", p.get("amount", "0"))))
        except (InvalidOperation, TypeError):
            value = Decimal("0")
        amount_category = {
            EventType.SALE_CREATED: "sales",
            EventType.REFUND_CREATED: "refunds",
            EventType.PURCHASE_CREATED: "purchases",
        }.get(event.event_type)
        if amount_category and value.is_finite():
            currency = str(p.get("currency", "UNKNOWN")).upper()[:3]
            totals = {key: dict(value) for key, value in (metric.amount_totals or {}).items()}
            previous = Decimal(str(totals.setdefault(amount_category, {}).get(currency, "0")))
            totals[amount_category][currency] = str(previous + value)
            metric.amount_totals = totals
    elif name == "ml":
        if event.event_type in {
            EventType.SALE_CREATED,
            EventType.INVENTORY_UPDATED,
            EventType.FORECAST_UPDATED,
        }:
            session.add(
                MLEventTask(
                    source_event_id=event.event_id,
                    business_id=event.business_id,
                    event_type=event.event_type.value,
                    payload=p,
                    status="pending",
                    created_at=event.occurred_at,
                )
            )
    elif name == "notifications":
        notices = {
            EventType.SALE_CREATED: (
                "Sale recorded",
                "A completed sale was recorded in this business.",
            ),
            EventType.REFUND_CREATED: (
                "Refund recorded",
                "A refund was recorded and reflected in the ledger.",
            ),
            EventType.PURCHASE_CREATED: (
                "Purchase order created",
                "A purchase order was created and awaits goods receipt.",
            ),
            EventType.STOCK_LOW: ("Low stock", "An inventory item is below its reorder level."),
            EventType.STOCK_CRITICAL: (
                "Critical stock",
                "An inventory item needs immediate attention.",
            ),
            EventType.STOCK_OUT_OF_STOCK: (
                "Out of stock",
                "An inventory item has no remaining stock.",
            ),
            EventType.ANOMALY_DETECTED: (
                "Anomaly detected",
                str(p.get("summary", "Review an unusual business event.")),
            ),
            EventType.REORDER_RECOMMENDED: (
                "Reorder recommended",
                str(p.get("summary", "Review the suggested reorder.")),
            ),
        }
        if event.event_type in notices:
            title, body = notices[event.event_type]
            session.add(
                Notification(
                    business_id=event.business_id,
                    source_event_id=event.event_id,
                    title=title,
                    body=body,
                    status="pending",
                    channel="in_app",
                )
            )
            session.add(
                OutboxEvent(
                    business_id=event.business_id,
                    event_type=EventType.NOTIFICATION_CREATED.value,
                    schema_version=1,
                    aggregate_type="notification",
                    aggregate_id=str(event.event_id),
                    payload={"source_event_id": str(event.event_id), "title": title},
                )
            )
    elif name == "voice_calls":
        await enqueue_stock_call(event, session)
    elif name == "audit":
        session.add(
            AuditLog(
                business_id=event.business_id,
                action="event.consumed",
                entity_type=event.aggregate_type,
                entity_id=event.aggregate_id,
                request_id=event.correlation_id,
                metadata_json={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type.value,
                    "consumer": "audit",
                },
            )
        )
    elif name == "recommendations" and event.event_type in {
        EventType.STOCK_LOW,
        EventType.STOCK_CRITICAL,
        EventType.STOCK_OUT_OF_STOCK,
    }:
        try:
            inventory_id = UUID(str(p.get("inventory_id", event.aggregate_id)))
        except ValueError:
            return
        item = await session.get(Inventory, inventory_id, with_for_update=True)
        if item is not None and item.business_id == event.business_id:
            gap = max(Decimal("0"), item.reorder_point + item.safety_stock - item.quantity)
            if gap > 0:
                summary = f"Reorder {gap.normalize()} units for inventory item"
                session.add(
                    Recommendation(
                        business_id=event.business_id,
                        recommendation_type="reorder",
                        target_type="inventory",
                        target_id=str(item.id),
                        summary=summary,
                        rationale=(
                            "Rule-based: stock is below the reorder point plus safety stock."
                        ),
                        status="pending",
                        provenance={"source": "rule_based", "source_event_id": str(event.event_id)},
                    )
                )
                session.add(
                    OutboxEvent(
                        business_id=event.business_id,
                        event_type=EventType.REORDER_RECOMMENDED.value,
                        schema_version=1,
                        aggregate_type="inventory",
                        aggregate_id=str(item.id),
                        payload={
                            "inventory_id": str(item.id),
                            "quantity": str(gap),
                            "summary": summary,
                            "provenance": "rule_based",
                        },
                    )
                )


async def record_failure(name: str, event: BusinessEvent, error: str) -> int:
    async with SessionFactory() as session, session.begin():
        receipt = await session.get(
            EventConsumerReceipt, (event.event_id, name), with_for_update=True
        )
        if receipt is None:
            receipt = EventConsumerReceipt(event_id=event.event_id, consumer_name=name, attempts=0)
            session.add(receipt)
        receipt.attempts += 1
        receipt.last_error = error[:4000]
        return receipt.attempts


async def consume_group(name: str, producer: AIOKafkaProducer) -> None:
    consumer = AIOKafkaConsumer(
        settings.redpanda_events_topic,
        bootstrap_servers=settings.redpanda_brokers,
        group_id=f"morrow-{name}-v1",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async for message in consumer:
            try:
                event = BusinessEvent.model_validate_json(message.value)
            except Exception as exc:
                await publish_dead_letter(
                    producer,
                    {
                        "consumer": name,
                        "topic": message.topic,
                        "partition": message.partition,
                        "offset": message.offset,
                        "error": str(exc)[:4000],
                        "raw_value": message.value.decode(errors="replace")[:16000],
                    },
                )
                await consumer.commit()
                continue
            try:
                await process_event(name, event)
                await consumer.commit()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("event consumer failed", extra={"consumer": name})
                attempts = await record_failure(name, event, str(exc))
                if attempts >= MAX_CONSUMER_ATTEMPTS:
                    await publish_dead_letter(
                        producer,
                        {
                            "event_id": str(event.event_id),
                            "consumer": name,
                            "error": str(exc)[:4000],
                            "event": event.model_dump(mode="json"),
                        },
                    )
                    async with SessionFactory() as session, session.begin():
                        receipt = await session.get(
                            EventConsumerReceipt, (event.event_id, name), with_for_update=True
                        )
                        receipt.dead_lettered_at = datetime.now(UTC)
                    await consumer.commit()
                else:
                    await asyncio.sleep(min(2**attempts, 60))
    finally:
        await consumer.stop()


async def main() -> None:
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.redpanda_brokers,
        enable_idempotence=True,
        value_serializer=None,
    )
    await producer.start()
    try:
        await asyncio.gather(
            publish_loop(producer),
            ml_task_loop(),
            voice_call_loop(),
            *(
                consume_group(name, producer)
                for name in (
                    "database",
                    "analytics",
                    "ml",
                    "notifications",
                    "audit",
                    "recommendations",
                    "voice_calls",
                )
            ),
        )
    finally:
        await producer.stop()


if __name__ == "__main__":
    logging.basicConfig(level=settings.log_level)
    asyncio.run(main())
