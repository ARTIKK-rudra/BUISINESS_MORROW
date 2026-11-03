from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKey


class Business(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "businesses"
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BusinessMembership(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "business_memberships"
    __table_args__ = (Index("uq_membership_business_user", "business_id", "user_id", unique=True),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False, default="staff")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Ingredient(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "ingredients"
    __table_args__ = (Index("uq_ingredient_business_sku", "business_id", "sku", unique=True),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    minimum_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Recipe(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        Index("uq_recipe_business_product", "business_id", "product_id", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    yield_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    yield_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(UUIDPrimaryKey, Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (Index("uq_recipe_ingredient", "recipe_id", "ingredient_id", unique=True),)
    recipe_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


class Category(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (Index("uq_category_business_name", "business_id", "name", unique=True),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )


class Product(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_product_nonnegative_price"),
        Index("uq_product_business_sku", "business_id", "sku", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    sku: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="each")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Inventory(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_inventory_nonnegative_quantity"),
        CheckConstraint("unit_cost_average >= 0", name="ck_inventory_nonnegative_unit_cost"),
        CheckConstraint("reorder_point >= 0", name="ck_inventory_nonnegative_reorder_point"),
        CheckConstraint(
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR "
            "(product_id IS NULL AND ingredient_id IS NOT NULL)",
            name="ck_inventory_exactly_one_stock_item",
        ),
        CheckConstraint(
            "minimum_stock >= 0 AND safety_stock >= 0", name="ck_inventory_stock_thresholds"
        ),
        CheckConstraint(
            "maximum_stock IS NULL OR maximum_stock >= minimum_stock",
            name="ck_inventory_maximum_stock",
        ),
        Index(
            "uq_inventory_business_product_location",
            "business_id",
            "product_id",
            "location",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL"),
            sqlite_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "uq_inventory_business_ingredient_location",
            "business_id",
            "ingredient_id",
            "location",
            unique=True,
            postgresql_where=text("ingredient_id IS NOT NULL"),
            sqlite_where=text("ingredient_id IS NOT NULL"),
        ),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    location: Mapped[str] = mapped_column(String(120), nullable=False, default="Main")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=Decimal("0"))
    unit_cost_average: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0")
    )
    reorder_point: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    minimum_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    maximum_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    safety_stock: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    expires_on: Mapped[date | None] = mapped_column(Date)


class InventoryMovement(UUIDPrimaryKey, Base):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity_delta != 0", name="ck_inventory_movement_nonzero_delta"),
        Index("ix_inventory_movement_business_created", "business_id", "created_at"),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    inventory_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory.id", ondelete="CASCADE"), index=True
    )
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(120))
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InventoryBatch(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "inventory_batches"
    __table_args__ = (
        CheckConstraint(
            "initial_quantity > 0 AND quantity_remaining >= 0", name="ck_batch_nonnegative_quantity"
        ),
        Index("ix_inventory_batch_expiry", "business_id", "expires_on"),
        Index("uq_inventory_batch_lot", "business_id", "inventory_id", "lot_code", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    inventory_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory.id", ondelete="CASCADE"), index=True
    )
    lot_code: Mapped[str] = mapped_column(String(100), nullable=False)
    initial_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_remaining: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    expires_on: Mapped[date | None] = mapped_column(Date)


class Supplier(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "suppliers"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    contact_name: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SupplierProduct(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "supplier_products"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL) != (ingredient_id IS NOT NULL)",
            name="ck_supplier_product_exactly_one_item",
        ),
        Index(
            "uq_supplier_product_product",
            "business_id",
            "supplier_id",
            "product_id",
            unique=True,
            postgresql_where=text("product_id IS NOT NULL"),
            sqlite_where=text("product_id IS NOT NULL"),
        ),
        Index(
            "uq_supplier_product_ingredient",
            "business_id",
            "supplier_id",
            "ingredient_id",
            unique=True,
            postgresql_where=text("ingredient_id IS NOT NULL"),
            sqlite_where=text("ingredient_id IS NOT NULL"),
        ),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    minimum_order_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )


class SupplierPriceHistory(UUIDPrimaryKey, Base):
    __tablename__ = "supplier_price_history"
    __table_args__ = (
        Index("ix_supplier_price_product_date", "supplier_product_id", "effective_at"),
    )
    supplier_product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("supplier_products.id", ondelete="CASCADE"), index=True
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Customer(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "customers"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    consent_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unknown")


class Order(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "subtotal >= 0 AND discount >= 0 AND tax >= 0 AND total >= 0",
            name="ck_order_nonnegative_totals",
        ),
        CheckConstraint(
            "total = subtotal - discount + tax", name="ck_order_total_matches_components"
        ),
        Index("ix_order_business_placed", "business_id", "placed_at"),
        Index("uq_order_business_idempotency", "business_id", "idempotency_key", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(UUIDPrimaryKey, Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND unit_cost >= 0 AND line_total >= 0",
            name="ck_order_item_valid_amounts",
        ),
    )
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT")
    )
    product_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    order: Mapped[Order] = relationship(back_populates="items")


class Payment(UUIDPrimaryKey, TimestampMixin, Base):
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_positive_amount"),)
    __tablename__ = "payments"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    provider_reference: Mapped[str | None] = mapped_column(String(180), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    method: Mapped[str | None] = mapped_column(String(40))


class Refund(UUIDPrimaryKey, TimestampMixin, Base):
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refund_positive_amount"),
        Index("uq_refund_business_idempotency", "business_id", "idempotency_key", unique=True),
    )
    __tablename__ = "refunds"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    payment_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))


class Purchase(UUIDPrimaryKey, TimestampMixin, Base):
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_purchase_nonnegative_total"),
        Index("uq_purchase_business_idempotency", "business_id", "idempotency_key", unique=True),
    )
    __tablename__ = "purchases"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    supplier_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    items: Mapped[list["PurchaseItem"]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan"
    )


class PurchaseItem(UUIDPrimaryKey, Base):
    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND ingredient_id IS NULL) OR "
            "(product_id IS NULL AND ingredient_id IS NOT NULL)",
            name="ck_purchase_item_exactly_one_stock_item",
        ),
        CheckConstraint(
            "quantity > 0 AND received_quantity >= 0 "
            "AND received_quantity <= quantity AND unit_cost > 0",
            name="ck_purchase_item_valid_amounts",
        ),
    )
    purchase_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT")
    )
    ingredient_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT")
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, default=Decimal("0")
    )
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    purchase: Mapped[Purchase] = relationship(back_populates="items")


