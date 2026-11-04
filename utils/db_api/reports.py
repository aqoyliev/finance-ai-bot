"""Financial-period reports: totals, expenses by category, comparison with the previous period.

A financial period starts on the user's salary day (capped at 28, so every month has that day) and
lasts until the next salary day. Period offsets are relative to the current one: 0 = current,
-1 = previous, and so on; the future is never shown.

Comparison rule: while a period is still running, it is compared with the *same number of days* from the
start of the previous period (day 10 of this period vs days 1-10 of the previous one), so a half-finished
month is not compared with a whole one. A completed period is compared with the whole previous period.
Transfers between own accounts are never part of income or expenses.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select

from utils import rates

from .base import session_factory
from .common import CURRENCIES, OPERATION_KINDS, now
from .models import Account, Budget, ExchangeRate, Transaction, User

NO_CATEGORY = "—"


# ---- Pure helpers ----

def period_start(salary_day: int, today: date) -> date:
    """First day of the current financial month (it begins on the salary day)."""
    day = min(salary_day, 28)
    if today.day >= day:
        return date(today.year, today.month, day)
    if today.month == 1:
        return date(today.year - 1, 12, day)
    return date(today.year, today.month - 1, day)


def shift_period(start: date, months: int) -> date:
    """Start of the period `months` periods after (negative: before) the period starting on `start`."""
    index = start.year * 12 + (start.month - 1) + months
    return date(index // 12, index % 12 + 1, start.day)


def period_bounds(salary_day: int, today: date, offset: int = 0) -> Tuple[date, date]:
    """(first day, first day of the next period) of the period `offset` periods from the current one."""
    base = period_start(salary_day, today)
    return shift_period(base, offset), shift_period(base, offset + 1)


def comparison_window(start: date, end: date, today: date) -> Tuple[date, date]:
    """[from, to) range of the previous period that the period [start, end) is compared with."""
    prev_start = shift_period(start, -1)
    if today >= end:  # completed period: compare with the whole previous one
        return prev_start, start
    elapsed = max((today - start).days + 1, 1)  # days of this period so far, today included
    return prev_start, min(prev_start + timedelta(days=elapsed), start)


def change_percent(current: int, previous: int) -> Optional[int]:
    """Relative change in whole percent, or None when there is nothing to compare with."""
    if previous <= 0:
        return None
    return round((current - previous) * 100 / previous)


def share_percent(part: int, total: int) -> int:
    return round(part * 100 / total) if total > 0 else 0


def parse_rate(value: Optional[str]) -> Optional[Decimal]:
    try:
        rate = Decimal(value) if value else None
    except InvalidOperation:
        return None
    return rate if rate and rate.is_finite() and rate > 0 else None


def convert(minor: int, from_currency: str, to_currency: str, usd_rate: Optional[Decimal]) -> int:
    """Convert minor units between UZS and USD at `usd_rate` (UZS per USD); 0 if a rate is needed but unset."""
    if from_currency == to_currency:
        return minor
    if not usd_rate:
        return 0
    return int(round(minor * usd_rate)) if to_currency == "UZS" else int(round(minor / usd_rate))


def spent_in_currency(by_currency: Dict[str, int], currency: str, usd_rate: Optional[Decimal]) -> int:
    """Spending in `currency`; amounts in the other currency are converted when a rate is set."""
    return sum(convert(amount, cur, currency, usd_rate) for cur, amount in by_currency.items())


def day_start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time())


# ---- Data classes ----

@dataclass
class CategoryRow:
    name: str
    amount: int
    share: int  # percent of the currency's expenses
    prev_amount: int

    @property
    def change(self) -> Optional[int]:
        return change_percent(self.amount, self.prev_amount)


@dataclass
class CurrencySummary:
    currency: str
    income: int
    expense: int
    prev_expense: int
    categories: List[CategoryRow] = field(default_factory=list)  # biggest first

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def expense_change(self) -> Optional[int]:
        return change_percent(self.expense, self.prev_expense)


@dataclass
class Combined:
    """All currencies converted to UZS at the user's USD rate."""
    income: int
    expense: int
    prev_expense: int
    rate: Decimal

    @property
    def balance(self) -> int:
        return self.income - self.expense

    @property
    def expense_change(self) -> Optional[int]:
        return change_percent(self.expense, self.prev_expense)


