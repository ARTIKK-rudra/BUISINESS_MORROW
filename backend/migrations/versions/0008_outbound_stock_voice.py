"""Persist opt-in low-stock voice alert configuration and call tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_outbound_stock_voice"
down_revision: str | None = "0007_phase8_interactions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_alert_settings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "voice_call_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_event_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("provider_call_sid", sa.String(40)),
        sa.Column("last_error", sa.Text()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_voice_call_tasks_business_id", "voice_call_tasks", ["business_id"])
    op.create_index("uq_voice_call_event", "voice_call_tasks", ["source_event_id"], unique=True)
    op.create_index(
        "ix_voice_call_delivery",
        "voice_call_tasks",
        ["status", "next_attempt_at", "locked_until", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_call_delivery", table_name="voice_call_tasks")
    op.drop_index("uq_voice_call_event", table_name="voice_call_tasks")
    op.drop_index("ix_voice_call_tasks_business_id", table_name="voice_call_tasks")
    op.drop_table("voice_call_tasks")
    op.drop_table("voice_alert_settings")
