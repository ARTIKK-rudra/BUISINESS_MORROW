"""Add tenant-scoped operational voice contacts.

Phone records are intentionally not seeded by migration: a migration cannot know
which tenant owns a supplied contact, and production contacts must be entered by
an authenticated owner or a controlled tenant bootstrap process.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Keep revision identifiers within the 32-character `alembic_version.version_num`
# limit established by the initial schema.  The filename remains descriptive.
revision: str = "0009_voice_contacts"
down_revision: str | None = "0008_outbound_stock_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "voice_contacts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("calling_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("consent_recorded_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'manager', 'supplier')", name="ck_voice_contact_role"
        ),
    )
    op.create_index("ix_voice_contacts_business_id", "voice_contacts", ["business_id"])
    op.create_index(
        "uq_voice_contact_business_phone", "voice_contacts", ["business_id", "phone"], unique=True
    )
    op.create_index(
        "ix_voice_contact_business_role",
        "voice_contacts",
        ["business_id", "role", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_contact_business_role", table_name="voice_contacts")
    op.drop_index("uq_voice_contact_business_phone", table_name="voice_contacts")
    op.drop_index("ix_voice_contacts_business_id", table_name="voice_contacts")
    op.drop_table("voice_contacts")
