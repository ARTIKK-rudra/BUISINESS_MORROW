from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LedgerEntry


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def profit_and_loss(
        self, business_id: UUID, start_date: date | None, end_date: date | None
    ) -> list[dict[str, Decimal | str]]:
        statement = select(
            LedgerEntry.currency,
            LedgerEntry.account,
            func.sum(LedgerEntry.debit),
            func.sum(LedgerEntry.credit),
        ).where(LedgerEntry.business_id == business_id)
        if start_date:
            statement = statement.where(
                LedgerEntry.occurred_at >= datetime.combine(start_date, time.min, tzinfo=UTC)
            )
        if end_date:
            statement = statement.where(
                LedgerEntry.occurred_at
                < datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=UTC)
            )
        statement = statement.group_by(LedgerEntry.currency, LedgerEntry.account)
        rows = (await self.session.execute(statement)).all()
        accounts: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
        for currency, account, debit, credit in rows:
            accounts.setdefault(currency, {})[account] = (Decimal(debit or 0), Decimal(credit or 0))

        reports = []
        for currency, lines in sorted(accounts.items()):
            revenue = lines.get("Sales Revenue", (Decimal(0), Decimal(0)))
            returns = lines.get("Sales Returns", (Decimal(0), Decimal(0)))
            cogs = lines.get("Cost of Goods Sold", (Decimal(0), Decimal(0)))
            sales_revenue = revenue[1] - revenue[0]
            sales_returns = returns[0] - returns[1]
            cost_of_goods = cogs[0] - cogs[1]
            operating_expenses = sum(
                (
                    debit - credit
                    for account, (debit, credit) in lines.items()
                    if account.startswith("Expense:")
                    or account in {"Inventory Shrinkage", "Inventory Wastage"}
                ),
                Decimal(0),
            )
            gross_profit = sales_revenue - sales_returns - cost_of_goods
            reports.append(
                {
                    "currency": currency,
                    "revenue": sales_revenue,
                    "refunds": sales_returns,
                    "cost_of_goods_sold": cost_of_goods,
                    "gross_profit": gross_profit,
                    "operating_expenses": operating_expenses,
                    "net_profit": gross_profit - operating_expenses,
                }
            )
        return reports