class GoodsReceipt(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index("uq_receipt_business_idempotency", "business_id", "idempotency_key", unique=True),
        Index("ix_receipt_purchase_received", "purchase_id", "received_at"),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    purchase_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="RESTRICT"), index=True
    )
    received_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    items: Mapped[list["GoodsReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class GoodsReceiptItem(UUIDPrimaryKey, Base):
    __tablename__ = "goods_receipt_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_goods_receipt_item_positive_quantity"),
        Index("uq_receipt_purchase_item", "goods_receipt_id", "purchase_item_id", unique=True),
    )
    goods_receipt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True
    )
    purchase_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchase_items.id", ondelete="RESTRICT"), index=True
    )
    inventory_batch_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventory_batches.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    receipt: Mapped[GoodsReceipt] = relationship(back_populates="items")


class Invoice(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("uq_invoice_business_number", "business_id", "invoice_number", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), index=True
    )
    supplier_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True
    )
    invoice_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="issued")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(UUIDPrimaryKey, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND unit_price >= 0", name="ck_invoice_line_amounts"),
        Index("ix_invoice_lines_invoice", "invoice_id"),
    )
    invoice_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class InvoiceCapture(UUIDPrimaryKey, TimestampMixin, Base):
    """OCR draft; confirmation is required before it becomes an invoice."""

    __tablename__ = "invoice_captures"
    __table_args__ = (Index("ix_invoice_capture_business_status", "business_id", "status"),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    confirmed_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    invoice_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="review_required")
    ocr_engine: Mapped[str] = mapped_column(String(60), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    draft: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Expense(UUIDPrimaryKey, TimestampMixin, Base):
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_positive_amount"),
        Index("uq_expense_business_idempotency", "business_id", "idempotency_key", unique=True),
    )
    __tablename__ = "expenses"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100))


class LedgerEntry(UUIDPrimaryKey, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="ck_ledger_nonnegative_amounts"),
        CheckConstraint("NOT (debit > 0 AND credit > 0)", name="ck_ledger_single_sided_line"),
        Index(
            "uq_ledger_source_account",
            "business_id",
            "source_type",
            "source_id",
            "account",
            unique=True,
        ),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    account: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_business_created", "business_id", "created_at"),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100))
    request_id: Mapped[str | None] = mapped_column(String(80))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(UUIDPrimaryKey, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_delivery",
            "published_at",
            "dead_lettered_at",
            "next_attempt_at",
            "locked_until",
            "created_at",
        ),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventConsumerReceipt(Base):
    __tablename__ = "event_consumer_receipts"
    __table_args__ = (Index("ix_event_receipts_retry", "consumer_name", "processed_at"),)
    event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class RealtimeEvent(UUIDPrimaryKey, Base):
    __tablename__ = "realtime_events"
    __table_args__ = (
        Index("ix_realtime_business_created", "business_id", "created_at"),
        Index("ix_realtime_business_sequence", "business_id", "stream_sequence"),
    )
    stream_sequence: Mapped[int] = mapped_column(
        BigInteger, Identity(start=1), nullable=False, unique=True
    )
    source_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RealtimeBusinessMetric(Base):
    __tablename__ = "realtime_business_metrics"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    event_counts: Mapped[dict[str, int]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    amount_totals: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MLEventTask(Base):
    __tablename__ = "ml_event_tasks"
    __table_args__ = (
        Index(
            "ix_ml_event_tasks_status_created",
            "status",
            "next_attempt_at",
            "locked_until",
            "created_at",
        ),
    )
    source_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("uq_notification_source_event", "source_event_id", unique=True),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    recipient_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    channel: Mapped[str] = mapped_column(String(24), nullable=False, default="in_app")
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    source_event_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))


