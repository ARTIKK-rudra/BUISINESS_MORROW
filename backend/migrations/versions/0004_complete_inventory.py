"""Add ingredient stock, inventory thresholds, batches, and goods receipts.

Revision ID: 0004_complete_inventory
Revises: 0003_transaction_constraints
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_complete_inventory"
down_revision: Union[str, None] = "0003_transaction_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ingredients") as batch:
        batch.add_column(
            sa.Column("minimum_stock", sa.Numeric(14, 3), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("maximum_stock", sa.Numeric(14, 3), nullable=True))
        batch.add_column(
            sa.Column("safety_stock", sa.Numeric(14, 3), nullable=False, server_default="0")
        )

    with op.batch_alter_table("inventory") as batch:
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("ingredient_id", sa.Uuid(), nullable=True))
        batch.add_column(
            sa.Column("minimum_stock", sa.Numeric(14, 3), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("maximum_stock", sa.Numeric(14, 3), nullable=True))
        batch.add_column(
            sa.Column("safety_stock", sa.Numeric(14, 3), nullable=False, server_default="0")
        )
        batch.create_foreign_key(
            "fk_inventory_ingredient", "ingredients", ["ingredient_id"], ["id"], ondelete="CASCADE"
        )
        batch.drop_index("uq_inventory_business_product_location")
        batch.create_check_constraint(
            "ck_inventory_exactly_one_stock_item",
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR (product_id IS NULL AND ingredient_id IS NOT NULL)",
        )
        batch.create_check_constraint(
            "ck_inventory_stock_thresholds", "minimum_stock >= 0 AND safety_stock >= 0"
        )
        batch.create_check_constraint(
            "ck_inventory_maximum_stock", "maximum_stock IS NULL OR maximum_stock >= minimum_stock"
        )
        batch.create_index(
            "uq_inventory_business_product_location",
            ["business_id", "product_id", "location"],
            unique=True,
            postgresql_where=sa.text("product_id IS NOT NULL"),
            sqlite_where=sa.text("product_id IS NOT NULL"),
        )
        batch.create_index(
            "uq_inventory_business_ingredient_location",
            ["business_id", "ingredient_id", "location"],
            unique=True,
            postgresql_where=sa.text("ingredient_id IS NOT NULL"),
            sqlite_where=sa.text("ingredient_id IS NOT NULL"),
        )
        batch.create_index("ix_inventory_ingredient_id", ["ingredient_id"])

    with op.batch_alter_table("supplier_products") as batch:
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("ingredient_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_supplier_products_ingredient",
            "ingredients",
            ["ingredient_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.drop_index("uq_supplier_product")
        batch.create_check_constraint(
            "ck_supplier_product_exactly_one_item",
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR (product_id IS NULL AND ingredient_id IS NOT NULL)",
        )
        batch.create_index(
            "uq_supplier_product_product",
            ["business_id", "supplier_id", "product_id"],
            unique=True,
            postgresql_where=sa.text("product_id IS NOT NULL"),
            sqlite_where=sa.text("product_id IS NOT NULL"),
        )
        batch.create_index(
            "uq_supplier_product_ingredient",
            ["business_id", "supplier_id", "ingredient_id"],
            unique=True,
            postgresql_where=sa.text("ingredient_id IS NOT NULL"),
            sqlite_where=sa.text("ingredient_id IS NOT NULL"),
        )
        batch.create_index("ix_supplier_products_ingredient_id", ["ingredient_id"])

    with op.batch_alter_table("purchase_items") as batch:
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("ingredient_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_purchase_items_ingredient",
            "ingredients",
            ["ingredient_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "ck_purchase_item_exactly_one_stock_item",
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR (product_id IS NULL AND ingredient_id IS NOT NULL)",
        )
        batch.create_index("ix_purchase_items_ingredient_id", ["ingredient_id"])

    with op.batch_alter_table("recipe_ingredients") as batch:
        batch.add_column(sa.Column("unit", sa.String(32), nullable=False, server_default="each"))
    op.execute(
        "UPDATE recipe_ingredients SET unit = "
        "(SELECT ingredients.unit FROM ingredients WHERE ingredients.id = recipe_ingredients.ingredient_id)"
    )

    op.create_table(
        "inventory_batches",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_id", sa.Uuid(), nullable=False),
        sa.Column("lot_code", sa.String(100), nullable=False),
        sa.Column("initial_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("quantity_remaining", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "initial_quantity > 0 AND quantity_remaining >= 0", name="ck_batch_nonnegative_quantity"
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventory.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_batches_business_id", "inventory_batches", ["business_id"])
    op.create_index("ix_inventory_batches_inventory_id", "inventory_batches", ["inventory_id"])
    op.create_index("ix_inventory_batch_expiry", "inventory_batches", ["business_id", "expires_on"])
    op.create_index(
        "uq_inventory_batch_lot",
        "inventory_batches",
        ["business_id", "inventory_id", "lot_code"],
        unique=True,
    )

    op.create_table(
        "supplier_price_history",
        sa.Column("supplier_product_id", sa.Uuid(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "effective_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["supplier_product_id"], ["supplier_products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_supplier_price_history_supplier_product_id",
        "supplier_price_history",
        ["supplier_product_id"],
    )
    op.create_index(
        "ix_supplier_price_product_date",
        "supplier_price_history",
        ["supplier_product_id", "effective_at"],
    )

    op.create_table(
        "goods_receipts",
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_id", sa.Uuid(), nullable=False),
        sa.Column("received_by", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_goods_receipts_business_id", "goods_receipts", ["business_id"])
    op.create_index("ix_goods_receipts_purchase_id", "goods_receipts", ["purchase_id"])
    op.create_index(
        "uq_receipt_business_idempotency",
        "goods_receipts",
        ["business_id", "idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_receipt_purchase_received", "goods_receipts", ["purchase_id", "received_at"]
    )

    op.create_table(
        "goods_receipt_items",
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_item_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_batch_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_goods_receipt_item_positive_quantity"),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_item_id"], ["purchase_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inventory_batch_id"], ["inventory_batches.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_goods_receipt_items_goods_receipt_id", "goods_receipt_items", ["goods_receipt_id"]
    )
    op.create_index(
        "ix_goods_receipt_items_purchase_item_id", "goods_receipt_items", ["purchase_item_id"]
    )
    op.create_index(
        "ix_goods_receipt_items_inventory_batch_id", "goods_receipt_items", ["inventory_batch_id"]
    )
    op.create_index(
        "uq_receipt_purchase_item",
        "goods_receipt_items",
        ["goods_receipt_id", "purchase_item_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("goods_receipt_items")
    op.drop_table("goods_receipts")
    op.drop_table("supplier_price_history")
    op.drop_table("inventory_batches")
    with op.batch_alter_table("recipe_ingredients") as batch:
        batch.drop_column("unit")
    with op.batch_alter_table("purchase_items") as batch:
        batch.drop_index("ix_purchase_items_ingredient_id")
        batch.drop_constraint("ck_purchase_item_exactly_one_stock_item", type_="check")
        batch.drop_constraint("fk_purchase_items_ingredient", type_="foreignkey")
        batch.drop_column("ingredient_id")
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=False)
    with op.batch_alter_table("supplier_products") as batch:
        batch.drop_index("ix_supplier_products_ingredient_id")
        batch.drop_index("uq_supplier_product_ingredient")
        batch.drop_index("uq_supplier_product_product")
        batch.drop_constraint("ck_supplier_product_exactly_one_item", type_="check")
        batch.drop_constraint("fk_supplier_products_ingredient", type_="foreignkey")
        batch.drop_column("ingredient_id")
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_index(
            "uq_supplier_product", ["business_id", "supplier_id", "product_id"], unique=True
        )
    with op.batch_alter_table("inventory") as batch:
        batch.drop_index("ix_inventory_ingredient_id")
        batch.drop_index("uq_inventory_business_ingredient_location")
        batch.drop_index("uq_inventory_business_product_location")
        batch.drop_constraint("ck_inventory_maximum_stock", type_="check")
        batch.drop_constraint("ck_inventory_stock_thresholds", type_="check")
        batch.drop_constraint("ck_inventory_exactly_one_stock_item", type_="check")
        batch.drop_constraint("fk_inventory_ingredient", type_="foreignkey")
        batch.drop_column("safety_stock")
        batch.drop_column("maximum_stock")
        batch.drop_column("minimum_stock")
        batch.drop_column("ingredient_id")
        batch.alter_column("product_id", existing_type=sa.Uuid(), nullable=False)
        batch.create_index(
            "uq_inventory_business_product_location",
            ["business_id", "product_id", "location"],
            unique=True,
        )
    with op.batch_alter_table("ingredients") as batch:
        batch.drop_column("safety_stock")
        batch.drop_column("maximum_stock")
        batch.drop_column("minimum_stock")
