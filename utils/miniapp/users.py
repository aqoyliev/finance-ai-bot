"""Mini App API of the Users screen (Settings -> Users): who may use the bot besides the owners and superadmins.

Only owners and superadmins (request["role"], set by the auth middleware in api.py) may call these; a regular
user gets 403 "not_manager". Owners and superadmins themselves never appear in any answer.
Bot messages (the new user is told, the contact picker keyboard) go through utils/access_notify.py.
"""
import logging
from typing import Optional

from aiohttp import web

from utils.db_api import access

from .common import MAX_QUERY_LENGTH, ApiError, path_id, read_json

log = logging.getLogger(__name__)

BOT = "miniapp_bot"  # app key: aiogram Bot used to send messages (None -> loader.bot)


def bot_of(request: web.Request):
    bot = request.app.get(BOT)
    if bot is None:
        from loader import bot  # imports the dispatcher; only needed when a message is sent
    return bot


def require_manager(request: web.Request) -> None:
    if request.get("role") not in access.MANAGER_ROLES:
        raise ApiError(403, "not_manager")


async def summary(role: Optional[str]) -> dict:
    """The Settings fields of this screen: whether the row is shown and how many grants there are."""
    manager = role in access.MANAGER_ROLES
    return {"can_manage_users": manager, "users_count": await access.count_grants() if manager else 0}


def grant_json(grant) -> dict:
    return {"id": grant.id, "user_id": grant.user_id, "username": grant.username or "",
            "display_name": grant.display_name or "", "pending": grant.user_id is None}


def visitor_json(visitor) -> dict:
    return {"user_id": visitor.user_id, "username": visitor.username or "",
            "name": access.full_name(visitor.first_name, visitor.last_name),
            "last_seen": visitor.last_seen.date().isoformat()}


async def granted(request: web.Request, user_id: Optional[int]) -> None:
    """Tell a newly granted user (best effort: never fails the request)."""
    if user_id is None:
        return
    from utils import access_notify
    try:
        await access_notify.notify_granted(bot_of(request), user_id)
    except Exception:  # noqa: BLE001
        log.exception("Could not notify a newly granted user")


# ---- Handlers ----

async def list_users(request: web.Request) -> web.Response:
    require_manager(request)
    return web.json_response({"grants": [grant_json(g) for g in await access.list_grants()]})


async def add_user(request: web.Request) -> web.Response:
    """{username}: '@name', 'name' or a t.me link. 409 if already granted; a known visitor is bound at once."""
    require_manager(request)
    data = await read_json(request)
    try:
        grant, bound = await access.grant_by_username(data.get("username"), request["user_id"])
    except access.InvalidUsername:
        raise ApiError(400, "username") from None
    except access.AlreadyGranted:
        raise ApiError(409, "exists") from None
    if bound:
        await granted(request, grant.user_id)
    return web.json_response({"grant": grant_json(grant)}, status=201)


async def grant_visitor(request: web.Request) -> web.Response:
    require_manager(request)
    user_id = path_id(request, "user_id")
    if await access.get_visitor(user_id) is None:
        raise ApiError(404, "not_found")
    try:
        grant = await access.grant_by_id(user_id, request["user_id"])
    except access.AlreadyGranted:
        raise ApiError(409, "exists") from None
    await granted(request, user_id)
    return web.json_response({"grant": grant_json(grant)}, status=201)


async def revoke_user(request: web.Request) -> web.Response:
    require_manager(request)
    try:
        grant = await access.revoke(path_id(request, "grant_id"))
    except access.GrantNotFound:
        raise ApiError(404, "not_found") from None
    if grant.user_id is not None:
        from utils import access_notify
        await access_notify.reset_menu_button(bot_of(request), grant.user_id)
    return web.json_response({"result": "deleted"})


async def visitors(request: web.Request) -> web.Response:
    require_manager(request)
    query = request.query.get("q", "")[:MAX_QUERY_LENGTH]
    return web.json_response({"visitors": [visitor_json(v) for v in await access.search_visitors(query)]})


async def pick_contact(request: web.Request) -> web.Response:
    """Send the caller the one-time "pick a contact" keyboard in the bot chat (the app then closes itself)."""
    require_manager(request)
    from utils import access_notify
    try:
        await access_notify.send_picker(bot_of(request), request["user_id"])
    except Exception:  # noqa: BLE001  e.g. the chat with the bot was deleted
        log.warning("Could not send the contact picker", exc_info=True)
        raise ApiError(502, "send") from None
    return web.json_response({"result": "sent"})


def add_routes(app: web.Application) -> None:
    app.router.add_get("/api/users", list_users)
    app.router.add_post("/api/users", add_user)
    app.router.add_post("/api/users/pick", pick_contact)
    app.router.add_post("/api/users/{user_id}/grant", grant_visitor)
    app.router.add_delete("/api/users/{grant_id}", revoke_user)
    app.router.add_get("/api/visitors", visitors)
