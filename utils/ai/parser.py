"""Validation of Gemini output and mapping onto the user's own accounts and categories.

The model's answer is never trusted: amounts are re-parsed, currencies checked, accounts must belong to
the user (and match the currency), categories must exist. Anything doubtful is left empty (None) so the
user fills it in on the draft card. Drafts are plain dicts so they can live in FSM storage.
"""
import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence

from utils.db_api import finance as db
from utils.misc.money import MAX_AMOUNT

KINDS = ("expense", "income", "transfer")
MAX_DRAFTS = 10
MAX_NOTE_LENGTH = 200
LOW_CONFIDENCE = 0.6
MAX_PAST = timedelta(days=366)  # older dates from a receipt are treated as misread
MAX_FUTURE = timedelta(days=1)


@dataclass
class AccountRef:
    id: int
    name: str
    kind: str
    currency: str


@dataclass
class UserContext:
    accounts: List[AccountRef]
    # {"expense": {category: [subcategories]}, "income": {category: []}}
    categories: Dict[str, Dict[str, List[str]]]

    def account(self, account_id: Any) -> Optional[AccountRef]:
        return next((a for a in self.accounts if a.id == account_id), None)

    def as_prompt_data(self):
        return [asdict(a) for a in self.accounts], self.categories


@dataclass
class Draft:
    kind: str = "expense"
    amount_minor: Optional[int] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None  # transfers only
    note: Optional[str] = None
    occurred_at: Optional[str] = None  # ISO "YYYY-MM-DDTHH:MM:SS"; None = now at save time
    confidence: float = 0.0
    card_last4: Optional[str] = None
    source_ref: Optional[str] = None
    duplicate: bool = False
    notes: List[str] = field(default_factory=list)  # validation notices (i18n keys)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Draft":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


async def load_context(user_id: int) -> UserContext:
    accounts = [AccountRef(a.id, a.name, a.kind, a.currency) for a in await db.list_accounts(user_id)]
    categories: Dict[str, Dict[str, List[str]]] = {"expense": {}, "income": {}}
    for kind in categories:
        for category in await db.list_categories(user_id, kind):
            subs = [s.name for s in await db.list_subcategories(category.id)] if kind == "expense" else []
            categories[kind][category.name] = subs
    return UserContext(accounts, categories)


