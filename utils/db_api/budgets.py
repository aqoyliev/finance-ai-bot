"""Monthly spending limits per expense category (one limit per category, UZS or USD)."""
from typing import Dict, List, Optional

from sqlalchemy import delete, select

from .base import session_factory
from .common import CURRENCIES, InvalidValue, now
from .models import AlertSent, Budget, Category
from .reports import BudgetUsage, expense_by_category, get_usd_rate, period_bounds, spent_in_currency
from .users import get_user


async def list_budgets(user_id: int) -> Dict[str, Budget]:
    """The user's budgets by category name."""
    async with session_factory() as session:
        rows = await session.scalars(select(Budget).where(Budget.user_id == user_id).order_by(Budget.id))
        return {budget.category: budget for budget in rows}


async def get_budget(user_id: int, category: str) -> Optional[Budget]:
    async with session_factory() as session:
        return await session.scalar(select(Budget).where(Budget.user_id == user_id, Budget.category == category))


async def set_budget(user_id: int, category: str, currency: str, amount_minor: int) -> Budget:
    """Create or change the limit of an expense category. Alerts of the category start over."""
    if currency not in CURRENCIES or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise InvalidValue()
    async with session_factory() as session, session.begin():
        known = await session.scalar(select(Category.id).where(
            Category.user_id == user_id, Category.name == category, Category.kind == "expense"))
        if known is None:
            raise InvalidValue()
        budget = await session.scalar(select(Budget).where(Budget.user_id == user_id, Budget.category == category))
        stamp = now()
        if budget is None:
            budget = Budget(user_id=user_id, category=category, currency=currency, amount_minor=amount_minor,
                            created_at=stamp, updated_at=stamp)
            session.add(budget)
        else:
            budget.currency, budget.amount_minor, budget.updated_at = currency, amount_minor, stamp
        # A new limit means new thresholds: forget alerts that were sent for the old one
        await session.execute(delete(AlertSent).where(
            AlertSent.user_id == user_id, AlertSent.kind == "budget", AlertSent.ref == category))
        return budget


async def remove_budget(user_id: int, category: str) -> bool:
    async with session_factory() as session, session.begin():
        await session.execute(delete(AlertSent).where(
            AlertSent.user_id == user_id, AlertSent.kind == "budget", AlertSent.ref == category))
        result = await session.execute(delete(Budget).where(Budget.user_id == user_id, Budget.category == category))
        return result.rowcount > 0


async def budget_usages(user_id: int) -> List[BudgetUsage]:
    """Usage of every budget in the current financial period."""
    budgets = await list_budgets(user_id)
    if not budgets:
        return []
    user = await get_user(user_id)
    start, end = period_bounds(user.salary_day, now().date())
    by_category = await expense_by_category(user_id, start, end)
    rate = await get_usd_rate(user_id)
    return [BudgetUsage(b.category, b.currency, b.amount_minor, spent_in_currency(
        {cur: amount for (cur, name), amount in by_category.items() if name == b.category}, b.currency, rate))
        for b in budgets.values()]
