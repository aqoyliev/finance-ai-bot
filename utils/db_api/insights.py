"""Read-only queries behind the AI assistant (Q&A tools and automatic advice).

Nothing here writes. Amounts stay in minor units; utils/ai/tools.py turns them into human amounts.
Transfers between own accounts are never income or expense: summaries ignore them, and the transaction
search lists a transfer once (by its outgoing leg) with both account names.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import and_, func, not_, select
from sqlalchemy.orm import aliased

from .base import session_factory
from .common import CURRENCIES, OPERATION_KINDS
from .models import Account, Transaction
from .reports import NO_CATEGORY, day_start

SEARCH_SCAN_LIMIT = 5000  # rows read before the in-Python text filter; plenty for one person's history


@dataclass
class TxRow:
    id: int
    occurred_at: datetime
    kind: str  # expense | income | transfer
    amount_minor: int
    currency: str
    category: Optional[str]
    subcategory: Optional[str]
    account: str
    to_account: Optional[str]  # transfers: the receiving account
    note: Optional[str]


@dataclass
class SearchResult:
    rows: List[TxRow]  # newest first, at most `limit`
    count: int  # all matches
    totals: Dict[Tuple[str, str], int]  # (kind, currency) -> minor units of all matches


@dataclass
class RangeSummary:
    """Income / expense of [start, end) without transfers."""
    start: date
    end: date  # exclusive
    totals: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (kind, currency) -> minor
    expense_by_category: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (currency, category) -> minor
    income_by_category: Dict[Tuple[str, str], int] = field(default_factory=dict)
    operations: int = 0  # number of income / expense rows

    def total(self, kind: str, currency: str) -> int:
        return self.totals.get((kind, currency), 0)

    @property
    def currencies(self) -> List[str]:
        return [c for c in CURRENCIES if self.total("income", c) or self.total("expense", c)]


def _fold(text: Optional[str]) -> str:
    return " ".join((text or "").casefold().split())


async def search_transactions(user_id: int, date_from: Optional[date] = None, date_to: Optional[date] = None,
                              kind: Optional[str] = None, category: Optional[str] = None,
                              account_ids: Optional[Sequence[int]] = None, text: Optional[str] = None,
                              min_minor: Optional[int] = None, max_minor: Optional[int] = None,
                              limit: int = 20) -> SearchResult:
    """Operations matching all given filters. date_to is inclusive; `category` matches the category or the
    subcategory name, `text` the note, category or subcategory (both case-insensitive)."""
    counterpart = aliased(Transaction)
    target = aliased(Account)
    incoming_transfer = and_(Transaction.kind == "transfer", Transaction.direction == "in")
    query = (
        select(Transaction, Account.name, target.name)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(counterpart, and_(Transaction.kind == "transfer", counterpart.group_id == Transaction.group_id,
                                     counterpart.direction == "in", counterpart.user_id == user_id))
        .outerjoin(target, target.id == counterpart.account_id)
        .where(Transaction.user_id == user_id, not_(incoming_transfer))
    )
    if date_from:
        query = query.where(Transaction.occurred_at >= day_start(date_from))
    if date_to:
        query = query.where(Transaction.occurred_at < day_start(date_to + timedelta(days=1)))
    if kind:
        query = query.where(Transaction.kind == kind)
    if account_ids is not None:
        # A transfer matches by either of its accounts
        query = query.where(Transaction.account_id.in_(account_ids) | counterpart.account_id.in_(account_ids))
    if min_minor is not None:
        query = query.where(Transaction.amount_minor >= min_minor)
    if max_minor is not None:
        query = query.where(Transaction.amount_minor <= max_minor)
    query = query.order_by(Transaction.occurred_at.desc(), Transaction.id.desc()).limit(SEARCH_SCAN_LIMIT)

    async with session_factory() as session:
        result = (await session.execute(query)).all()

    wanted_category, wanted_text = _fold(category), _fold(text)
    rows: List[TxRow] = []
    for tx, account_name, target_name in result:
        if wanted_category and wanted_category not in (_fold(tx.category), _fold(tx.subcategory)):
            continue
        if wanted_text and not any(wanted_text in _fold(value) for value in (tx.note, tx.category, tx.subcategory)):
            continue
        rows.append(TxRow(tx.id, tx.occurred_at, tx.kind, tx.amount_minor, tx.currency, tx.category,
                          tx.subcategory, account_name, target_name, tx.note))
    totals: Dict[Tuple[str, str], int] = {}
    for row in rows:
        totals[(row.kind, row.currency)] = totals.get((row.kind, row.currency), 0) + row.amount_minor
    return SearchResult(rows[:max(limit, 0)], len(rows), totals)


async def range_summary(user_id: int, start: date, end: date) -> RangeSummary:
    """Totals and per-category sums of incomes and expenses in [start, end)."""
    label = func.coalesce(Transaction.category, NO_CATEGORY)
    query = (select(Transaction.kind, Transaction.currency, label, func.sum(Transaction.amount_minor),
                    func.count(Transaction.id))
             .where(Transaction.user_id == user_id, Transaction.kind.in_(OPERATION_KINDS),
                    Transaction.occurred_at >= day_start(start), Transaction.occurred_at < day_start(end))
             .group_by(Transaction.kind, Transaction.currency, label))
    summary = RangeSummary(start, end)
    async with session_factory() as session:
        for kind, currency, name, total, count in (await session.execute(query)).all():
            total = total or 0
            summary.totals[(kind, currency)] = summary.totals.get((kind, currency), 0) + total
            target = summary.expense_by_category if kind == "expense" else summary.income_by_category
            target[(currency, name)] = total
            summary.operations += count
    return summary


async def largest_expenses(user_id: int, start: date, end: date, limit: int = 5) -> List[TxRow]:
    """Biggest single expense rows in [start, end)."""
    query = (select(Transaction, Account.name).join(Account, Account.id == Transaction.account_id)
             .where(Transaction.user_id == user_id, Transaction.kind == "expense",
                    Transaction.occurred_at >= day_start(start), Transaction.occurred_at < day_start(end))
             .order_by(Transaction.amount_minor.desc(), Transaction.id).limit(limit))
    async with session_factory() as session:
        result = (await session.execute(query)).all()
    return [TxRow(tx.id, tx.occurred_at, tx.kind, tx.amount_minor, tx.currency, tx.category, tx.subcategory,
                  name, None, tx.note) for tx, name in result]


async def has_operations(user_id: int, start: date, end: date) -> bool:
    """Any income or expense in [start, end) (transfers alone do not count)."""
    async with session_factory() as session:
        found = await session.scalar(
            select(Transaction.id).where(Transaction.user_id == user_id, Transaction.kind.in_(OPERATION_KINDS),
                                         Transaction.occurred_at >= day_start(start),
                                         Transaction.occurred_at < day_start(end)).limit(1))
    return found is not None


@dataclass
class ExpenseRow:
    """One expense row with the kind of account it was paid from (a split purchase has several rows)."""
    occurred_at: datetime
    amount_minor: int
    currency: str
    category: Optional[str]
    note: Optional[str]
    group_id: str
    account_kind: str  # cash | debit | credit


async def expense_rows(user_id: int, start: date, end: date) -> List[ExpenseRow]:
    """Every expense row in [start, end), oldest first (transfers are never expenses)."""
    query = (select(Transaction.occurred_at, Transaction.amount_minor, Transaction.currency, Transaction.category,
                    Transaction.note, Transaction.group_id, Account.kind)
             .join(Account, Account.id == Transaction.account_id)
             .where(Transaction.user_id == user_id, Transaction.kind == "expense",
                    Transaction.occurred_at >= day_start(start), Transaction.occurred_at < day_start(end))
             .order_by(Transaction.occurred_at, Transaction.id))
    async with session_factory() as session:
        result = (await session.execute(query)).all()
    return [ExpenseRow(*row) for row in result]
