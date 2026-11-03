import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.dependencies import MembershipDep, require_permission
from app.db.models import RealtimeEvent
from app.db.session import SessionFactory
from app.services.authorization import Permission

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream", dependencies=[Depends(require_permission(Permission.INSIGHTS_READ))])
async def stream_events(
    request: Request,
    membership: MembershipDep,
    after: str | None = Query(
        default=None, description="Opaque cursor from a previous stream event"
    ),
):
    cursor_sequence = 0
    if after:
        try:
            cursor_sequence = max(int(after), 0)
        except (ValueError, TypeError):
            cursor_sequence = 0
    else:
        async with SessionFactory() as session:
            latest_sequence = await session.scalar(
                select(func.max(RealtimeEvent.stream_sequence)).where(
                    RealtimeEvent.business_id == membership.business_id
                )
            )
        cursor_sequence = max(0, int(latest_sequence or 0) - 100)

    async def generate():
        nonlocal cursor_sequence
        heartbeat = 0
        while not await request.is_disconnected():
            async with SessionFactory() as session:
                criteria = [RealtimeEvent.business_id == membership.business_id]
                criteria.append(RealtimeEvent.stream_sequence > cursor_sequence)
                rows = list(
                    (
                        await session.scalars(
                            select(RealtimeEvent)
                            .where(*criteria)
                            .order_by(RealtimeEvent.stream_sequence)
                            .limit(100)
                        )
                    ).all()
                )
            for row in rows:
                cursor_sequence = row.stream_sequence
                cursor = str(cursor_sequence)
                data = {
                    "event_id": str(row.source_event_id),
                    "event_type": row.event_type,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_id": row.aggregate_id,
                    "occurred_at": row.created_at.isoformat(),
                    "payload": row.payload,
                }
                yield f"id: {cursor}\nevent: business\ndata: {json.dumps(data, default=str)}\n\n"
            if not rows:
                heartbeat += 1
                if heartbeat % 15 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