@dataclass
class BudgetUsage:
    category: str
    currency: str
    limit: int
    spent: int

    @property
    def percent(self) -> int:
        return self.spent * 100 // self.limit if self.limit else 0


@dataclass
class Report:
    start: date
    totals: Dict[Tuple[str, str], int]  # (kind, currency) -> minor units; transfers excluded
    accounts: List[Account]
    usd_rate: Optional[str]


@dataclass
class PeriodReport:
    offset: int
    start: date
    end: date  # first day of the next period (exclusive)
    compare_start: date
    compare_end: date  # exclusive
    is_current: bool
    has_earlier: bool  # there are operations before this period
    currencies: List[CurrencySummary]
    combined: Optional[Combined]
    usd_rate: Optional[Decimal]
    budgets: List[BudgetUsage]
    today: date

    @property
    def last_day(self) -> date:
        return self.end - timedelta(days=1)

    @property
    def through(self) -> date:
        """Last day the report covers so far: today for the current period, else the last day."""
        return min(self.last_day, self.today)

    @property
    def compare_last_day(self) -> date:
        return self.compare_end - timedelta(days=1)

    def chart_series(self) -> Optional[Tuple[str, List[Tuple[str, int]], bool]]:
        """(currency, [(category, minor)], converted) to draw as the expense chart, or None without expenses.

        With a USD rate and expenses in both currencies, everything is summed in UZS (converted=True);
        otherwise the first currency that has expenses is charted."""
        spending = [s for s in self.currencies if s.expense > 0]
        if not spending:
            return None
        if self.combined and len(spending) > 1:
            totals: Dict[str, int] = {}
            for summary in spending:
                for row in summary.categories:
                    totals[row.name] = totals.get(row.name, 0) + convert(
                        row.amount, summary.currency, "UZS", self.usd_rate)
            return "UZS", list(totals.items()), True
        summary = spending[0]
        return summary.currency, [(row.name, row.amount) for row in summary.categories], False

    @property
    def has_data(self) -> bool:
        return any(c.income or c.expense for c in self.currencies)


# ---- Queries ----

def _range(query, start: date, end: Optional[date]):
    query = query.where(Transaction.occurred_at >= day_start(start))
    return query.where(Transaction.occurred_at < day_start(end)) if end else query


async def period_totals(user_id: int, start: date, end: Optional[date] = None) -> Dict[Tuple[str, str], int]:
    """Income and expense sums from `start` (until `end` if given). Transfers are not counted."""
    async with session_factory() as session:
        rows = await session.execute(_range(
            select(Transaction.kind, Transaction.currency, func.sum(Transaction.amount_minor))
            .where(Transaction.user_id == user_id, Transaction.kind.in_(OPERATION_KINDS)), start, end)
            .group_by(Transaction.kind, Transaction.currency))
        return {(kind, currency): total or 0 for kind, currency, total in rows.all()}


async def expense_by_category(user_id: int, start: date, end: Optional[date] = None,
                              category: Optional[str] = None) -> Dict[Tuple[str, str], int]:
    """Expense sums: (currency, category) -> minor units; uncategorized rows use NO_CATEGORY."""
    label = func.coalesce(Transaction.category, NO_CATEGORY)
    query = select(Transaction.currency, label, func.sum(Transaction.amount_minor)).where(
        Transaction.user_id == user_id, Transaction.kind == "expense")
    if category is not None:
        query = query.where(Transaction.category == category)
    async with session_factory() as session:
        rows = await session.execute(_range(query, start, end).group_by(Transaction.currency, label))
        return {(currency, name): total or 0 for currency, name, total in rows.all()}


async def expense_by_subcategory(user_id: int, category: str, start: date,
                                 end: Optional[date] = None) -> Dict[str, List[Tuple[str, int]]]:
    """Expenses of one category split by subcategory: currency -> [(subcategory, minor)], biggest first."""
    label = func.coalesce(Transaction.subcategory, NO_CATEGORY)
    query = select(Transaction.currency, label, func.sum(Transaction.amount_minor)).where(
        Transaction.user_id == user_id, Transaction.kind == "expense", Transaction.category == category)
    async with session_factory() as session:
        rows = await session.execute(_range(query, start, end).group_by(Transaction.currency, label))
        result: Dict[str, List[Tuple[str, int]]] = {}
        for currency, name, total in rows.all():
            result.setdefault(currency, []).append((name, total or 0))
    for items in result.values():
        items.sort(key=lambda item: (-item[1], item[0]))
    return result


