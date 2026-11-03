from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LedgerEntry


def add_journal(
    session: AsyncSession,
    *,
    business_id: UUID,
    source_type: str,
    source_id: UUID,
    debit_account: str,
    credit_account: str,
    amount: Decimal,
    currency: str,
) -> None:
    """Add balanced, system-generated double-entry journal lines."""
    if amount < 0:
        raise ValueError("Journal amount cannot be negative")
    session.add_all(
        [
            LedgerEntry(
                business_id=business_id,
                source_type=source_type,
                source_id=str(source_id),
                account=debit_account,
                debit=amount,
                credit=Decimal("0"),
                currency=currency,
            ),
            LedgerEntry(
                business_id=business_id,
                source_type=source_type,
                source_id=str(source_id),
                account=credit_account,
                debit=Decimal("0"),
                credit=amount,
                currency=currency,
            ),
        ]
    )
