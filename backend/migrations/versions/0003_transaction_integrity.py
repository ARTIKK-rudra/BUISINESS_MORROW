"""Add transaction idempotency and integrity constraints.

Revision ID: 0003_transaction_constraints
Revises: 0002_phase0_entities
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_transaction_constraints"
down_revision: Union[str, None] = "0002_phase0_entities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("purchases") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(100), nullable=True))
        batch.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_purchases_created_by_users", "users", ["created_by"], ["id"], ondelete="SET NULL"
        )
        batch.create_index(
            "uq_purchase_business_idempotency", ["business_id", "idempotency_key"], unique=True
        )
    with op.batch_alter_table("expenses") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(100), nullable=True))
        batch.create_check_constraint("ck_expense_positive_amount", "amount > 0")
        batch.create_index(
            "uq_expense_business_idempotency", ["business_id", "idempotency_key"], unique=True
        )
    with op.batch_alter_table("refunds") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(100), nullable=True))
        batch.create_check_constraint("ck_refund_positive_amount", "amount > 0")
        batch.create_index(
            "uq_refund_business_idempotency", ["business_id", "idempotency_key"], unique=True
        )
    with op.batch_alter_table("products") as batch:
        batch.create_check_constraint("ck_product_nonnegative_price", "price >= 0")
    with op.batch_alter_table("inventory") as batch:
        batch.add_column(
            sa.Column("unit_cost_average", sa.Numeric(12, 4), nullable=False, server_default="0")
        )
        batch.create_check_constraint("ck_inventory_nonnegative_quantity", "quantity >= 0")
        batch.create_check_constraint(
            "ck_inventory_nonnegative_unit_cost", "unit_cost_average >= 0"
        )
        batch.create_check_constraint(
            "ck_inventory_nonnegative_reorder_point", "reorder_point >= 0"
        )
    with op.batch_alter_table("inventory_movements") as batch:
        batch.create_check_constraint("ck_inventory_movement_nonzero_delta", "quantity_delta != 0")
    with op.batch_alter_table("orders") as batch:
        batch.create_check_constraint(
            "ck_order_nonnegative_totals",
            "subtotal >= 0 AND discount >= 0 AND tax >= 0 AND total >= 0",
        )
        batch.create_check_constraint(
            "ck_order_total_matches_components", "total = subtotal - discount + tax"
        )
    with op.batch_alter_table("order_items") as batch:
        batch.add_column(
            sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False, server_default="0")
        )
        batch.create_check_constraint(
            "ck_order_item_valid_amounts",
            "quantity > 0 AND unit_price >= 0 AND unit_cost >= 0 AND line_total >= 0",
        )
    with op.batch_alter_table("payments") as batch:
        batch.create_check_constraint("ck_payment_positive_amount", "amount > 0")
    with op.batch_alter_table("purchase_items") as batch:
        batch.create_check_constraint(
            "ck_purchase_item_valid_amounts",
            "quantity > 0 AND received_quantity >= 0 "
            "AND received_quantity <= quantity AND unit_cost > 0",
        )
    with op.batch_alter_table("purchases") as batch:
        batch.create_check_constraint("ck_purchase_nonnegative_total", "total >= 0")
    with op.batch_alter_table("ledger_entries") as batch:
        batch.create_check_constraint("ck_ledger_nonnegative_amounts", "debit >= 0 AND credit >= 0")
        batch.create_check_constraint(
            "ck_ledger_single_sided_line", "NOT (debit > 0 AND credit > 0)"
        )
        batch.create_index(
            "uq_ledger_source_account",
            ["business_id", "source_type", "source_id", "account"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("ledger_entries") as batch:
        batch.drop_index("uq_ledger_source_account")
        batch.drop_constraint("ck_ledger_single_sided_line", type_="check")
        batch.drop_constraint("ck_ledger_nonnegative_amounts", type_="check")
    with op.batch_alter_table("purchases") as batch:
        batch.drop_constraint("ck_purchase_nonnegative_total", type_="check")
    with op.batch_alter_table("purchase_items") as batch:
        batch.drop_constraint("ck_purchase_item_valid_amounts", type_="check")
    with op.batch_alter_table("payments") as batch:
        batch.drop_constraint("ck_payment_positive_amount", type_="check")
    with op.batch_alter_table("order_items") as batch:
        batch.drop_constraint("ck_order_item_valid_amounts", type_="check")
        batch.drop_column("unit_cost")
    with op.batch_alter_table("orders") as batch:
        batch.drop_constraint("ck_order_total_matches_components", type_="check")
        batch.drop_constraint("ck_order_nonnegative_totals", type_="check")
    with op.batch_alter_table("inventory_movements") as batch:
        batch.drop_constraint("ck_inventory_movement_nonzero_delta", type_="check")
    with op.batch_alter_table("inventory") as batch:
        batch.drop_constraint("ck_inventory_nonnegative_reorder_point", type_="check")
        batch.drop_constraint("ck_inventory_nonnegative_unit_cost", type_="check")
        batch.drop_constraint("ck_inventory_nonnegative_quantity", type_="check")
        batch.drop_column("unit_cost_average")
    with op.batch_alter_table("products") as batch:
        batch.drop_constraint("ck_product_nonnegative_price", type_="check")
    with op.batch_alter_table("refunds") as batch:
        batch.drop_index("uq_refund_business_idempotency")
        batch.drop_constraint("ck_refund_positive_amount", type_="check")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("expenses") as batch:
        batch.drop_index("uq_expense_business_idempotency")
        batch.drop_constraint("ck_expense_positive_amount", type_="check")
        batch.drop_column("idempotency_key")
    with op.batch_alter_table("purchases") as batch:
        batch.drop_index("uq_purchase_business_idempotency")
        batch.drop_constraint("fk_purchases_created_by_users", type_="foreignkey")
        batch.drop_column("created_by")
        batch.drop_column("idempotency_key")
