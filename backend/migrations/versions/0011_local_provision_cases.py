"""Persist local/browser provision workflow state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_provision_cases"
down_revision: str | None = "0010_voice_conversation_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provision_cases",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_contact_id",
            sa.Uuid(),
            sa.ForeignKey("voice_contacts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(48), nullable=False, server_default="awaiting_owner"),
        sa.Column("demo_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("shortage_snapshot", sa.JSON(), nullable=False),
        sa.Column("manager_recommendations", sa.JSON(), nullable=False),
        sa.Column("supplier_quote", sa.JSON()),
        sa.Column("approval", sa.JSON()),
        sa.Column(
            "purchase_id",
            sa.Uuid(),
            sa.ForeignKey("purchases.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("idempotency_key", sa.String(100)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_provision_cases_business_id", "provision_cases", ["business_id"])
    op.create_index("ix_provision_cases_owner_contact_id", "provision_cases", ["owner_contact_id"])
    op.create_index("ix_provision_cases_created_by", "provision_cases", ["created_by"])
    op.create_index(
        "ix_provision_case_business_status",
        "provision_cases",
        ["business_id", "status", "created_at"],
    )
    op.create_index(
        "uq_provision_case_business_key",
        "provision_cases",
        ["business_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_provision_case_business_key", table_name="provision_cases")
    op.drop_index("ix_provision_case_business_status", table_name="provision_cases")
    op.drop_index("ix_provision_cases_created_by", table_name="provision_cases")
    op.drop_index("ix_provision_cases_owner_contact_id", table_name="provision_cases")
    op.drop_index("ix_provision_cases_business_id", table_name="provision_cases")
    op.drop_table("provision_cases")
