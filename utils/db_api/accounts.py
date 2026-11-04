import re
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import session_factory
from .common import ACCOUNT_KINDS, CURRENCIES, AccountNotFound, FinanceError, InvalidValue, now
from .models import Account, Transaction

MAX_NAME_LENGTH = 40
MAX_BALANCE_MINOR = 10 ** 14  # 1 000 000 000 000.00, the same cap as a single amount
# Card types of the Mini App; "cash" is the only one without card digits
CARD_TYPES = ("cash", "uzcard", "humo", "visa", "mastercard")


class Last4Taken(FinanceError):
    """Another active account already has these last 4 digits (SMS matching needs them unique)."""


class CurrencyLocked(FinanceError):
    """The currency of an account with operations cannot change (the operations keep theirs)."""


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


def clean_last4(value: Optional[str]) -> Optional[str]:
    """Exactly 4 digits, or None for an empty value."""
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"\d{4}", value):
        raise InvalidValue()
    return value


async def _check_last4_free(session: AsyncSession, user_id: int, last4: Optional[str],
                            except_id: Optional[int] = None) -> None:
    if not last4:
        return
    query = select(Account.id).where(Account.user_id == user_id, Account.is_active.is_(True),
                                     Account.last4 == last4)
    if except_id is not None:
        query = query.where(Account.id != except_id)
    if await session.scalar(query.limit(1)) is not None:
        raise Last4Taken()


async def create_account(user_id: int, name: str, kind: str, currency: str,
                         opening_minor: int = 0, credit_limit_minor: int = 0,
                         card_type: Optional[str] = None, last4: Optional[str] = None) -> Account:
    """Create an account. opening_minor is signed: pass -debt for a credit account."""
    if kind not in ACCOUNT_KINDS or currency not in CURRENCIES or credit_limit_minor < 0:
        raise InvalidValue()
    if card_type is not None and card_type not in CARD_TYPES:
        raise InvalidValue()
    last4 = clean_last4(last4)
    account = Account(
        user_id=user_id, name=clean_name(name), kind=kind, currency=currency,
        balance_minor=opening_minor, opening_balance_minor=opening_minor,
        credit_limit_minor=credit_limit_minor if kind == "credit" else 0, created_at=now(),
        card_type=card_type, last4=last4,
    )
    async with session_factory() as session, session.begin():
        await _check_last4_free(session, user_id, last4)
        session.add(account)
    return account


async def account_has_operations(session: AsyncSession, account_id: int) -> bool:
    found = await session.scalar(select(Transaction.id).where(Transaction.account_id == account_id).limit(1))
    return found is not None


async def update_account_details(user_id: int, account_id: int, *, name: str, kind: str, currency: str,
                                 card_type: Optional[str], last4: Optional[str], balance_minor: int,
                                 credit_limit_minor: int = 0) -> Account:
    """Mini App edit: every field at once. balance_minor is the wanted current balance (signed: -debt
    for a credit account); the opening balance moves by the difference, so history stays consistent."""
    if (kind not in ACCOUNT_KINDS or currency not in CURRENCIES or credit_limit_minor < 0
            or (card_type is not None and card_type not in CARD_TYPES)
            or abs(balance_minor) > MAX_BALANCE_MINOR or credit_limit_minor > MAX_BALANCE_MINOR):
        raise InvalidValue()
    name, last4 = clean_name(name), clean_last4(last4)
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        if currency != account.currency and await account_has_operations(session, account.id):
            raise CurrencyLocked()
        await _check_last4_free(session, user_id, last4, except_id=account.id)
        account.name, account.kind, account.currency = name, kind, currency
        account.card_type, account.last4 = card_type, last4
        account.credit_limit_minor = credit_limit_minor if kind == "credit" else 0
        account.opening_balance_minor += balance_minor - account.balance_minor
        account.balance_minor = balance_minor
        return account


async def remove_account(user_id: int, account_id: int) -> str:
    """Delete an account without operations; archive (deactivate) one with history.
    Returns "deleted" or "archived"."""
    async with session_factory() as session, session.begin():
        account = await load_account(session, user_id, account_id)
        if await account_has_operations(session, account.id):
            account.is_active = False
            return "archived"
        await session.execute(delete(Account).where(Account.id == account.id))
        return "deleted"


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
