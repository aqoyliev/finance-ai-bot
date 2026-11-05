"""Mini App API behind the screens Home, NewOp (add / edit / delete operations), History, Report and Settings
(with Budgets). Registered by api.create_app next to the accounts endpoints; the auth middleware in api.py has
already checked initData and the caller's role, so request["user_id"] is the caller and every query is scoped to it.

Writes go through the same service functions the bot used (record_operation, record_transfer, update_*,
delete_operation, set_budget, ...), and limit alerts are sent to the chat exactly as after a save in the bot.
"""
import asyncio
import logging
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from aiohttp import web

from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.i18n import LANGUAGES

from . import users
from .common import (MAX_NOTE_LENGTH, MAX_QUERY_LENGTH, ApiError, account_json, clean_text, current_user, int_id,
                     minor, moment_text, parse_moment, path_id, query_int, rate_json, read_json, to_uzs,
                     tx_row_json)

log = logging.getLogger(__name__)

ALERT_SENDER = "miniapp_alert_sender"  # app key: async (user_id, lang, *saved) -> None
KINDS = ("expense", "income", "transfer")
PERIODS = ("week", "month", "year")
HOME_RECENT = 3
PAGE_SIZE = 30
MAX_PAGE = 100
MAX_OFFSET = 4900  # search_transactions reads at most 5000 rows
MAX_RATE = Decimal(10_000_000)
ADVICE_TTL = 30 * 60  # seconds an AI advice is reused for the same user, period, language and day
ADVICE_KIND = {"week": "weekly", "month": "now", "year": "now"}
_advice_cache: Dict[Tuple[int, str, str, date], Tuple[float, Optional[str]]] = {}
_advice_locks: Dict[int, asyncio.Lock] = {}


async def default_alert_sender(user_id: int, lang: str, *saved: db.SavedOperation) -> None:
    from utils.notify_alerts import send_alerts  # imports the bot (loader); only needed when something is saved
    await send_alerts(user_id, lang, *saved)


async def send_alerts(request: web.Request, user, *saved: db.SavedOperation) -> None:
    sender = request.app.get(ALERT_SENDER) or default_alert_sender
    try:
        await sender(user.id, user.language, *saved)
    except Exception:  # noqa: BLE001  an alert must never fail a save
        log.exception("Mini App: could not send limit alerts")


# ---- Shared pieces ----

async def rate_of(user_id: int):
    info = await db.get_usd_rate_info(user_id)
    return info, (info.rate if info else None)


def money_pair(by_currency: Dict[str, int], rate: Optional[Decimal]) -> dict:
    """UZS figure plus the USD one: combined into UZS when a rate is known, else kept apart."""
    uzs, usd = by_currency.get("UZS", 0), by_currency.get("USD", 0)
    if rate and usd:
        return {"uzs_minor": uzs + to_uzs(usd, "USD", rate), "usd_minor": 0, "converted": True}
    return {"uzs_minor": uzs, "usd_minor": usd, "converted": False}


# ---- Home ----

def headline_month(start: date) -> int:
    """The calendar month most of the financial period [start, start + 1 month) falls in."""
    return start.month if start.day <= 15 else start.month % 12 + 1


async def home(request: web.Request) -> web.Response:
    user = await current_user(request)
    today = db.now().date()
    start, end = db.period_bounds(user.salary_day, today)
    info, rate = await rate_of(user.id)
    accounts = await db.list_accounts(user.id)
    balances: Dict[str, int] = {}
    for account in accounts:
        balances[account.currency] = balances.get(account.currency, 0) + account.balance_minor
    totals = await db.period_totals(user.id, start, end)

    limit = None
    usages = await db.budget_usages(user.id)
    usable = [u for u in usages if u.currency == "UZS" or rate]  # a USD budget needs a rate to add up
    if usable:
        total_limit = sum(to_uzs(u.limit, u.currency, rate) for u in usable)
        spent = sum(to_uzs(u.spent, u.currency, rate) for u in usable)
        limit = {"limit_minor": total_limit, "spent_minor": spent, "count": len(usages),
                 "percent": spent * 100 // total_limit if total_limit else 0,
                 "left_minor": max(total_limit - spent, 0)}

    recent = await db.search_transactions(user.id, limit=HOME_RECENT)
    return web.json_response({
        "month": headline_month(start),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "rate": rate_json(info),
        "balance": money_pair(balances, rate),
        "expense": money_pair({c: totals.get(("expense", c), 0) for c in db.CURRENCIES}, rate),
        "income": money_pair({c: totals.get(("income", c), 0) for c in db.CURRENCIES}, rate),
        "limit": limit,
        "accounts": [account_json(a) for a in accounts],
        "recent": [tx_row_json(row) for row in recent.rows],
    })


