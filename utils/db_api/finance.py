from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select

from .base import session_factory
from .models import Account, Category, ExchangeRate, Subcategory, Transaction, User

# Uzbekistan time (UTC+5, no DST). Datetimes are stored naive in this zone.
TZ = timezone(timedelta(hours=5))

CURRENCIES = ("UZS", "USD")

DEFAULT_ACCOUNTS = [
    ("Cash", "cash", "UZS"),
    ("Cash (USD)", "cash", "USD"),
    ("UOB", "debit", "UZS"),
    ("Infinbank", "debit", "UZS"),
    ("Hamkorbank", "debit", "UZS"),
    ("Credit card", "credit", "UZS"),
]

DEFAULT_CATEGORIES = {
    "Small expenses": ["Coffee", "Soda and water", "Sweets", "Snacks", "Light meals", "Other"],
    "Home and household": ["Meat", "Groceries for home", "Household chemicals", "Household purchases"],
    "Family": ["Family needs", "Clothing", "Personal expenses"],
    "Children": ["Food", "Clothing", "Toys", "School and clubs", "Medicine"],
    "Utilities": ["Rent", "Electricity", "Gas", "Water", "Wi-Fi", "Phone"],
    "Transport": ["Fuel", "Taxi", "Car maintenance", "Parking"],
    "Health": ["Pharmacy", "Doctor", "Checkups"],
    "Other": ["Gifts", "Entertainment", "Miscellaneous"],
}

INCOME_CATEGORIES = [
    "Salary", "Extra income", "Transfer from another person", "Debt repayment", "Other income",
]


class AccountNotFound(Exception):
    pass


class CurrencyMismatch(Exception):
    def __init__(self, account_currency: str):
        self.account_currency = account_currency


@dataclass
class Report:
    start: date
    totals: Dict[Tuple[str, str], int]  # (kind, currency) -> minor units
    accounts: List[Account]
    usd_rate: Optional[str]


def now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


async def ensure_user(user_id: int, username: Optional[str]) -> User:
    """Return the user, creating it (with starter accounts and categories) on first contact."""
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        if user is not None:
            return user

        user = User(id=user_id, username=username or "", created_at=now())
        session.add(user)
        for name, kind, currency in DEFAULT_ACCOUNTS:
            session.add(Account(user_id=user_id, name=name, kind=kind, currency=currency))

        for name, subs in DEFAULT_CATEGORIES.items():
            category = Category(user_id=user_id, name=name, kind="expense")
            session.add(category)
            await session.flush()
            session.add_all(Subcategory(category_id=category.id, name=sub) for sub in subs)
        session.add_all(Category(user_id=user_id, name=name, kind="income") for name in INCOME_CATEGORIES)
        return user


async def list_categories(user_id: int, kind: str) -> List[Category]:
    async with session_factory() as session:
        result = await session.scalars(
            select(Category).where(Category.user_id == user_id, Category.kind == kind).order_by(Category.id))
        return list(result)


async def get_category(user_id: int, category_id: int) -> Optional[Category]:
    async with session_factory() as session:
        return await session.scalar(
            select(Category).where(Category.id == category_id, Category.user_id == user_id))


async def list_subcategories(category_id: int) -> List[Subcategory]:
    async with session_factory() as session:
        result = await session.scalars(
            select(Subcategory).where(Subcategory.category_id == category_id).order_by(Subcategory.id))
        return list(result)


async def get_subcategory(subcategory_id: int) -> Optional[Subcategory]:
    async with session_factory() as session:
        return await session.get(Subcategory, subcategory_id)


async def list_accounts(user_id: int, currency: Optional[str] = None) -> List[Account]:
    query = select(Account).where(Account.user_id == user_id, Account.is_active.is_(True))
    if currency:
        query = query.where(Account.currency == currency)
    async with session_factory() as session:
        return list(await session.scalars(query.order_by(Account.id)))


async def add_transaction(
    user_id: int, account_id: int, kind: str, amount_minor: int, currency: str,
    category: Optional[str], subcategory: Optional[str], group_id: str,
) -> None:
    """Record an operation and update the account balance atomically."""
    async with session_factory() as session, session.begin():
        account = await session.scalar(
            select(Account).where(Account.id == account_id, Account.user_id == user_id))
        if account is None:
            raise AccountNotFound()
        if account.currency != currency:
            raise CurrencyMismatch(account.currency)

        # Credit accounts store debt as a negative balance, so an expense lowers it as well
        account.balance_minor += amount_minor if kind == "income" else -amount_minor
        session.add(Transaction(
            user_id=user_id, group_id=group_id, account_id=account_id, kind=kind,
            amount_minor=amount_minor, currency=currency, category=category,
            subcategory=subcategory, occurred_at=now(),
        ))


async def recent_transactions(user_id: int, limit: int = 10) -> List[Tuple[Transaction, str]]:
    async with session_factory() as session:
        result = await session.execute(
            select(Transaction, Account.name)
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.id.desc())
            .limit(limit))
        return [(tx, account_name) for tx, account_name in result.all()]


async def set_salary_day(user_id: int, day: int) -> None:
    async with session_factory() as session, session.begin():
        user = await session.get(User, user_id)
        user.salary_day = day


async def set_usd_rate(user_id: int, rate: Decimal) -> None:
    """Store USD->UZS and the inverse UZS->USD rate."""
    updated_at = now()
    async with session_factory() as session, session.begin():
        for from_cur, to_cur, value in (("USD", "UZS", rate), ("UZS", "USD", Decimal(1) / rate)):
            row = await session.get(ExchangeRate, (user_id, from_cur, to_cur))
            if row is None:
                session.add(ExchangeRate(user_id=user_id, from_currency=from_cur, to_currency=to_cur,
                                         rate=str(value), updated_at=updated_at))
            else:
                row.rate = str(value)
                row.updated_at = updated_at


def period_start(salary_day: int, today: date) -> date:
    """First day of the current financial month (it begins on the salary day)."""
    day = min(salary_day, 28)
    if today.day >= day:
        return date(today.year, today.month, day)
    if today.month == 1:
        return date(today.year - 1, 12, day)
    return date(today.year, today.month - 1, day)


async def build_report(user_id: int) -> Report:
    async with session_factory() as session:
        user = await session.get(User, user_id)
        start = period_start(user.salary_day, now().date())

        rows = await session.execute(
            select(Transaction.kind, Transaction.currency, func.sum(Transaction.amount_minor))
            .where(Transaction.user_id == user_id, Transaction.occurred_at >= datetime.combine(start, datetime.min.time()))
            .group_by(Transaction.kind, Transaction.currency))
        totals = {(kind, currency): total or 0 for kind, currency, total in rows.all()}

        accounts = list(await session.scalars(
            select(Account).where(Account.user_id == user_id, Account.is_active.is_(True)).order_by(Account.id)))
        rate = await session.get(ExchangeRate, (user_id, "USD", "UZS"))
        return Report(start=start, totals=totals, accounts=accounts, usd_rate=rate.rate if rate else None)
