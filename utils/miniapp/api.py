"""JSON API of the Mini App (webapp/) and the static files it needs.

Every /api/ request must carry Telegram.WebApp.initData in the X-Telegram-Init-Data header; it is validated
with the bot token (auth.py) and only owners, superadmins and granted users get through (utils/db_api/access.py,
the same rule as middlewares/access.py); request["role"] carries the caller's role.
Amounts are integers in minor units (amount * 100), like in the database. This module has the auth middleware, the
accounts (cards) endpoints and the app factory; the other screens are in screens.py.
"""
import logging
from pathlib import Path
from typing import Optional

from aiohttp import web

from utils.db_api import access
from utils.db_api import finance as db
from utils.i18n import guess_language, webapp_texts

from . import screens, users
from .auth import InitDataError, validate_init_data
from .common import ApiError, account_json, minor, path_id, read_json, totals_json

ROOT_DIR = Path(__file__).resolve().parents[2]
WEBAPP_DIR = ROOT_DIR / "webapp"
FONTS_DIR = ROOT_DIR / "assets" / "fonts"
INIT_DATA_HEADER = "X-Telegram-Init-Data"
RECENT_LIMIT = 10

# Application keys (aiohttp 3.8, pinned by aiogram 2, has no web.AppKey)
BOT_TOKEN = "miniapp_bot_token"
ALERT_SENDER = screens.ALERT_SENDER
BOT = users.BOT

log = logging.getLogger(__name__)

ERRORS = {  # domain error -> (HTTP status, code shown by the app)
    db.AccountNotFound: (404, "not_found"),
    db.OperationNotFound: (404, "not_found"),
    db.Last4Taken: (409, "last4_taken"),
    db.CurrencyLocked: (409, "currency_locked"),
    db.CurrencyMismatch: (409, "currency_mismatch"),
    db.SameAccount: (400, "same_account"),
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
    user_id, tg_user = fields["user_id"], fields["user"]
    role = await access.role_of(user_id, tg_user.get("username"),
                                access.full_name(tg_user.get("first_name"), tg_user.get("last_name")))
    if role is None:
        log.info("Mini App request from %s refused: no access", user_id)
        return refusal(request, 403, "forbidden", tg_user.get("language_code"))
    request["user_id"] = user_id
    request["role"] = role
    request["language_code"] = fields["user"].get("language_code")
    try:
        return await handler(request)
    except ApiError as err:
        return web.json_response({"error": err.code}, status=err.status)
    except db.FinanceError as err:
        status, code = next((v for k, v in ERRORS.items() if isinstance(err, k)), (400, "invalid"))
        return web.json_response({"error": code}, status=status)


# ---- Serialization ----

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
    return path_id(request, "account_id")


# ---- Input ----

async def read_form(request: web.Request) -> dict:
    """Validated account fields from the JSON body of a create / update request."""
    data = await read_json(request)
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
    balance = minor(data.get("balance_minor"), "amount")  # credit: the current debt
    limit = minor(data.get("credit_limit_minor") or 0, "amount") if credit else 0
    return {
        "name": name, "card_type": card_type, "last4": last4 or None, "currency": currency,
        "kind": "cash" if card_type == "cash" else ("credit" if credit else "debit"),
        "balance_minor": -balance if credit else balance,  # debt is stored as a negative balance
        "credit_limit_minor": limit,
    }


# ---- Handlers ----

async def me(request: web.Request) -> web.Response:
    """Language and texts of the app, plus whether AI is configured (the report's advice box needs it)."""
    from utils.ai import core as ai

    lang = await db.get_language(request["user_id"]) or guess_language(request["language_code"])
    return web.json_response({"lang": lang, "texts": webapp_texts(lang), "ai": bool(ai.get_client().configured)})


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


def create_app(bot_token: str, alert_sender=None, bot=None) -> web.Application:
    """alert_sender: async (user_id, lang, *saved) that sends limit alerts; default: the bot (notify_alerts).
    bot: the aiogram Bot that sends the access messages of the Users screen; default: the bot of loader.py."""
    app = web.Application(middlewares=[auth_middleware], client_max_size=64 * 1024)
    app[BOT_TOKEN] = bot_token
    app[ALERT_SENDER] = alert_sender
    app[BOT] = bot
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/accounts", list_accounts)
    app.router.add_post("/api/accounts", create_account)
    app.router.add_get("/api/accounts/{account_id}", get_account)
    app.router.add_put("/api/accounts/{account_id}", update_account)
    app.router.add_delete("/api/accounts/{account_id}", delete_account)
    screens.add_routes(app)
    users.add_routes(app)
    app.router.add_static("/static/", WEBAPP_DIR)
    app.router.add_static("/fonts/", FONTS_DIR)
    return app

