from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


def add_audit_entry(
    session: AsyncSession,
    *,
    business_id: UUID,
    actor_user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | str | None,
    request_id: str | None,
    metadata: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            business_id=business_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            request_id=request_id,
            metadata_json=metadata,
        )
    )
