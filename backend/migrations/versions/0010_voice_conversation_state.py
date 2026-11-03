"""Persist permission-controlled provision-call state and transcript turns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_voice_conversation_state"
down_revision: str | None = "0009_voice_contacts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.Uuid(),
            sa.ForeignKey("voice_contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("workflow", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), server_default="initiated", nullable=False),
        sa.Column("provider_call_sid", sa.String(40)),
        sa.Column("shortage_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "supplier_contact_authorized", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("purchase_authorized", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("turn_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "workflow IN ('owner_shortage_authorization', 'manager_quantity_collection', "
            "'supplier_quotation', 'owner_purchase_authorization')",
            name="ck_voice_conversation_workflow",
        ),
    )
    op.create_index("ix_voice_conversations_business_id", "voice_conversations", ["business_id"])
    op.create_index("ix_voice_conversations_contact_id", "voice_conversations", ["contact_id"])
    op.create_index(
        "ix_voice_conversation_business_status",
        "voice_conversations",
        ["business_id", "status", "created_at"],
    )
    op.create_index(
        "uq_voice_conversation_call_sid",
        "voice_conversations",
        ["provider_call_sid"],
        unique=True,
    )
    op.create_table(
        "voice_conversation_turns",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("voice_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("speaker", sa.String(16), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_voice_conversation_turns_conversation_id",
        "voice_conversation_turns",
        ["conversation_id"],
    )
    op.create_index(
        "ix_voice_turn_conversation_created",
        "voice_conversation_turns",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_turn_conversation_created", table_name="voice_conversation_turns")
    op.drop_index(
        "ix_voice_conversation_turns_conversation_id", table_name="voice_conversation_turns"
    )
    op.drop_table("voice_conversation_turns")
    op.drop_index("uq_voice_conversation_call_sid", table_name="voice_conversations")
    op.drop_index("ix_voice_conversation_business_status", table_name="voice_conversations")
    op.drop_index("ix_voice_conversations_contact_id", table_name="voice_conversations")
    op.drop_index("ix_voice_conversations_business_id", table_name="voice_conversations")
    op.drop_table("voice_conversations")