def fingerprint(text: str) -> str:
    """Stable hash of an input (e.g. a forwarded SMS), insensitive to spacing and case."""
    normalized = " ".join((text or "").split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---- Amounts ----

_SUFFIXES = {"k": 1_000, "к": 1_000, "ming": 1_000, "тыс": 1_000, "m": 1_000_000, "mln": 1_000_000,
             "млн": 1_000_000}


def normalize_amount(value: Any) -> Optional[int]:
    """Amount from the model (number or string like '125 000,00', '125.000', '1,250.50') -> minor units."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        text = repr(value) if isinstance(value, float) else str(value)
        multiplier = 1
    else:
        text = str(value).strip().lower().replace(" ", " ").replace("'", "").replace("`", "")
        text = re.sub(r"^[^\d\-]+", "", text)  # leading currency words / signs ("UZS 25000", "$20")
        multiplier = 1
        # Trailing words: currency ("so'm", "сум") or multipliers ("ming", "млн", "k")
        while (match := re.search(r"([a-zа-яё$]+)\.?\s*$", text)):
            multiplier *= _SUFFIXES.get(match.group(1), 1)
            text = text[:match.start()].rstrip()
        text = text.replace(" ", "")
        if not re.fullmatch(r"-?[\d.,]+", text):
            return None  # letters inside the number: do not guess
        text = _decimal_separator(text)
    try:
        amount = Decimal(text) * multiplier
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        return None
    minor = int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return minor or None


def _decimal_separator(text: str) -> str:
    """Resolve ',' / '.' into a plain decimal string."""
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        return text.replace(thousands, "").replace(decimal_sep, ".")
    for sep in (",", "."):
        if sep in text:
            head, _, tail = text.rpartition(sep)
            # Several separators, or exactly three digits after one, mean thousands ("125.000", "1,250,000")
            if text.count(sep) > 1 or len(tail) == 3:
                return text.replace(sep, "")
            return f"{head.replace(sep, '')}.{tail}"
    return text


# ---- Matching ----

def _fold(text: Any) -> str:
    return " ".join(str(text or "").casefold().replace("ʻ", "'").replace("’", "'").split())


def _match_name(value: Any, names: Sequence[str]) -> Optional[str]:
    """Exact (case-insensitive) match, else a unique containment match."""
    wanted = _fold(value)
    if not wanted:
        return None
    for name in names:
        if _fold(name) == wanted:
            return name
    partial = [name for name in names if wanted in _fold(name) or _fold(name) in wanted]
    return partial[0] if len(partial) == 1 else None


def _last4(value: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-4:] if len(digits) >= 4 else None


def match_account(ctx: UserContext, account_id: Any = None, card_last4: Any = None,
                  hint: Any = None) -> Optional[AccountRef]:
    """The user's account by id (validated), by card last 4 digits in its name, or by a name hint."""
    if isinstance(account_id, str) and account_id.strip().isdigit():
        account_id = int(account_id)
    if isinstance(account_id, (int, float)) and not isinstance(account_id, bool):
        account = ctx.account(int(account_id))
        if account:
            return account
    last4 = _last4(card_last4)
    if last4:
        by_card = [a for a in ctx.accounts if last4 in re.findall(r"\d{4}", a.name)]
        if len(by_card) == 1:
            return by_card[0]
    name = _match_name(hint, [a.name for a in ctx.accounts])
    return next((a for a in ctx.accounts if a.name == name), None) if name else None


def match_category(ctx: UserContext, kind: str, category: Any, subcategory: Any):
    """(category, subcategory) existing for the user, or Nones."""
    if kind not in ("expense", "income"):
        return None, None
    tree = ctx.categories.get(kind, {})
    name = _match_name(category, list(tree))
    sub = None
    if name:
        sub = _match_name(subcategory, tree[name]) if kind == "expense" else None
    elif kind == "expense" and subcategory:
        # Unknown category but a known subcategory: take its parent if it is unambiguous
        owners = [(cat, _match_name(subcategory, subs)) for cat, subs in tree.items()]
        owners = [(cat, s) for cat, s in owners if s]
        if len(owners) == 1:
            name, sub = owners[0]
    return name, sub


def parse_datetime(value: Any, now: datetime) -> Optional[datetime]:
    """'YYYY-MM-DD HH:MM[:SS]' / 'DD.MM.YYYY [HH:MM]' within a plausible range, else None."""
    text = " ".join(str(value or "").replace("T", " ").split())[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%H" not in fmt:
            # Date only: keep the current time of day so the ordering stays natural
            parsed = parsed.replace(hour=now.hour, minute=now.minute)
        return parsed if now - MAX_PAST <= parsed <= now + MAX_FUTURE else None
    return None


# ---- Validation ----

def validate_operation(item: Any, ctx: UserContext, now: datetime) -> Optional[Draft]:
    if not isinstance(item, dict):
        return None
    kind = item.get("kind") if item.get("kind") in KINDS else "expense"
    draft = Draft(kind=kind)
    draft.amount_minor = normalize_amount(item.get("amount"))
    if draft.amount_minor is None:
        draft.notes.append("ai_note_amount")

    currency = str(item.get("currency") or "").upper() or None
    if currency is not None and currency not in db.CURRENCIES:
        currency = None
        draft.notes.append("ai_note_currency")

    account = match_account(ctx, item.get("account_id"), item.get("card_last4"), item.get("account_hint"))
    if account and currency and account.currency != currency:
        account = None  # e.g. a USD amount on a UZS card: let the user choose
        draft.notes.append("ai_note_account_currency")
    draft.currency = currency or (account.currency if account else None)
    draft.account_id = account.id if account else None
    draft.card_last4 = _last4(item.get("card_last4"))

    if kind == "transfer":
        target = match_account(ctx, item.get("to_account_id"))
        if target and (target.id == draft.account_id or (draft.currency and target.currency != draft.currency)):
            target = None
        draft.to_account_id = target.id if target else None
    else:
        draft.category, draft.subcategory = match_category(ctx, kind, item.get("category"),
                                                           item.get("subcategory"))

    note = " ".join(str(item.get("note") or "").split())
    draft.note = note[:MAX_NOTE_LENGTH] or None
    occurred = parse_datetime(item.get("occurred_at"), now) if item.get("occurred_at") else None
    draft.occurred_at = occurred.isoformat() if occurred else None
    try:
        draft.confidence = min(max(float(item.get("confidence") or 0), 0.0), 1.0)
    except (TypeError, ValueError):
        draft.confidence = 0.0
    return draft


def parse_response(raw: Any, ctx: UserContext, now: datetime, source_ref: Optional[str] = None) -> List[Draft]:
    """Gemini JSON -> validated drafts (at most MAX_DRAFTS). Empty list = nothing recognized."""
    items = raw.get("operations") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    drafts = [d for d in (validate_operation(item, ctx, now) for item in items[:MAX_DRAFTS]) if d]
    # Drop entries with nothing useful at all (no amount and no account/category)
    drafts = [d for d in drafts if d.amount_minor or d.account_id or d.category]
    for draft in drafts:
        draft.source_ref = source_ref if len(drafts) == 1 else None
    return drafts


def missing_fields(draft: Draft) -> List[str]:
    """Required fields still empty; Save is possible only when this is empty."""
    missing = []
    if not draft.amount_minor:
        missing.append("amount")
    if not draft.currency:
        missing.append("currency")
    if not draft.account_id:
        missing.append("account")
    if draft.kind == "transfer":
        if not draft.to_account_id:
            missing.append("to_account")
    elif not draft.category:
        missing.append("category")
    return missing


def occurred_at(draft: Draft) -> Optional[datetime]:
    return datetime.fromisoformat(draft.occurred_at) if draft.occurred_at else None


async def mark_duplicate(user_id: int, draft: Draft, now: datetime) -> Draft:
    """Flag a draft that looks like an already saved operation (same input, or same amount/account/time)."""
    similar = await db.find_similar(user_id, draft.amount_minor, draft.account_id,
                                    occurred_at(draft) or now, source_ref=draft.source_ref)
    draft.duplicate = bool(similar)
    return draft


async def save_draft(user_id: int, draft: Draft) -> db.SavedOperation:
    """Write a complete draft through the regular service layer (source='ai'). Raises db.FinanceError."""
    if missing_fields(draft):
        raise db.InvalidValue()
    if draft.kind == "transfer":
        return await db.record_transfer(user_id, draft.account_id, draft.to_account_id, draft.amount_minor,
                                        note=draft.note, occurred_at=occurred_at(draft), source="ai",
                                        source_ref=draft.source_ref)
    return await db.record_operation(
        user_id, draft.kind, draft.currency, [db.Leg(draft.account_id, draft.amount_minor)],
        category=draft.category, subcategory=draft.subcategory, note=draft.note,
        occurred_at=occurred_at(draft), source="ai", source_ref=draft.source_ref)