# ---- NewOp: form data, create, read, edit, delete ----

async def form(request: web.Request) -> web.Response:
    """Everything the operation form needs: categories with subcategories and the active accounts."""
    user = await current_user(request)
    tree = await db.category_tree(user.id)
    return web.json_response({
        "categories": {kind: [{"name": name, "subcategories": subs} for name, subs in items]
                       for kind, items in tree.items()},
        "accounts": [account_json(a) for a in await db.list_accounts(user.id)],
        "now": moment_text(db.now()),
    })


async def checked_category(user_id: int, kind: str, category, subcategory) -> Tuple[str, Optional[str]]:
    """The category (required) and subcategory (optional, expenses only) must be the user's own."""
    if not isinstance(category, str) or not category:
        raise ApiError(400, "category")
    tree = dict((await db.category_tree(user_id)).get(kind, []))
    if category not in tree:
        raise ApiError(400, "category")
    if subcategory in (None, ""):
        return category, None
    if kind != "expense" or not isinstance(subcategory, str) or subcategory not in tree[category]:
        raise ApiError(400, "category")
    return category, subcategory


async def read_operation(request: web.Request, user, kind: Optional[str] = None) -> dict:
    """Validated fields of a create / edit request. `kind` fixes the kind (edit)."""
    data = await read_json(request)
    kind = kind or data.get("kind")
    if kind not in KINDS:
        raise ApiError(400, "invalid")
    fields = {"kind": kind, "amount_minor": minor(data.get("amount_minor"), "amount", minimum=1),
              "note": clean_text(data.get("note"), MAX_NOTE_LENGTH, "note"),
              "occurred_at": parse_moment(data["occurred_at"]) if data.get("occurred_at") else None}
    if kind == "transfer":
        fields["from_account_id"] = int_id(data.get("from_account_id"), "account")
        fields["to_account_id"] = int_id(data.get("to_account_id"), "account")
        if fields["from_account_id"] == fields["to_account_id"]:
            raise ApiError(400, "same_account")
        return fields
    if data.get("currency") not in db.CURRENCIES:
        raise ApiError(400, "invalid")
    fields["currency"] = data["currency"]
    fields["account_id"] = int_id(data.get("account_id"), "account")
    fields["category"], fields["subcategory"] = await checked_category(
        user.id, kind, data.get("category"), data.get("subcategory"))
    return fields


def saved_json(saved: List[db.SavedOperation]) -> dict:
    over = {a.id: a.name for op in saved for a in op.over_limit}
    return {"over_limit": list(over.values())}


async def create_operation(request: web.Request) -> web.Response:
    user = await current_user(request)
    fields = await read_operation(request, user)
    if fields["kind"] == "transfer":
        saved = await db.record_transfer(user.id, fields["from_account_id"], fields["to_account_id"],
                                         fields["amount_minor"], note=fields["note"],
                                         occurred_at=fields["occurred_at"])
    else:
        saved = await db.record_operation(
            user.id, fields["kind"], fields["currency"], [db.Leg(fields["account_id"], fields["amount_minor"])],
            category=fields["category"], subcategory=fields["subcategory"], note=fields["note"],
            occurred_at=fields["occurred_at"])
    await send_alerts(request, user, saved)
    view = await db.get_operation(user.id, saved.transactions[0].id)
    return web.json_response({"operation": view_json(view), **saved_json([saved])}, status=201)


def view_json(view: db.OperationView) -> dict:
    tx = view.tx
    result = {
        "id": tx.id, "kind": tx.kind, "amount_minor": tx.amount_minor, "currency": tx.currency,
        "category": tx.category, "subcategory": tx.subcategory, "note": tx.note,
        "occurred_at": moment_text(tx.occurred_at), "account": account_json(view.account),
    }
    if view.is_transfer and view.counterpart_account is not None:
        result["to_account"] = account_json(view.counterpart_account)
    return result


async def get_operation(request: web.Request) -> web.Response:
    user = await current_user(request)
    view = await db.get_operation(user.id, path_id(request, "tx_id"))
    return web.json_response({"operation": view_json(view)})


