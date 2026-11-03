"""Limit alerts: category budgets and credit card limits reaching 80% and 100% of the limit.

check_alerts is the single place that decides what to tell the user. Each (subject, threshold) is reported
once per financial period; the fact is stored in `alerts_sent`, keyed by the period start, so the next
period starts clean on its own. Deleting or lowering an expense does not un-send anything, and a later
re-crossing inside the same period is not announced again. When one change jumps over both thresholds
(e.g. 50% -> 120%) only the highest one is reported, but both are marked as sent. Changing or removing a
budget limit clears the alerts of that category (see budgets.set_budget).
"""
from dataclasses import dataclass
from datetime import date
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .accounts import debt
from .base import session_factory
from .common import now
from .models import Account, AlertSent, Budget, User
from .reports import expense_by_category, get_usd_rate, period_bounds, spent_in_currency

THRESHOLDS = (80, 100)


@dataclass
class Alert:
    kind: str  # budget | credit
    threshold: int  # 80 | 100
    name: str  # category name or account name
    currency: str
    used: int  # spent in the category / current debt, minor units
    limit: int

    @property
    def percent(self) -> int:
        return self.used * 100 // self.limit if self.limit else 0


async def _register(session: AsyncSession, user_id: int, kind: str, ref: str, used: int, limit: int,
                    period: date) -> Optional[int]:
    """Mark the thresholds reached by used/limit as sent; return the highest newly reached one."""
    reached = [th for th in THRESHOLDS if used * 100 >= limit * th]
    if not reached:
        return None
    sent = set(await session.scalars(select(AlertSent.threshold).where(
        AlertSent.user_id == user_id, AlertSent.kind == kind, AlertSent.ref == ref,
        AlertSent.period_start == period)))
    new = [th for th in reached if th not in sent]
    for th in new:
        session.add(AlertSent(user_id=user_id, kind=kind, ref=ref, threshold=th, period_start=period,
                              sent_at=now()))
    return max(new) if new else None


async def check_alerts(user_id: int, categories: Iterable[str] = (), account_ids: Iterable[int] = (),
                       already_warned: Iterable[int] = ()) -> List[Alert]:
    """Alerts newly earned by the given expense categories (budgets) and accounts (credit limits).

    already_warned: credit account ids whose over-the-limit state the user was just told about by the
    save confirmation; their 100% alert is recorded but not returned, so it is not said twice.
    """
    categories, account_ids, warned = list(dict.fromkeys(categories)), set(account_ids), set(already_warned)
    alerts: List[Alert] = []
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        start, end = period_bounds(user.salary_day, now().date())

        budgets = []
        if categories:
            budgets = list(await session.scalars(select(Budget).where(
                Budget.user_id == user_id, Budget.category.in_(categories))))
        if budgets:
            rate = await get_usd_rate(user_id)
            by_category = await expense_by_category(user_id, start, end)
            for budget in budgets:
                spent = spent_in_currency(
                    {cur: amount for (cur, name), amount in by_category.items() if name == budget.category},
                    budget.currency, rate)
                threshold = await _register(session, user_id, "budget", budget.category, spent,
                                            budget.amount_minor, start)
                if threshold:
                    alerts.append(Alert("budget", threshold, budget.category, budget.currency, spent,
                                        budget.amount_minor))

        cards = []
        if account_ids:
            cards = list(await session.scalars(select(Account).where(
                Account.user_id == user_id, Account.id.in_(account_ids), Account.kind == "credit",
                Account.is_active.is_(True), Account.credit_limit_minor > 0).order_by(Account.id)))
        for card in cards:
            threshold = await _register(session, user_id, "credit", str(card.id), debt(card),
                                        card.credit_limit_minor, start)
            if threshold and not (threshold == 100 and card.id in warned):
                alerts.append(Alert("credit", threshold, card.name, card.currency, debt(card),
                                    card.credit_limit_minor))
    return alerts
