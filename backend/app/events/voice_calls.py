"""Outbox consumer handler and durable outbound voice-call worker."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.db.models import Ingredient, Inventory, Product, VoiceAlertSettings, VoiceCallTask
from app.db.session import SessionFactory
from app.events.contracts import BusinessEvent, EventType

settings = get_settings()
logger = logging.getLogger("morrow.events.voice")
ALERT_TYPES = {EventType.STOCK_LOW, EventType.STOCK_CRITICAL, EventType.STOCK_OUT_OF_STOCK}


async def enqueue_stock_call(event: BusinessEvent, session) -> None:
    if event.event_type not in ALERT_TYPES:
        return
    config = await session.scalar(
        select(VoiceAlertSettings).where(
            VoiceAlertSettings.business_id == event.business_id,
            VoiceAlertSettings.enabled.is_(True),
        )
    )
    if config is None:
        return
    try:
        inventory_id = UUID(str(event.payload.get("inventory_id", event.aggregate_id)))
    except ValueError:
        logger.warning(
            "invalid inventory id in stock alert", extra={"event_id": str(event.event_id)}
        )
        return
    item = await session.scalar(
        select(Inventory).where(
            Inventory.id == inventory_id, Inventory.business_id == event.business_id
        )
    )
    if item is None:
        return
    item_name, unit = "inventory item", "units"
    if item.product_id:
        product = await session.get(Product, item.product_id)
        if product:
            item_name, unit = product.name, product.unit
    elif item.ingredient_id:
        ingredient = await session.get(Ingredient, item.ingredient_id)
        if ingredient:
            item_name, unit = ingredient.name, ingredient.unit
    level = {
        EventType.STOCK_LOW: "below its reorder level",
        EventType.STOCK_CRITICAL: "at a critical level",
        EventType.STOCK_OUT_OF_STOCK: "out of stock",
    }[event.event_type]
    session.add(
        VoiceCallTask(
            business_id=event.business_id,
            source_event_id=event.event_id,
            recipient_phone=config.recipient_phone,
            message=(
                f"Morrow inventory alert. {item_name} is {level}. "
                f"Current quantity is {item.quantity} {unit}. Please review inventory."
            ),
            status="pending",
        )
    )


async def process_voice_call_batch() -> int:
    if not settings.voice_delivery_enabled:
        return 0
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        tasks = list(
            (
                await session.scalars(
                    select(VoiceCallTask)
                    .where(
                        VoiceCallTask.status.in_(("pending", "queued")),
                        or_(
                            VoiceCallTask.next_attempt_at.is_(None),
                            VoiceCallTask.next_attempt_at <= now,
                        ),
                        or_(
                            VoiceCallTask.locked_until.is_(None), VoiceCallTask.locked_until <= now
                        ),
                    )
                    .order_by(VoiceCallTask.created_at)
                    .limit(20)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for task in tasks:
            task.locked_until = now + timedelta(seconds=60)

    if not tasks:
        return 0
    from app.services.outbound_voice import get_call, start_call

    for claimed in tasks:
        try:
            async with SessionFactory() as session:
                task = await session.get(VoiceCallTask, claimed.id)
                if task is None:
                    continue
                if task.provider_call_sid:
                    result = await get_call(task.provider_call_sid)
                    call_status = str(result.get("status", "unknown"))
                    if call_status == "completed":
                        task.status = "completed"
                        task.processed_at = datetime.now(UTC)
                        task.last_error = None
                    elif call_status in {"busy", "failed", "no-answer", "canceled"}:
                        task.last_error = f"Call ended with status: {call_status}"
                        if task.attempts < settings.voice_call_max_attempts:
                            task.status = "pending"
                            task.provider_call_sid = None
                            task.next_attempt_at = datetime.now(UTC) + timedelta(
                                seconds=min(30 * (2 ** max(task.attempts - 1, 0)), 300)
                            )
                        else:
                            task.status = "failed"
                            task.processed_at = datetime.now(UTC)
                    else:
                        task.status = "queued"
                        task.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                    task.locked_until = None
                    await session.commit()
                    continue

                task.attempts += 1
                phone, message = task.recipient_phone, task.message
                await session.commit()
                result = await start_call(phone, message)
                async with SessionFactory() as result_session, result_session.begin():
                    task = await result_session.get(VoiceCallTask, claimed.id, with_for_update=True)
                    if task:
                        task.provider_call_sid = result.get("sid")
                        task.status = "queued"
                        task.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                        task.last_error = None
                        task.locked_until = None
        except Exception as exc:
            logger.exception("outbound stock alert call failed", extra={"task_id": str(claimed.id)})
            async with SessionFactory() as session, session.begin():
                task = await session.get(VoiceCallTask, claimed.id, with_for_update=True)
                if task is None:
                    continue
                task.locked_until = None
                task.last_error = str(exc)[:1000]
                if task.attempts >= settings.voice_call_max_attempts:
                    task.status = "failed"
                    task.processed_at = datetime.now(UTC)
                else:
                    task.status = "pending"
                    task.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=min(30 * (2 ** max(task.attempts - 1, 0)), 300)
                    )
    return len(tasks)


async def voice_call_loop() -> None:
    while True:
        try:
            count = await process_voice_call_batch()
            if not count:
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("voice call worker failed")
            await asyncio.sleep(5)