async def update_operation(request: web.Request) -> web.Response:
    """Edit through the bot's service functions: amount, category, account (expense / income), note and time.
    The kind, the currency and the accounts of a transfer stay as they are."""
    user = await current_user(request)
    view = await db.get_operation(user.id, path_id(request, "tx_id"))
    tx = view.tx
    fields = await read_operation(request, user, kind=tx.kind)
    if tx.kind == "transfer":
        to_id = view.counterpart_account.id if view.counterpart_account else None
        if (fields["from_account_id"], fields["to_account_id"]) != (view.account.id, to_id):
            raise ApiError(400, "locked")
    else:
        if fields["currency"] != tx.currency:
            raise ApiError(400, "locked")
        if fields["account_id"] != tx.account_id:
            target = await db.get_account(user.id, fields["account_id"])
            if target is None:
                raise ApiError(404, "not_found")
            if target.currency != tx.currency:
                raise db.CurrencyMismatch(target.currency)

    saved: List[db.SavedOperation] = []
    if fields["amount_minor"] != tx.amount_minor:
        saved.append(await db.update_amount(user.id, tx.id, fields["amount_minor"]))
    if tx.kind != "transfer":
        if (fields["category"], fields["subcategory"]) != (tx.category, tx.subcategory):
            changed = await db.update_category(user.id, tx.id, fields["category"], fields["subcategory"])
            saved.append(db.SavedOperation(changed.group_id, [changed]))
        if fields["account_id"] != tx.account_id:
            saved.append(await db.update_account(user.id, tx.id, fields["account_id"]))
    occurred_at = fields["occurred_at"] or tx.occurred_at
    if fields["note"] != tx.note or occurred_at != tx.occurred_at:
        await db.update_details(user.id, tx.id, fields["note"], occurred_at)
    if saved:
        await send_alerts(request, user, *saved)
    view = await db.get_operation(user.id, tx.id)
    return web.json_response({"operation": view_json(view), **saved_json(saved)})


async def delete_operation(request: web.Request) -> web.Response:
    user = await current_user(request)
    await db.delete_operation(user.id, path_id(request, "tx_id"))
    return web.json_response({"result": "deleted"})


# ---- History ----

async def history(request: web.Request) -> web.Response:
    """Operations newest first: ?q= (note / category / subcategory), ?kind=expense|income, ?account_id=,
    ?offset= and ?limit= for paging."""
    user = await current_user(request)
    text = clean_text(request.query.get("q"), MAX_QUERY_LENGTH)
    kind = request.query.get("kind") or None
    if kind not in (None, "all", "expense", "income"):
        raise ApiError(400, "invalid")
    account_id = query_int(request, "account_id", None, 1, 2 ** 63 - 1)
    offset = query_int(request, "offset", 0, 0, MAX_OFFSET)
    limit = query_int(request, "limit", PAGE_SIZE, 1, MAX_PAGE)
    result = await db.search_transactions(
        user.id, kind=None if kind in (None, "all") else kind, text=text,
        account_ids=[account_id] if account_id else None, limit=offset + limit)
    rows = result.rows[offset:offset + limit]
    more = offset + len(rows) < result.count
    return web.json_response({"operations": [tx_row_json(row) for row in rows], "total": result.count,
                              "next_offset": offset + len(rows) if more else None})


# ---- Report ----

def report_window(period: str, today: date, salary_day: int) -> Tuple[date, date, date, date]:
    """(start, end, compare_start, compare_end), ends exclusive. A running period is compared with the same
    number of days of the previous one (the rule of the bot's report)."""
    if period == "month":
        start, end = db.period_bounds(salary_day, today)
        return (start, end) + db.comparison_window(start, end, today)
    if period == "week":  # Monday to Sunday
        start = today - timedelta(days=today.weekday())
        end, prev_start = start + timedelta(days=7), start - timedelta(days=7)
    else:  # calendar year
        start, end = date(today.year, 1, 1), date(today.year + 1, 1, 1)
        prev_start = date(today.year - 1, 1, 1)
    elapsed = (today - start).days + 1
    return start, end, prev_start, min(prev_start + timedelta(days=elapsed), start)


def section(currency: str, converted: bool, income: int, expense: int, prev_expense: int,
            categories: Dict[str, int]) -> dict:
    rows = sorted(categories.items(), key=lambda item: (-item[1], item[0]))
    return {
        "currency": currency, "converted": converted, "income_minor": income, "expense_minor": expense,
        "prev_expense_minor": prev_expense, "balance_minor": income - expense,
        "change_percent": rep.change_percent(expense, prev_expense),
        "categories": [{"name": name, "amount_minor": amount, "share": rep.share_percent(amount, expense)}
                       for name, amount in rows if amount],
    }