class VoiceInteraction(UUIDPrimaryKey, Base):
    __tablename__ = "voice_interactions"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider_session: Mapped[str | None] = mapped_column(String(180))
    transcript: Mapped[str | None] = mapped_column(Text)
    consent_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoiceContact(UUIDPrimaryKey, TimestampMixin, Base):
    """An approved operational contact for a tenant's voice workflow."""

    __tablename__ = "voice_contacts"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'manager', 'supplier')", name="ck_voice_contact_role"),
        Index("uq_voice_contact_business_phone", "business_id", "phone", unique=True),
        Index("ix_voice_contact_business_role", "business_id", "role", "is_active"),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    calling_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProvisionCase(UUIDPrimaryKey, TimestampMixin, Base):
    """A local or live-ready provision workflow; conversations retain the transcript turns."""

    __tablename__ = "provision_cases"
    __table_args__ = (
        Index("ix_provision_case_business_status", "business_id", "status", "created_at"),
        Index("uq_provision_case_business_key", "business_id", "idempotency_key", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    owner_contact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voice_contacts.id", ondelete="RESTRICT"), index=True
    )
    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="awaiting_owner")
    demo_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shortage_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manager_recommendations: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    supplier_quote: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approval: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    purchase_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="SET NULL"), unique=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VoiceConversation(UUIDPrimaryKey, TimestampMixin, Base):
    """Durable state for one permission-controlled provision call."""

    __tablename__ = "voice_conversations"
    __table_args__ = (
        CheckConstraint(
            "workflow IN ('owner_shortage_authorization', 'manager_quantity_collection', "
            "'supplier_quotation', 'owner_purchase_authorization')",
            name="ck_voice_conversation_workflow",
        ),
        Index("ix_voice_conversation_business_status", "business_id", "status", "created_at"),
        Index("uq_voice_conversation_call_sid", "provider_call_sid", unique=True),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voice_contacts.id", ondelete="RESTRICT"), index=True
    )
    workflow: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="initiated", server_default=text("'initiated'")
    )
    provider_call_sid: Mapped[str | None] = mapped_column(String(40))
    shortage_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    supplier_contact_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    purchase_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    turn_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VoiceConversationTurn(UUIDPrimaryKey, Base):
    __tablename__ = "voice_conversation_turns"
    __table_args__ = (Index("ix_voice_turn_conversation_created", "conversation_id", "created_at"),)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voice_conversations.id", ondelete="CASCADE"), index=True
    )
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    structured_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VoiceAlertSettings(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "voice_alert_settings"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), unique=True
    )
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class VoiceCallTask(UUIDPrimaryKey, Base):
    __tablename__ = "voice_call_tasks"
    __table_args__ = (
        Index("uq_voice_call_event", "source_event_id", unique=True),
        Index("ix_voice_call_delivery", "status", "next_attempt_at", "locked_until", "created_at"),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    source_event_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default=text("'pending'")
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_call_sid: Mapped[str | None] = mapped_column(String(40))
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Forecast(UUIDPrimaryKey, Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        Index(
            "ix_forecast_business_target_period",
            "business_id",
            "target_type",
            "target_id",
            "period_start",
        ),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    point_value: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    lower_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    upper_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelVersion(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        Index(
            "uq_model_version_business_type_version",
            "business_id",
            "model_type",
            "version",
            unique=True,
        ),
        Index("ix_model_version_business_type_created", "business_id", "model_type", "created_at"),
    )
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    model_type: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="evaluated")
    dataset_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_names: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_uri: Mapped[str | None] = mapped_column(String(500))
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Prediction(UUIDPrimaryKey, Base):
    __tablename__ = "predictions"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    predicted_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 5))
    probability: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Anomaly(UUIDPrimaryKey, Base):
    __tablename__ = "anomalies"
    __table_args__ = (Index("ix_anomaly_business_created", "business_id", "created_at"),)
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False, default="robust_mad_v1")
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Recommendation(UUIDPrimaryKey, Base):
    __tablename__ = "recommendations"
    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    recommendation_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str] = mapped_column(String(60), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_purchase_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("purchases.id", ondelete="SET NULL"), unique=True
    )
