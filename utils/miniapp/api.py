"""JSON API of the Mini App (webapp/) and the static files it needs.

Every /api/ request must carry Telegram.WebApp.initData in the X-Telegram-Init-Data header; it is validated
with the bot token (auth.py) and only users in ADMINS get through (the same rule as middlewares/access.py).
Amounts are integers in minor units (amount * 100), like in the database.
"""
import logging
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

from aiohttp import web

from utils.db_api import finance as db
from utils.db_api.accounts import MAX_BALANCE_MINOR
from utils.db_api.models import Account
from utils.i18n import guess_language, webapp_texts

from .auth import InitDataError, validate_init_data

ROOT_DIR = Path(__file__).resolve().parents[2]
WEBAPP_DIR = ROOT_DIR / "webapp"
FONTS_DIR = ROOT_DIR / "assets" / "fonts"
INIT_DATA_HEADER = "X-Telegram-Init-Data"
RECENT_LIMIT = 10

# Application keys (aiohttp 3.8, pinned by aiogram 2, has no web.AppKey)
BOT_TOKEN = "miniapp_bot_token"
ALLOWED_IDS = "miniapp_allowed_ids"

log = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


ERRORS = {  # domain error -> (HTTP status, code shown by the app)
    db.AccountNotFound: (404, "not_found"),
    db.Last4Taken: (409, "last4_taken"),
    db.CurrencyLocked: (409, "currency_locked"),
    db.InvalidValue: (400, "invalid"),
}


# ---- Auth ----

def refusal(request: web.Request, status: int, code: str, language_code: Optional[str]) -> web.Response:
    """401 / 403 with a message the app can show before it has loaded its texts."""
    lang = guess_language(language_code or request.headers.get("Accept-Language", "")[:2])
    return web.json_response({"error": code, "message": webapp_texts(lang)[f"err_{code}"]}, status=status)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    try:
        fields = validate_init_data(request.headers.get(INIT_DATA_HEADER), request.app[BOT_TOKEN])
    except InitDataError as err:
        log.info("Mini App request refused: %s", err)  # the reason only, never initData itself
        return refusal(request, 401, "auth", None)
    user_id = fields["user_id"]
    if user_id not in request.app[ALLOWED_IDS]:
        log.info("Mini App request from %s refused: not in ADMINS", user_id)
        return refusal(request, 403, "forbidden", fields["user"].get("language_code"))
    request["user_id"] = user_id
    request["language_code"] = fields["user"].get("language_code")
    try:
        return await handler(request)
    except ApiError as err:
        return web.json_response({"error": err.code}, status=err.status)
    except db.FinanceError as err:
        status, code = next((v for k, v in ERRORS.items() if isinstance(err, k)), (400, "invalid"))
        return web.json_response({"error": code}, status=status)


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


def operation_json(tx) -> dict:
    return {
        "id": tx.id,
        "date": tx.occurred_at.date().isoformat(),
        "kind": tx.kind,
        "direction": tx.direction,
        "amount_minor": tx.amount_minor,
        "currency": tx.currency,
        "category": tx.category,
        "subcategory": tx.subcategory,
    }


def account_id_of(request: web.Request) -> int:
    try:
        return int(request.match_info["account_id"])
    except ValueError:
        raise ApiError(404, "not_found") from None


# ---- Input ----

def _minor(value, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_BALANCE_MINOR:
        raise ApiError(400, code)
    return value


async def read_form(request: web.Request) -> dict:
    """Validated account fields from the JSON body of a create / update request."""
    try:
        data = await request.json()
    except ValueError:
        raise ApiError(400, "invalid") from None
    if not isinstance(data, dict):
        raise ApiError(400, "invalid")
    card_type = data.get("card_type")
    if card_type not in db.CARD_TYPES:
        raise ApiError(400, "invalid")
    name = " ".join(str(data.get("name") or "").split())
    if not name or len(name) > 40:
        raise ApiError(400, "name")
    last4 = str(data.get("last4") or "").strip()
    if (last4 or card_type != "cash") and not (len(last4) == 4 and last4.isdigit()):
        raise ApiError(400, "last4")  # required for a card, optional for cash
    currency = data.get("currency")
    if currency not in db.CURRENCIES:
        raise ApiError(400, "invalid")
    credit = data.get("is_credit") is True and card_type != "cash"
    balance = _minor(data.get("balance_minor"), "amount")  # credit: the current debt
    limit = _minor(data.get("credit_limit_minor") or 0, "amount") if credit else 0
    return {
        "name": name, "card_type": card_type, "last4": last4 or None, "currency": currency,
        "kind": "cash" if card_type == "cash" else ("credit" if credit else "debit"),
        "balance_minor": -balance if credit else balance,  # debt is stored as a negative balance
        "credit_limit_minor": limit,
    }


# ---- Handlers ----

async def me(request: web.Request) -> web.Response:
    lang = await db.get_language(request["user_id"]) or guess_language(request["language_code"])
    return web.json_response({"lang": lang, "texts": webapp_texts(lang)})


async def list_accounts(request: web.Request) -> web.Response:
    accounts = await db.list_accounts(request["user_id"])
    return web.json_response({"accounts": [account_json(a) for a in accounts],
                              "totals": totals_json(accounts), "count": len(accounts)})


async def get_account(request: web.Request) -> web.Response:
    user_id = request["user_id"]
    account = await db.get_account(user_id, account_id_of(request))
    if account is None:
        raise ApiError(404, "not_found")
    user = await db.get_user(user_id)
    start, end = db.period_bounds(user.salary_day if user else 1, db.now().date())
    activity = await db.account_activity(user_id, account.id, start, end, RECENT_LIMIT)
    return web.json_response({
        "account": account_json(account),
        "month": {"start": start.isoformat(), "end": end.isoformat(),
                  "expense_minor": activity.expense_minor, "income_minor": activity.income_minor},
        "operations": [operation_json(tx) for tx in activity.recent],
        "has_operations": bool(activity.recent),
    })


async def create_account(request: web.Request) -> web.Response:
    form = await read_form(request)
    account = await db.create_account(
        request["user_id"], form["name"], form["kind"], form["currency"], form["balance_minor"],
        form["credit_limit_minor"], card_type=form["card_type"], last4=form["last4"])
    return web.json_response({"account": account_json(account)}, status=201)


async def update_account(request: web.Request) -> web.Response:
    form = await read_form(request)
    account = await db.update_account_details(request["user_id"], account_id_of(request), **form)
    return web.json_response({"account": account_json(account)})


async def delete_account(request: web.Request) -> web.Response:
    result = await db.remove_account(request["user_id"], account_id_of(request))
    return web.json_response({"result": result})  # "deleted" | "archived"


# ---- Static files ----

async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEBAPP_DIR / "index.html", headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return web.Response(text="ok")


def create_app(bot_token: str, allowed_ids: Iterable[int]) -> web.Application:
    app = web.Application(middlewares=[auth_middleware], client_max_size=64 * 1024)
    app[BOT_TOKEN] = bot_token
    app[ALLOWED_IDS] = frozenset(allowed_ids)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/accounts", list_accounts)
    app.router.add_post("/api/accounts", create_account)
    app.router.add_get("/api/accounts/{account_id}", get_account)
    app.router.add_put("/api/accounts/{account_id}", update_account)
    app.router.add_delete("/api/accounts/{account_id}", delete_account)
    app.router.add_static("/static/", WEBAPP_DIR)
    app.router.add_static("/fonts/", FONTS_DIR)
    return app

