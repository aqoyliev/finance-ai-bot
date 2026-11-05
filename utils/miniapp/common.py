"""Helpers shared by the Mini App API modules: errors, input checks and JSON shapes.

Amounts are integers in minor units (amount * 100), like in the database.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from aiohttp import web

from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.db_api.accounts import MAX_BALANCE_MINOR
from utils.db_api.models import Account, User

MAX_NOTE_LENGTH = 200
MAX_QUERY_LENGTH = 100
EARLIEST_DATE = datetime(2000, 1, 1)
FUTURE_TOLERANCE = timedelta(minutes=5)  # a phone clock slightly ahead of the server is fine


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


# ---- Input ----

async def read_json(request: web.Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        raise ApiError(400, "invalid") from None
    if not isinstance(data, dict):
        raise ApiError(400, "invalid")
    return data


def minor(value, code: str = "amount", minimum: int = 0) -> int:
    """An integer amount in minor units within [minimum, MAX_BALANCE_MINOR] (booleans are refused)."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_BALANCE_MINOR:
        raise ApiError(400, code)
    return value


def int_id(value, code: str = "invalid") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2 ** 63:
        raise ApiError(400, code)
    return value


def query_int(request: web.Request, name: str, default: Optional[int], low: int, high: int) -> Optional[int]:
    raw = request.query.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, "invalid") from None
    if not low <= value <= high:
        raise ApiError(400, "invalid")
    return value


def path_id(request: web.Request, name: str) -> int:
    try:
        value = int(request.match_info[name])
    except ValueError:
        raise ApiError(404, "not_found") from None
    if not 0 < value < 2 ** 63:
        raise ApiError(404, "not_found")
    return value


def clean_text(value, limit: int, code: str = "invalid") -> Optional[str]:
    """A single-line string (whitespace collapsed) of at most `limit` characters; None when empty."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, code)
    text = " ".join(value.split())
    if len(text) > limit:
        raise ApiError(400, code)
    return text or None


def parse_moment(value) -> datetime:
    """'YYYY-MM-DDTHH:MM[:SS]' in Tashkent time, not in the future, not before 2000."""
    if not isinstance(value, str) or len(value) > 25:
        raise ApiError(400, "date")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise ApiError(400, "date") from None
    if moment.tzinfo is not None:  # an offset is converted to the bot's local time
        moment = moment.astimezone(db.TZ).replace(tzinfo=None)
    moment = moment.replace(microsecond=0)
    if moment < EARLIEST_DATE or moment > db.now() + FUTURE_TOLERANCE:
        raise ApiError(400, "date")
    return moment


# ---- Users ----

async def current_user(request: web.Request) -> User:
    """The caller's user row; an admin who never chose a language in the bot gets 409 'start'."""
    user = await db.get_user(request["user_id"])
    if user is None or not user.language:
        raise ApiError(409, "start")
    return user


# ---- Serialization ----

def card_type_of(account: Account) -> Optional[str]:
    """The saved card type; accounts added in the chat have none (cash ones count as "cash")."""
    return account.card_type or ("cash" if account.kind == "cash" else None)


def account_json(account: Account) -> dict:
    credit = account.kind == "credit"
    return {
        "id": account.id,
        "name": account.name,
        "kind": account.kind,
        "card_type": card_type_of(account),
        "last4": account.last4,
        "currency": account.currency,
        "is_credit": credit,
        "is_active": bool(account.is_active),
        "balance_minor": account.balance_minor,
        "debt_minor": db.debt(account) if credit else 0,
        "credit_limit_minor": account.credit_limit_minor if credit else 0,
        "available_minor": db.available_credit(account) if credit else None,
    }


def totals_json(accounts: Iterable[Account]) -> dict:
    totals = {currency: 0 for currency in db.CURRENCIES}
    for account in accounts:
        totals[account.currency] += account.balance_minor
    return totals


def moment_text(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M")


def tx_row_json(row: db.TxRow) -> dict:
    """One history line (a transfer once, with both account names)."""
    return {
        "id": row.id,
        "occurred_at": moment_text(row.occurred_at),
        "date": row.occurred_at.date().isoformat(),
        "kind": row.kind,
        "amount_minor": row.amount_minor,
        "currency": row.currency,
        "category": row.category,
        "subcategory": row.subcategory,
        "account": row.account,
        "to_account": row.to_account,
        "note": row.note,
    }


def rate_json(info: Optional[db.UsdRate]) -> Optional[dict]:
    if info is None:
        return None
    return {"rate": format(info.rate.normalize(), "f"), "source": info.source,
            "date": info.day.isoformat() if info.day else None}


def to_uzs(minor_amount: int, currency: str, rate: Optional[Decimal]) -> int:
    return rep.convert(minor_amount, currency, "UZS", rate)


def day_after(day: date) -> date:
    return day + timedelta(days=1)
