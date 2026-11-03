from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.db.models import (
    Business,
    Expense,
    Supplier,
)
from app.repositories.operations import OperationsRepository
from app.schemas.finance import ExpenseCreate
from app.schemas.procurement import SupplierCreate
from app.services.accounting import add_journal
from app.services.audit import add_audit_entry


class OperationsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = OperationsRepository(session)

    async def list_suppliers(self, business_id: UUID) -> list[Supplier]:
        return await self.repository.list_suppliers(business_id)

    async def create_supplier(
        self, business_id: UUID, actor_id: UUID, payload: SupplierCreate, request_id: str | None
    ) -> Supplier:
        supplier = Supplier(
            business_id=business_id,
            name=payload.name.strip(),
            email=str(payload.email).lower() if payload.email else None,
            contact_name=payload.contact_name,
        )
        self.session.add(supplier)
        await self.session.flush()
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="supplier.created",
            entity_type="supplier",
            entity_id=supplier.id,
            request_id=request_id,
        )
        await self.session.commit()
        await self.session.refresh(supplier)
        return supplier

    async def list_expenses(self, business_id: UUID, limit: int, offset: int) -> list[Expense]:
        return await self.repository.list_expenses(business_id, limit, offset)

    async def create_expense(
        self, business_id: UUID, actor_id: UUID, payload: ExpenseCreate, request_id: str | None
    ) -> Expense:
        base_currency = await self.session.scalar(
            select(Business.base_currency).where(Business.id == business_id)
        )
        if payload.currency != base_currency:
            raise ConflictError("Expense currency must match the business base currency")
        if payload.idempotency_key:
            existing = await self.session.scalar(
                select(Expense).where(
                    Expense.business_id == business_id,
                    Expense.idempotency_key == payload.idempotency_key,
                )
            )
            if existing:
                return existing
        expense = Expense(
            business_id=business_id,
            category=payload.category.strip(),
            description=payload.description.strip(),
            amount=payload.amount,
            currency=payload.currency,
            occurred_at=payload.occurred_at or datetime.now(UTC),
            idempotency_key=payload.idempotency_key,
        )
        self.session.add(expense)
        await self.session.flush()
        add_journal(
            self.session,
            business_id=business_id,
            source_type="expense",
            source_id=expense.id,
            debit_account=f"Expense: {expense.category}",
            credit_account="Cash",
            amount=expense.amount,
            currency=expense.currency,
        )
        add_audit_entry(
            self.session,
            business_id=business_id,
            actor_user_id=actor_id,
            action="expense.created",
            entity_type="expense",
            entity_id=expense.id,
            request_id=request_id,
            metadata={"amount": str(expense.amount), "currency": expense.currency},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.idempotency_key:
                existing = await self.session.scalar(
                    select(Expense).where(
                        Expense.business_id == business_id,
                        Expense.idempotency_key == payload.idempotency_key,
                    )
                )
                if existing:
                    return existing
            raise ConflictError("Expense conflicts with an existing request") from exc
        await self.session.refresh(expense)
        return expense

    async def list_ledger(self, business_id: UUID, limit: int, offset: int):
        return await self.repository.list_ledger(business_id, limit, offset)