def report_sections(current: db.RangeSummary, previous: db.RangeSummary, rate: Optional[Decimal]) -> List[dict]:
    """One section per currency with data; with a rate and both currencies, a single section in UZS."""
    used = [c for c in db.CURRENCIES if current.total("income", c) or current.total("expense", c)
            or previous.total("expense", c)]
    if rate and len(used) > 1:
        def uzs(summary, kind):
            return sum(to_uzs(summary.total(kind, c), c, rate) for c in db.CURRENCIES)

        merged: Dict[str, int] = {}
        for (currency, name), amount in current.expense_by_category.items():
            merged[name] = merged.get(name, 0) + to_uzs(amount, currency, rate)
        return [section("UZS", True, uzs(current, "income"), uzs(current, "expense"), uzs(previous, "expense"),
                        merged)]
    return [section(c, False, current.total("income", c), current.total("expense", c),
                    previous.total("expense", c),
                    {name: amount for (cur, name), amount in current.expense_by_category.items() if cur == c})
            for c in used]


def period_of(request: web.Request) -> str:
    period = request.query.get("period", "month")
    if period not in PERIODS:
        raise ApiError(400, "invalid")
    return period


async def report(request: web.Request) -> web.Response:
    user = await current_user(request)
    period = period_of(request)
    today = db.now().date()
    start, end, cmp_start, cmp_end = report_window(period, today, user.salary_day)
    current = await db.range_summary(user.id, start, end)
    previous = await db.range_summary(user.id, cmp_start, cmp_end)
    _, rate = await rate_of(user.id)
    return web.json_response({
        "period": period,
        "start": start.isoformat(), "last_day": min(end - timedelta(days=1), today).isoformat(),
        "compare_start": cmp_start.isoformat(), "compare_last_day": (cmp_end - timedelta(days=1)).isoformat(),
        "sections": report_sections(current, previous, rate),
    })


async def report_subcategories(request: web.Request) -> web.Response:
    """Subcategories of one expense category in the report window (?period=, ?category=, ?currency=)."""
    user = await current_user(request)
    period = period_of(request)
    category = request.query.get("category", "")
    currency = request.query.get("currency", "UZS")
    converted = request.query.get("converted") == "1"
    if not category or len(category) > 200 or currency not in db.CURRENCIES:
        raise ApiError(400, "invalid")
    start, end, _, _ = report_window(period, db.now().date(), user.salary_day)
    by_currency = await db.expense_by_subcategory(user.id, category, start, end)
    _, rate = await rate_of(user.id)
    totals: Dict[str, int] = {}
    for cur, items in by_currency.items():
        if not converted and cur != currency:
            continue
        for name, amount in items:
            totals[name] = totals.get(name, 0) + (to_uzs(amount, cur, rate) if converted else amount)
    rows = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return web.json_response({"subcategories": [
        {"name": None if name == rep.NO_CATEGORY else name, "amount_minor": amount} for name, amount in rows]})


async def advice(request: web.Request) -> web.Response:
    """AI advice for the report (loaded lazily, may take a while). {"text": null} when AI is off or fails."""
    from utils.ai import assistant
    from utils.ai import core as ai

    user = await current_user(request)
    period = period_of(request)
    client = ai.get_client()
    if not client.configured:
        return web.json_response({"text": None, "reason": "not_configured"})
    today = db.now().date()
    key = (user.id, ADVICE_KIND[period], user.language, today)
    lock = _advice_locks.setdefault(user.id, asyncio.Lock())
    async with lock:  # one AI call per user at a time; repeated opens reuse the answer
        cached = _advice_cache.get(key)
        if cached and time.monotonic() - cached[0] < ADVICE_TTL:
            return web.json_response({"text": cached[1], "reason": None if cached[1] else "no_data"})
        try:
            result = await assistant.advice(user.id, ADVICE_KIND[period], user.language, client=client)
        except ai.AIError as err:
            log.info("Mini App advice failed: %s", err)
            return web.json_response({"text": None, "reason": "error"})
        text = result.text if result else None
        _advice_cache[key] = (time.monotonic(), text)
    return web.json_response({"text": text, "reason": None if text else "no_data"})


# ---- Settings ----

async def settings_json(user, role: Optional[str] = None) -> dict:
    info = await db.get_usd_rate_info(user.id)
    budgets = await db.list_budgets(user.id)
    from utils.ai import core as ai
    return {
        "lang": user.language,
        "salary_day": user.salary_day,
        "rate": rate_json(info),
        "rate_manual": bool(info and info.source == "manual"),
        "accounts_count": len(await db.list_accounts(user.id)),
        "budgets_count": len(budgets),
        "advice_weekly": bool(user.advice_weekly),
        "advice_monthly": bool(user.advice_monthly),
        "ai_configured": bool(ai.get_client().configured),
        **(await users.summary(role)),
    }