@dataclass(frozen=True)
class UsdRate:
    """The USD -> UZS rate in use and where it comes from."""
    rate: Decimal
    source: str  # "cbu" (official, set by the Central Bank for `day`) | "manual" (the user's /rate override)
    day: Optional[date] = None


async def get_usd_rate_info(user_id: int) -> Optional[UsdRate]:
    """The user's manual /rate override if set, otherwise the Central Bank rate; None if neither is known."""
    async with session_factory() as session:
        row = await session.get(ExchangeRate, (user_id, "USD", "UZS"))
    manual = parse_rate(row.rate) if row else None
    if manual:
        return UsdRate(manual, "manual", row.updated_at.date())
    official = await rates.get_official()
    return UsdRate(official.rate, "cbu", official.day) if official else None


async def get_usd_rate(user_id: int) -> Optional[Decimal]:
    info = await get_usd_rate_info(user_id)
    return info.rate if info else None


async def _has_earlier(user_id: int, before: date) -> bool:
    async with session_factory() as session:
        found = await session.scalar(
            select(Transaction.id).where(Transaction.user_id == user_id, Transaction.kind.in_(OPERATION_KINDS),
                                         Transaction.occurred_at < day_start(before)).limit(1))
    return found is not None


async def build_report(user_id: int) -> Report:
    """Plain totals of the current period plus account balances."""
    async with session_factory() as session:
        user = await session.get(User, user_id)
        start = period_start(user.salary_day, now().date())
        accounts = list(await session.scalars(
            select(Account).where(Account.user_id == user_id, Account.is_active.is_(True)).order_by(Account.id)))
        rate = await session.get(ExchangeRate, (user_id, "USD", "UZS"))
    totals = await period_totals(user_id, start)
    return Report(start=start, totals=totals, accounts=accounts, usd_rate=rate.rate if rate else None)


async def build_period_report(user_id: int, offset: int = 0, today: Optional[date] = None) -> PeriodReport:
    """Report for the financial period `offset` periods back (0 = current; positive is clamped to 0)."""
    offset = min(offset, 0)
    today = today or now().date()
    async with session_factory() as session:
        user = await session.get(User, user_id)
        salary_day = user.salary_day
        budgets = list(await session.scalars(select(Budget).where(Budget.user_id == user_id).order_by(Budget.id)))
    start, end = period_bounds(salary_day, today, offset)
    cmp_start, cmp_end = comparison_window(start, end, today)
    usd_rate = await get_usd_rate(user_id)

    totals = await period_totals(user_id, start, end)
    prev_totals = await period_totals(user_id, cmp_start, cmp_end)
    by_category = await expense_by_category(user_id, start, end)
    prev_by_category = await expense_by_category(user_id, cmp_start, cmp_end)

    currencies = []
    for currency in CURRENCIES:
        income, expense = totals.get(("income", currency), 0), totals.get(("expense", currency), 0)
        prev_expense = prev_totals.get(("expense", currency), 0)
        if not (income or expense):
            continue
        rows = [CategoryRow(name, amount, share_percent(amount, expense), prev_by_category.get((currency, name), 0))
                for (cur, name), amount in by_category.items() if cur == currency]
        rows.sort(key=lambda row: (-row.amount, row.name))
        currencies.append(CurrencySummary(currency, income, expense, prev_expense, rows))

    combined = None
    if usd_rate and len(currencies) > 1:
        def uzs_total(source, kind):
            return sum(convert(source.get((kind, c), 0), c, "UZS", usd_rate) for c in CURRENCIES)

        combined = Combined(income=uzs_total(totals, "income"), expense=uzs_total(totals, "expense"),
                            prev_expense=uzs_total(prev_totals, "expense"), rate=usd_rate)

    usages = []
    for budget in budgets:
        per_currency = {cur: amount for (cur, name), amount in by_category.items() if name == budget.category}
        usages.append(BudgetUsage(budget.category, budget.currency, budget.amount_minor,
                                  spent_in_currency(per_currency, budget.currency, usd_rate)))

    return PeriodReport(
        offset=offset, start=start, end=end, compare_start=cmp_start, compare_end=cmp_end,
        is_current=offset == 0, has_earlier=await _has_earlier(user_id, start), currencies=currencies,
        combined=combined, usd_rate=usd_rate, budgets=usages, today=today)
