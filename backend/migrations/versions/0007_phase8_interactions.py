"""Add reviewed OCR invoice captures."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase8_interactions"
down_revision: str | None = "0006_realtime_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("recommendations") as batch:
        batch.add_column(sa.Column("approved_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("executed_purchase_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_recommendation_approver", "users", ["approved_by"], ["id"], ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "fk_recommendation_purchase",
            "purchases",
            ["executed_purchase_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_recommendation_executed_purchase", ["executed_purchase_id"]
        )
    with op.batch_alter_table("invoices") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_invoice_supplier", "suppliers", ["supplier_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index("ix_invoices_supplier_id", ["supplier_id"])
    op.create_table(
        "invoice_captures",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "business_id",
            sa.Uuid(),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "confirmed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "invoice_id", sa.Uuid(), sa.ForeignKey("invoices.id", ondelete="SET NULL"), unique=True
        ),
        sa.Column("status", sa.String(24), nullable=False, server_default="review_required"),
        sa.Column("ocr_engine", sa.String(60), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_invoice_captures_business_id", "invoice_captures", ["business_id"])
    op.create_index(
        "ix_invoice_capture_business_status", "invoice_captures", ["business_id", "status"]
    )
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "invoice_id",
            sa.Uuid(),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0 AND unit_price >= 0", name="ck_invoice_line_amounts"),
    )
    op.create_index("ix_invoice_lines_invoice", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_invoice", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_invoice_capture_business_status", table_name="invoice_captures")
    op.drop_index("ix_invoice_captures_business_id", table_name="invoice_captures")
    op.drop_table("invoice_captures")
    with op.batch_alter_table("recommendations") as batch:
        batch.drop_constraint("uq_recommendation_executed_purchase", type_="unique")
        batch.drop_constraint("fk_recommendation_purchase", type_="foreignkey")
        batch.drop_constraint("fk_recommendation_approver", type_="foreignkey")
        batch.drop_column("executed_purchase_id")
        batch.drop_column("approved_at")
        batch.drop_column("approved_by")
    with op.batch_alter_table("invoices") as batch:
        batch.drop_index("ix_invoices_supplier_id")
        batch.drop_constraint("fk_invoice_supplier", type_="foreignkey")
        batch.drop_column("supplier_id")