async def get_settings(request: web.Request) -> web.Response:
    return web.json_response(await settings_json(await current_user(request), request.get("role")))


def parse_rate(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ApiError(400, "rate")
    try:
        rate = Decimal(str(value).replace(" ", "").replace(",", "."))
    except InvalidOperation:
        raise ApiError(400, "rate") from None
    if not rate.is_finite() or rate <= 0 or rate >= MAX_RATE or rate.as_tuple().exponent < -6:
        raise ApiError(400, "rate")
    return rate


async def update_settings(request: web.Request) -> web.Response:
    """Partial update: salary_day (1-28), rate_mode auto | manual (+ rate), advice_weekly / advice_monthly
    (booleans) and lang (uz | ru | en). Everything is checked before anything is saved."""
    user = await current_user(request)
    data = await read_json(request)
    changes = []
    if "salary_day" in data:
        day = data["salary_day"]
        if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 28:
            raise ApiError(400, "salary_day")
        changes.append(lambda: db.set_salary_day(user.id, day))
    if "rate_mode" in data:
        if data["rate_mode"] == "auto":
            changes.append(lambda: db.clear_usd_rate(user.id))
        elif data["rate_mode"] == "manual":
            rate = parse_rate(data.get("rate"))
            changes.append(lambda: db.set_usd_rate(user.id, rate))
        else:
            raise ApiError(400, "invalid")
    for kind in db.ADVICE_KINDS:
        key = f"advice_{kind}"
        if key in data:
            if not isinstance(data[key], bool):
                raise ApiError(400, "invalid")
            if data[key] != bool(getattr(user, key)):
                changes.append(lambda kind=kind: db.toggle_advice(user.id, kind))
    if "lang" in data:
        if data["lang"] not in LANGUAGES:
            raise ApiError(400, "invalid")
        changes.append(lambda: db.set_language(user.id, user.username, data["lang"]))
    if not changes:
        raise ApiError(400, "invalid")
    for change in changes:
        await change()
    return web.json_response(await settings_json(await current_user(request), request.get("role")))


# ---- Budgets ----

async def budgets(request: web.Request) -> web.Response:
    user = await current_user(request)
    start, end = db.period_bounds(user.salary_day, db.now().date())
    usages = await db.budget_usages(user.id)
    return web.json_response({
        "period": {"start": start.isoformat(), "end": end.isoformat(),
                   "last_day": (end - timedelta(days=1)).isoformat()},
        "budgets": [{"category": u.category, "currency": u.currency, "limit_minor": u.limit,
                     "spent_minor": u.spent, "percent": u.percent} for u in usages],
        "categories": [c.name for c in await db.list_categories(user.id, "expense")],
    })


async def set_budget(request: web.Request) -> web.Response:
    """Create or change the monthly limit of an expense category (alerts of the category start over)."""
    user = await current_user(request)
    data = await read_json(request)
    category = data.get("category")
    if not isinstance(category, str) or not category or data.get("currency") not in db.CURRENCIES:
        raise ApiError(400, "invalid")
    amount = minor(data.get("amount_minor"), "amount", minimum=1)
    if category not in [c.name for c in await db.list_categories(user.id, "expense")]:
        raise ApiError(400, "category")
    budget = await db.set_budget(user.id, category, data["currency"], amount)
    return web.json_response({"budget": {"category": budget.category, "currency": budget.currency,
                                         "limit_minor": budget.amount_minor}})


async def delete_budget(request: web.Request) -> web.Response:
    user = await current_user(request)
    category = request.query.get("category", "")
    if not category or len(category) > 200:
        raise ApiError(400, "invalid")
    if not await db.remove_budget(user.id, category):
        raise ApiError(404, "not_found")
    return web.json_response({"result": "deleted"})


def add_routes(app: web.Application) -> None:
    app.router.add_get("/api/home", home)
    app.router.add_get("/api/form", form)
    app.router.add_get("/api/operations", history)
    app.router.add_post("/api/operations", create_operation)
    app.router.add_get("/api/operations/{tx_id}", get_operation)
    app.router.add_put("/api/operations/{tx_id}", update_operation)
    app.router.add_delete("/api/operations/{tx_id}", delete_operation)
    app.router.add_get("/api/report", report)
    app.router.add_get("/api/report/subcategories", report_subcategories)
    app.router.add_get("/api/advice", advice)
    app.router.add_get("/api/settings", get_settings)
    app.router.add_put("/api/settings", update_settings)
    app.router.add_get("/api/budgets", budgets)
    app.router.add_put("/api/budgets", set_budget)
    app.router.add_delete("/api/budgets", delete_budget)
