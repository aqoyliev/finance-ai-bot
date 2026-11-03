from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import session_factory
from .common import ACCOUNT_KINDS, CURRENCIES, AccountNotFound, InvalidValue, now
from .models import Account

MAX_NAME_LENGTH = 40


# ---- Credit helpers (pure) ----

def debt(account: Account) -> int:
    """Current debt of a credit account in minor units (0 if it has a positive balance)."""
    return max(-account.balance_minor, 0)


def available_credit(account: Account) -> int:
    return account.credit_limit_minor - debt(account)


def is_over_limit(account: Account) -> bool:
    return account.kind == "credit" and account.credit_limit_minor > 0 and debt(account) > account.credit_limit_minor


# ---- Queries ----

async def list_accounts(user_id: int, currency: Optional[str] = None) -> List[Account]:
    """Active accounts of the user, optionally of one currency."""
    query = select(Account).where(Account.user_id == user_id, Account.is_active.is_(True))
    if currency:
        query = query.where(Account.currency == currency)
    async with session_factory() as session:
        return list(await session.scalars(query.order_by(Account.id)))


async def load_account(session: AsyncSession, user_id: int, account_id: int, active_only: bool = True) -> Account:
    query = select(Account).where(Account.id == account_id, Account.user_id == user_id)
    if active_only:
        query = query.where(Account.is_active.is_(True))
    account = await session.scalar(query)
    if account is None:
        raise AccountNotFound()
    return account


async def get_account(user_id: int, account_id: int) -> Optional[Account]:
    async with session_factory() as session:
        try:
            return await load_account(session, user_id, account_id)
        except AccountNotFound:
            return None


# ---- Changes ----

def clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not name or len(name) > MAX_NAME_LENGTH:
        raise InvalidValue()
    return name


async def create_account(user_id: int, name: str, kind: str, currency: str,
                         opening_minor: int = 0, credit_limit_minor: int = 0) -> Account:
    """Create an account. opening_minor is signed: pass -debt for a credit account."""
    if kind not in ACCOUNT_KINDS or currency not in CURRENCIES or credit_limit_minor < 0:
        raise InvalidValue()
    account = Account(
        user_id=user_id, name=clean_name(name), kind=kind, currency=currency,
        balance_minor=opening_minor, opening_balance_minor=opening_minor,
        credit_limit_minor=credit_limit_minor if kind == "credit" else 0, created_at=now(),
    )
    async with session_factory() as session, session.begin():
        session.add(account)
    return account


async def rename_account(user_id: int, account_id: int, name: str) -> Account:
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        account.name = clean_name(name)
        return account


async def set_opening_balance(user_id: int, account_id: int, opening_minor: int) -> Account:
    """Change the opening balance; the current balance moves by the same difference."""
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        account.balance_minor += opening_minor - account.opening_balance_minor
        account.opening_balance_minor = opening_minor
        return account


async def set_credit_limit(user_id: int, account_id: int, limit_minor: int) -> Account:
    if limit_minor < 0:
        raise InvalidValue()
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        if account.kind != "credit":
            raise InvalidValue()
        account.credit_limit_minor = limit_minor
        return account


async def deactivate_account(user_id: int, account_id: int) -> Account:
    """Soft-delete: hide the account from menus but keep its history."""
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        account.is_active = False
        return account
