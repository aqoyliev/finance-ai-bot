"""Recording, editing and deleting operations (expenses, incomes, transfers).

record_operation / record_transfer are the single entry points that write operations, so
later input channels (AI parsing of receipts, voice, SMS) can call them after the user confirms.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from sqlalchemy import and_, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .accounts import is_over_limit, load_account
from .base import session_factory
from .common import OPERATION_KINDS, CurrencyMismatch, InvalidValue, OperationNotFound, SameAccount, now
from .models import Account, Transaction


@dataclass
class Leg:
    """One part of an operation: how much was paid from / received to one account."""
    account_id: int
    amount_minor: int


@dataclass
class SavedOperation:
    group_id: str
    transactions: List[Transaction]
    accounts: List[Account] = field(default_factory=list)  # touched accounts, after the change

    @property
    def over_limit(self) -> List[Account]:
        """Credit accounts whose debt is now above the limit."""
        return [a for a in self.accounts if is_over_limit(a)]


@dataclass
class OperationView:
    tx: Transaction  # for a transfer: the outgoing leg
    account: Account
    counterpart: Optional[Transaction] = None  # for a transfer: the incoming leg
    counterpart_account: Optional[Account] = None

    @property
    def is_transfer(self) -> bool:
        return self.tx.kind == "transfer"


def effect(tx: Transaction) -> int:
    """Signed change of the account balance caused by a row."""
    return tx.amount_minor if tx.direction == "in" else -tx.amount_minor


def _check_amount(amount_minor: int) -> None:
    if not isinstance(amount_minor, int) or amount_minor <= 0:
        raise InvalidValue()


def _remember(touched: Dict[int, Account], account: Account) -> None:
    touched[account.id] = account


# ---- Create ----

async def record_operation(
    user_id: int, kind: str, currency: str, legs: Sequence[Leg],
    category: Optional[str] = None, subcategory: Optional[str] = None, note: Optional[str] = None,
    occurred_at: Optional[datetime] = None, group_id: Optional[str] = None, source: str = "manual",
) -> SavedOperation:
    """Record an expense or income paid from one or more accounts and update balances atomically.

    Pass an existing group_id to add another part to an already saved split purchase.
    """
    if kind not in OPERATION_KINDS or not legs:
        raise InvalidValue()
    group_id = group_id or str(uuid.uuid4())
    occurred_at = occurred_at or now()
    direction = "in" if kind == "income" else "out"
    touched: Dict[int, Account] = {}
    rows = []

    async with session_factory() as session, session.begin():
        for leg in legs:
            _check_amount(leg.amount_minor)
            account = await load_account(session, user_id, leg.account_id)
            if account.currency != currency:
                raise CurrencyMismatch(account.currency)
            tx = Transaction(
                user_id=user_id, group_id=group_id, account_id=account.id, kind=kind, direction=direction,
                amount_minor=leg.amount_minor, currency=currency, category=category,
                subcategory=subcategory, note=note, source=source, occurred_at=occurred_at,
            )
            # Credit accounts store debt as a negative balance, so an expense lowers it as well
            account.balance_minor += effect(tx)
            session.add(tx)
            rows.append(tx)
            _remember(touched, account)
    return SavedOperation(group_id, rows, list(touched.values()))


async def record_transfer(
    user_id: int, from_account_id: int, to_account_id: int, amount_minor: int,
    note: Optional[str] = None, occurred_at: Optional[datetime] = None, source: str = "manual",
) -> SavedOperation:
    """Move money between two own accounts of the same currency (e.g. repay a credit card).

    Stored as two rows (out + in) with kind="transfer" and a shared group_id; not income or expense.
    """
    _check_amount(amount_minor)
    if from_account_id == to_account_id:
        raise SameAccount()
    group_id = str(uuid.uuid4())
    occurred_at = occurred_at or now()

    async with session_factory() as session, session.begin():
        source_account = await load_account(session, user_id, from_account_id)
        target_account = await load_account(session, user_id, to_account_id)
        if source_account.currency != target_account.currency:
            raise CurrencyMismatch(source_account.currency)
        rows = []
        for account, direction in ((source_account, "out"), (target_account, "in")):
            tx = Transaction(
                user_id=user_id, group_id=group_id, account_id=account.id, kind="transfer",
                direction=direction, amount_minor=amount_minor, currency=account.currency,
                note=note, source=source, occurred_at=occurred_at,
            )
            account.balance_minor += effect(tx)
            session.add(tx)
            rows.append(tx)
    return SavedOperation(group_id, rows, [source_account, target_account])


# ---- Read ----

async def _load_tx(session: AsyncSession, user_id: int, tx_id: int) -> Transaction:
    tx = await session.scalar(select(Transaction).where(Transaction.id == tx_id, Transaction.user_id == user_id))
    if tx is None:
        raise OperationNotFound()
    return tx


async def _rows_to_change(session: AsyncSession, user_id: int, tx_id: int) -> List[Transaction]:
    """The opened row, or both legs if it belongs to a transfer (out leg first)."""
    tx = await _load_tx(session, user_id, tx_id)
    if tx.kind != "transfer":
        return [tx]
    legs = await session.scalars(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.group_id == tx.group_id,
                                  Transaction.kind == "transfer"))
    return sorted(legs, key=lambda row: row.direction != "out")


async def _view(session: AsyncSession, user_id: int, rows: List[Transaction]) -> OperationView:
    main = rows[0]
    view = OperationView(main, await load_account(session, user_id, main.account_id, active_only=False))
    if len(rows) > 1:
        view.counterpart = rows[1]
        view.counterpart_account = await load_account(session, user_id, rows[1].account_id, active_only=False)
    return view


async def get_operation(user_id: int, tx_id: int) -> OperationView:
    async with session_factory() as session:
        return await _view(session, user_id, await _rows_to_change(session, user_id, tx_id))


async def recent_operations(user_id: int, limit: int = 10) -> List[OperationView]:
    """Latest operations, newest first; a transfer is shown once (by its outgoing leg)."""
    incoming_transfer = and_(Transaction.kind == "transfer", Transaction.direction == "in")
    async with session_factory() as session:
        rows = await session.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id, not_(incoming_transfer))
            .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
            .limit(limit))
        return [await _view(session, user_id, await _rows_to_change(session, user_id, tx.id)) for tx in rows]


# ---- Edit / delete ----

async def _account_for(session: AsyncSession, user_id: int, tx: Transaction) -> Account:
    # The account may be deactivated already; its balance is still corrected
    return await load_account(session, user_id, tx.account_id, active_only=False)


async def update_amount(user_id: int, tx_id: int, amount_minor: int) -> SavedOperation:
    """Change the amount (both legs for a transfer): reverse the old effect, apply the new one."""
    _check_amount(amount_minor)
    touched: Dict[int, Account] = {}
    async with session_factory() as session, session.begin():
        rows = await _rows_to_change(session, user_id, tx_id)
        for tx in rows:
            account = await _account_for(session, user_id, tx)
            account.balance_minor -= effect(tx)
            tx.amount_minor = amount_minor
            account.balance_minor += effect(tx)
            _remember(touched, account)
    return SavedOperation(rows[0].group_id, rows, list(touched.values()))


async def update_account(user_id: int, tx_id: int, account_id: int) -> SavedOperation:
    """Move an expense/income row to another active account of the same currency."""
    async with session_factory() as session, session.begin():
        tx = await _load_tx(session, user_id, tx_id)
        if tx.kind == "transfer":
            raise InvalidValue()
        new_account = await load_account(session, user_id, account_id)
        if new_account.currency != tx.currency:
            raise CurrencyMismatch(new_account.currency)
        old_account = await _account_for(session, user_id, tx)
        old_account.balance_minor -= effect(tx)
        tx.account_id = new_account.id
        new_account.balance_minor += effect(tx)
    return SavedOperation(tx.group_id, [tx], [old_account, new_account])


async def update_category(user_id: int, tx_id: int, category: str, subcategory: Optional[str]) -> Transaction:
    async with session_factory() as session, session.begin():
        tx = await _load_tx(session, user_id, tx_id)
        if tx.kind == "transfer":
            raise InvalidValue()
        tx.category = category
        tx.subcategory = subcategory
        return tx


async def delete_operation(user_id: int, tx_id: int) -> List[Account]:
    """Delete a row (both legs for a transfer) and reverse its effect. Returns touched accounts."""
    touched: Dict[int, Account] = {}
    async with session_factory() as session, session.begin():
        for tx in await _rows_to_change(session, user_id, tx_id):
            account = await _account_for(session, user_id, tx)
            account.balance_minor -= effect(tx)
            _remember(touched, account)
            await session.delete(tx)
    return list(touched.values())
