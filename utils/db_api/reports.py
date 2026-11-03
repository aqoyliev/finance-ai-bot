from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select

from .base import session_factory
from .common import OPERATION_KINDS, now
from .models import Account, ExchangeRate, Transaction, User


@dataclass
class Report:
    start: date
    totals: Dict[Tuple[str, str], int]  # (kind, currency) -> minor units; transfers excluded
    accounts: List[Account]
    usd_rate: Optional[str]


def period_start(salary_day: int, today: date) -> date:
    """First day of the current financial month (it begins on the salary day)."""
    day = min(salary_day, 28)
    if today.day >= day:
        return date(today.year, today.month, day)
    if today.month == 1:
        return date(today.year - 1, 12, day)
    return date(today.year, today.month - 1, day)


async def period_totals(user_id: int, start: date) -> Dict[Tuple[str, str], int]:
    """Income and expense sums since start. Transfers between own accounts are not counted."""
    async with session_factory() as session:
        rows = await session.execute(
            select(Transaction.kind, Transaction.currency, func.sum(Transaction.amount_minor))
            .where(Transaction.user_id == user_id,
                   Transaction.kind.in_(OPERATION_KINDS),
                   Transaction.occurred_at >= datetime.combine(start, datetime.min.time()))
            .group_by(Transaction.kind, Transaction.currency))
        return {(kind, currency): total or 0 for kind, currency, total in rows.all()}


async def build_report(user_id: int) -> Report:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        start = period_start(user.salary_day, now().date())
        accounts = list(await session.scalars(
            select(Account).where(Account.user_id == user_id, Account.is_active.is_(True)).order_by(Account.id)))
        rate = await session.get(ExchangeRate, (user_id, "USD", "UZS"))
    totals = await period_totals(user_id, start)
    return Report(start=start, totals=totals, accounts=accounts, usd_rate=rate.rate if rate else None)
