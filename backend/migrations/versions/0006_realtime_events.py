"""Add Redpanda outbox delivery state and realtime consumer projections."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_realtime_events"
down_revision: str | None = "0005_ml_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch:
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_outbox_delivery",
        "outbox_events",
        ["published_at", "dead_lettered_at", "next_attempt_at", "locked_until", "created_at"],
    )
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("source_event_id", sa.Uuid(), nullable=True))
    op.create_index(
        "uq_notification_source_event", "notifications", ["source_event_id"], unique=True
    )
    op.create_table(
        "event_consumer_receipts",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("consumer_name", sa.String(60), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_event_receipts_retry", "event_consumer_receipts", ["consumer_name", "processed_at"]
    )
    op.create_table(
        "realtime_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("stream_sequence", sa.BigInteger(), sa.Identity(start=1), nullable=False),
        sa.Column("source_event_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stream_sequence"),
    )
    op.create_index("ix_realtime_events_business_id", "realtime_events", ["business_id"])
    op.create_index(
        "ix_realtime_business_created", "realtime_events", ["business_id", "created_at"]
    )
    op.create_index(
        "ix_realtime_business_sequence", "realtime_events", ["business_id", "stream_sequence"]
    )
    op.create_table(
        "realtime_business_metrics",
        sa.Column("business_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_counts", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("amount_totals", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "ml_event_tasks",
        sa.Column("source_event_id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ml_event_tasks_business_id", "ml_event_tasks", ["business_id"])
    op.create_index(
        "ix_ml_event_tasks_status_created",
        "ml_event_tasks",
        ["status", "next_attempt_at", "locked_until", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ml_event_tasks")
    op.drop_table("realtime_business_metrics")
    op.drop_index("ix_realtime_business_created", table_name="realtime_events")
    op.drop_index("ix_realtime_business_sequence", table_name="realtime_events")
    op.drop_index("ix_realtime_events_business_id", table_name="realtime_events")
    op.drop_table("realtime_events")
    op.drop_index("ix_event_receipts_retry", table_name="event_consumer_receipts")
    op.drop_table("event_consumer_receipts")
    op.drop_index("uq_notification_source_event", table_name="notifications")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("source_event_id")
    op.drop_index("ix_outbox_delivery", table_name="outbox_events")
    with op.batch_alter_table("outbox_events") as batch:
        batch.drop_column("dead_lettered_at")
        batch.drop_column("last_error")
        batch.drop_column("locked_until")
        batch.drop_column("next_attempt_at")
        batch.drop_column("attempts")
