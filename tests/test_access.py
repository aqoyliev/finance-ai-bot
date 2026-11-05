"""Role-based access: roles, grants, visitors, the Users API of the Mini App, the access middleware and the chat side
(grant button, shared contacts)."""
from types import SimpleNamespace

import pytest
from aiogram import types
from aiohttp.test_utils import TestClient, TestServer

from data import config
from utils.db_api import access
from utils.db_api import finance as db
from utils.miniapp.api import create_app

from test_miniapp import ADMIN, STRANGER, TOKEN, auth, init_data

OWNER = ADMIN  # ADMINS=7 in conftest
SUPER, USER_ID, VISITOR = 70, 71, 72


class FakeBot:
    def __init__(self, fail=False):
        self.sent = []
        self.menus = []
        self.fail = fail

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        if self.fail:
            raise RuntimeError("blocked")
        self.sent.append((chat_id, text, reply_markup))

    async def set_chat_menu_button(self, chat_id=None, menu_button=None):
        self.menus.append((chat_id, menu_button))


@pytest.fixture(autouse=True)
def superadmins(monkeypatch):
    monkeypatch.setattr(config, "SUPERADMIN_IDS", frozenset({SUPER}))


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
async def client(bot):
    async with TestClient(TestServer(create_app(TOKEN, bot=bot))) as test_client:
        yield test_client


def headers(user_id, **user):
    from test_miniapp import INIT_DATA_HEADER
    import json
    import time
    from urllib.parse import urlencode

    from utils.miniapp.auth import sign

    fields = {"auth_date": str(int(time.time())),
              "user": json.dumps({"id": user_id, "first_name": "X", "language_code": "en", **user})}
    fields["hash"] = sign(fields, TOKEN)
    return {INIT_DATA_HEADER: urlencode(fields)}


# ---- Roles ----

async def test_roles():
    assert await access.role_of(OWNER) == "owner"
    assert await access.role_of(SUPER) == "superadmin"
    assert await access.role_of(USER_ID) is None
    await access.grant_by_id(USER_ID, OWNER)
    assert await access.role_of(USER_ID) == "user"
    assert await access.is_allowed(USER_ID) and not await access.is_allowed(STRANGER)
    assert access.manager_ids() == [OWNER, SUPER]


async def test_superadmin_listed_in_admins_too_is_an_owner(monkeypatch):
    monkeypatch.setattr(config, "SUPERADMIN_IDS", frozenset({OWNER, SUPER}))
    assert await access.role_of(OWNER) == "owner"
    assert access.manager_ids() == [OWNER, SUPER]


@pytest.mark.parametrize("raw, clean", [("@Ali_Valiev", "ali_valiev"), ("ali_valiev", "ali_valiev"),
                                        ("https://t.me/Ali_Valiev", "ali_valiev"), ("t.me/ali_valiev/", "ali_valiev"),
                                        ("  @abcde ", "abcde"), ("abcd", None), ("a" * 33, None),
                                        ("ali-valiev", None), ("алишер", None), ("", None), (None, None), (5, None)])
def test_clean_username(raw, clean):
    assert access.clean_username(raw) == clean


async def test_pending_username_grant_is_bound_on_first_access():
    grant, bound = await access.grant_by_username("@Ali_Valiev", OWNER)
    assert not bound and grant.user_id is None and grant.username == "ali_valiev"
    assert await access.role_of(USER_ID, "someone_else") is None
    assert await access.role_of(USER_ID, "ALI_valiev", "Ali Valiev") == "user"  # case-insensitive
    [saved] = await access.list_grants()
    assert saved.user_id == USER_ID and saved.display_name == "Ali Valiev"
    assert await access.role_of(USER_ID) == "user"  # by id from now on, even after a username change


async def test_grant_by_username_binds_a_known_visitor_and_refuses_duplicates():
    await access.touch_visitor(VISITOR, "Vali_99", "Vali", "Aliyev")
    grant, bound = await access.grant_by_username("vali_99", OWNER)
    assert bound and grant.user_id == VISITOR and grant.display_name == "Vali Aliyev"
    with pytest.raises(access.AlreadyGranted):
        await access.grant_by_username("@VALI_99", SUPER)
    with pytest.raises(access.AlreadyGranted):
        await access.grant_by_id(VISITOR, OWNER)
    with pytest.raises(access.InvalidUsername):
        await access.grant_by_username("no", OWNER)


async def test_grant_by_id_reuses_a_pending_username_grant():
    await access.grant_by_username("pending_one", OWNER)
    grant = await access.grant_by_id(USER_ID, OWNER, username="Pending_One", display_name="Pen")
    grants = await access.list_grants()
    assert len(grants) == 1 and grants[0].id == grant.id and grants[0].user_id == USER_ID
    assert grants[0].display_name == "Pen"


async def test_owner_and_superadmin_cannot_be_granted_or_listed():
    for fixed in (OWNER, SUPER):
        with pytest.raises(access.AlreadyGranted):
            await access.grant_by_id(fixed, OWNER)


async def test_visitors_never_include_owners_superadmins_or_granted_people():
    assert await access.touch_visitor(OWNER, "boss", "Boss") is False
    assert await access.get_visitor(OWNER) is None  # owners are never stored
    assert await access.touch_visitor(SUPER, "superman", "Super") is True
    assert await access.touch_visitor(USER_ID, "granted_guy", "Granted") is True
    assert await access.touch_visitor(VISITOR, "", "Nameless", "Person") is True
    assert await access.touch_visitor(VISITOR, "", "Nameless", "Person") is False  # a refresh, not a new one
    await access.touch_visitor(80, "pending_guy", "Pending")
    await access.grant_by_id(USER_ID, OWNER)
    await access.grant_by_username("pending_guy_2", OWNER)
    await access.touch_visitor(81, "Pending_Guy_2", "Waiting")  # matches a pending grant: hidden as well
    ids = [v.user_id for v in await access.search_visitors()]
    assert ids == [80, VISITOR]  # newest first
    assert [v.user_id for v in await access.search_visitors("nameless pers")] == [VISITOR]
    assert [v.user_id for v in await access.search_visitors("@PENDING")] == [80]
    assert await access.search_visitors("%") == []  # LIKE wildcards are literal


async def test_claim_notice_once():
    assert not await access.claim_notice(VISITOR)  # unknown visitor
    await access.touch_visitor(VISITOR, "", "A")
    assert await access.claim_notice(VISITOR)
    assert not await access.claim_notice(VISITOR)


async def test_revoke_takes_effect_immediately():
    grant = await access.grant_by_id(USER_ID, OWNER)
    assert await access.role_of(USER_ID) == "user"
    await access.revoke(grant.id)
    assert await access.role_of(USER_ID) is None
    with pytest.raises(access.GrantNotFound):
        await access.revoke(grant.id)


# ---- Mini App API ----

USER_ENDPOINTS = [("GET", "/api/users"), ("POST", "/api/users"), ("POST", "/api/users/72/grant"),
                  ("DELETE", "/api/users/1"), ("GET", "/api/visitors"), ("POST", "/api/users/pick")]


@pytest.mark.parametrize("method, path", USER_ENDPOINTS)
async def test_users_endpoints_are_for_managers_only(client, method, path):
    assert (await client.request(method, path)).status == 401
    res = await client.request(method, path, headers=auth(STRANGER), json={})
    assert res.status == 403 and (await res.json())["error"] == "forbidden"
    await access.grant_by_id(USER_ID, OWNER)
    res = await client.request(method, path, headers=auth(USER_ID), json={"username": "someone_x"})
    assert res.status == 403 and (await res.json())["error"] == "not_manager"
    assert len(await access.list_grants()) == 1


async def test_granted_user_uses_the_app_with_own_data(client):
    await access.grant_by_id(USER_ID, OWNER)
    await db.set_language(USER_ID, "u", "en")
    body = await (await client.get("/api/settings", headers=auth(USER_ID))).json()
    assert body["can_manage_users"] is False and body["users_count"] == 0
    accounts = await (await client.get("/api/accounts", headers=auth(USER_ID))).json()
    assert all(a["name"] for a in accounts["accounts"])


async def test_settings_shows_users_row_to_managers(client):
    await db.set_language(OWNER, "owner", "uz")
    await access.grant_by_id(USER_ID, OWNER)
    await access.grant_by_username("waiting_one", OWNER)
    body = await (await client.get("/api/settings", headers=auth())).json()
    assert body["can_manage_users"] is True and body["users_count"] == 2
    await db.set_language(SUPER, "s", "ru")
    body = await (await client.get("/api/settings", headers=auth(SUPER))).json()
    assert body["can_manage_users"] is True


async def test_add_by_username_duplicate_and_invalid(client, bot):
    res = await client.post("/api/users", json={"username": "@New_Person"}, headers=auth())
    assert res.status == 201
    grant = (await res.json())["grant"]
    assert grant["pending"] is True and grant["username"] == "new_person" and grant["user_id"] is None
    assert bot.sent == []  # nobody to tell yet
    res = await client.post("/api/users", json={"username": "https://t.me/new_person"}, headers=auth(SUPER))
    assert res.status == 409 and (await res.json())["error"] == "exists"
    for bad in ("abc", "with space", "", None, 123, "a" * 40):
        res = await client.post("/api/users", json={"username": bad}, headers=auth())
        assert res.status == 400 and (await res.json())["error"] == "username", bad
    body = await (await client.get("/api/users", headers=auth())).json()
    assert body == {"grants": [{"id": grant["id"], "user_id": None, "username": "new_person", "display_name": "",
                                "pending": True}]}


async def test_add_by_username_of_a_visitor_binds_and_notifies(client, bot, monkeypatch):
    monkeypatch.setattr(config, "WEBAPP_ENABLED", True)
    monkeypatch.setattr(config, "WEBAPP_URL", "https://example.test")
    await access.touch_visitor(VISITOR, "known_one", "Known", None, "ru")
    res = await client.post("/api/users", json={"username": "known_one"}, headers=auth())
    grant = (await res.json())["grant"]
    assert res.status == 201 and grant["user_id"] == VISITOR and grant["pending"] is False
    [(chat, text, markup)] = bot.sent
    assert chat == VISITOR and "/start" in text and "доступ" in text  # in the visitor's language
    assert markup.inline_keyboard[0][0].web_app.url.startswith("https://example.test")
    assert bot.menus and bot.menus[0][0] == VISITOR


async def test_pending_grant_binds_through_the_mini_app(client):
    await client.post("/api/users", json={"username": "app_first"}, headers=auth())
    res = await client.get("/api/me", headers=headers(USER_ID, username="App_First", first_name="App",
                                                      last_name="First"))
    assert res.status == 200
    [grant] = await access.list_grants()
    assert grant.user_id == USER_ID and grant.display_name == "App First"


async def test_grant_visitor_by_id_and_revoke(client, bot):
    await access.touch_visitor(VISITOR, "", "Nameless")
    res = await client.post(f"/api/users/{VISITOR}/grant", headers=auth(SUPER))
    grant = (await res.json())["grant"]
    assert res.status == 201 and grant == {"id": grant["id"], "user_id": VISITOR, "username": "",
                                           "display_name": "Nameless", "pending": False}
    assert bot.sent[0][0] == VISITOR
    assert (await client.post(f"/api/users/{VISITOR}/grant", headers=auth())).status == 409
    assert (await client.post("/api/users/999999/grant", headers=auth())).status == 404  # not a visitor
    await db.set_language(VISITOR, "", "uz")
    assert (await client.get("/api/settings", headers=auth(VISITOR))).status == 200

    res = await client.delete(f"/api/users/{grant['id']}", headers=auth())
    assert res.status == 200
    assert (await client.get("/api/settings", headers=auth(VISITOR))).status == 403  # immediately
    assert bot.menus[-1][0] == VISITOR and isinstance(bot.menus[-1][1], types.MenuButtonDefault)
    assert (await client.delete(f"/api/users/{grant['id']}", headers=auth())).status == 404


async def test_owners_and_superadmins_never_appear_in_answers(client):
    for user_id, name in ((OWNER, "boss_user"), (SUPER, "super_user"), (VISITOR, "plain_user")):
        await access.touch_visitor(user_id, name, name)
    await access.grant_by_id(USER_ID, OWNER)
    users = await (await client.get("/api/users", headers=auth(SUPER))).json()
    visitors = await (await client.get("/api/visitors", headers=auth(SUPER))).json()
    assert [g["user_id"] for g in users["grants"]] == [USER_ID]
    assert "boss" not in str(users) and "super_user" not in str(users)
    assert [v["user_id"] for v in visitors["visitors"]] == [VISITOR]
    assert set(visitors["visitors"][0]) == {"user_id", "username", "name", "last_seen"}
    found = await (await client.get("/api/visitors?q=boss", headers=auth())).json()
    assert found["visitors"] == []
    # the owner's own id can neither be granted nor revoked through the API
    assert (await client.post(f"/api/users/{OWNER}/grant", headers=auth(SUPER))).status == 404


async def test_pick_sends_the_request_users_keyboard(client, bot):
    await db.set_language(SUPER, "s", "en")
    res = await client.post("/api/users/pick", headers=auth(SUPER))
    assert res.status == 200
    [(chat, text, markup)] = bot.sent
    assert chat == SUPER
    button = markup["keyboard"][0][0]
    assert button["request_users"] == {"request_id": 4207, "user_is_bot": False, "max_quantity": 1,
                                       "request_name": True, "request_username": True}
    assert markup["one_time_keyboard"] is True and markup["keyboard"][1][0]["text"] == "❌ Cancel"


async def test_pick_reports_a_send_failure():
    async with TestClient(TestServer(create_app(TOKEN, bot=FakeBot(fail=True)))) as client:
        res = await client.post("/api/users/pick", headers=auth())
        assert res.status == 502


# ---- Bot: access middleware ----

def message_update(user_id, username="ali_v", chat_type="private", text="/start"):
    user = {"id": user_id, "is_bot": False, "first_name": "Ali", "last_name": "V", "language_code": "ru"}
    if username:
        user["username"] = username
    return types.Update.to_object({"update_id": 1, "message": {
        "message_id": 1, "date": 0, "chat": {"id": user_id, "type": chat_type}, "from": user, "text": text}})


@pytest.fixture
def middleware(monkeypatch):
    from middlewares.access import AccessMiddleware

    knocked, notices = [], []

    async def knock(user):
        knocked.append(user.id)

    async def notify(update, text):
        notices.append((update_user_id(update), text))

    def update_user_id(update):
        return update.message.from_user.id if update.message else update.callback_query.from_user.id

    mw = AccessMiddleware(notify_visitor=knock)
    monkeypatch.setattr(mw, "notify", notify)
    mw.knocked, mw.notices = knocked, notices
    return mw


async def test_middleware_stranger_is_recorded_noticed_and_managers_told_once(middleware):
    from aiogram.dispatcher.handler import CancelHandler

    for _ in range(2):
        with pytest.raises(CancelHandler):
            await middleware.on_pre_process_update(message_update(VISITOR), {})
    assert middleware.knocked == [VISITOR]
    assert middleware.notices == [(VISITOR, "Это личный бот. Доступ закрыт.")]
    visitor = await access.get_visitor(VISITOR)
    assert visitor.username == "ali_v" and visitor.language_code == "ru" and visitor.notified


async def test_middleware_lets_roles_through_and_never_records_owners(middleware):
    await middleware.on_pre_process_update(message_update(OWNER), {})
    await middleware.on_pre_process_update(message_update(SUPER), {})
    assert await access.get_visitor(OWNER) is None
    assert (await access.get_visitor(SUPER)).username == "ali_v"
    await access.grant_by_username("pending_ali", OWNER)
    await middleware.on_pre_process_update(message_update(USER_ID, username="Pending_Ali"), {})  # bound now
    assert await access.role_of(USER_ID) == "user"
    assert middleware.knocked == [] and middleware.notices == []


async def test_middleware_group_messages_are_not_recorded(middleware):
    from aiogram.dispatcher.handler import CancelHandler

    with pytest.raises(CancelHandler):
        await middleware.on_pre_process_update(message_update(VISITOR, chat_type="group"), {})
    assert await access.get_visitor(VISITOR) is None and middleware.knocked == []


async def test_notify_managers_message_and_button(bot):
    from utils import access_notify

    await db.set_language(OWNER, "o", "uz")
    assert await access_notify.notify_managers(bot, VISITOR, None, "Ali V") == 2
    (owner_chat, text, markup), (super_chat, en_text, _) = bot.sent
    assert owner_chat == OWNER and super_chat == SUPER
    assert text == "👤 Ali V (username yo'q) botga kirmoqchi"
    assert markup.inline_keyboard[0][0].text == "✅ Ruxsat berish"
    assert markup.inline_keyboard[0][0].callback_data == f"acc:grant:{VISITOR}"
    bot.sent.clear()
    await access_notify.notify_managers(bot, VISITOR, "ali_v", "Ali <V>")
    assert bot.sent[0][1] == "👤 Ali &lt;V&gt; (@ali_v) botga kirmoqchi"


# ---- Bot: grant button and shared contacts ----

class FakeCall:
    def __init__(self, user_id, data, bot):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = data
        self.bot = bot
        self.answers = []
        self.edits = []
        outer = self

        class Msg:
            async def edit_text(self, text, **kwargs):
                outer.edits.append(text)

            async def edit_reply_markup(self, markup=None):
                outer.edits.append(markup)

        self.message = Msg()

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


@pytest.mark.parametrize("caller", [STRANGER, USER_ID])
async def test_grant_button_refuses_non_managers(bot, caller):
    from handlers.users.access import grant_button

    await access.grant_by_id(USER_ID, OWNER)
    call = FakeCall(caller, f"acc:grant:{VISITOR}", bot)
    await grant_button(call, "en")
    assert call.answers == [("Only an admin can grant access", True)]
    assert await access.role_of(VISITOR) is None and bot.sent == []


@pytest.mark.parametrize("caller", [OWNER, SUPER])
async def test_grant_button_grants_for_managers(bot, caller):
    from handlers.users.access import grant_button

    await access.touch_visitor(VISITOR, "ali_v", "Ali", "V", "en")
    call = FakeCall(caller, f"acc:grant:{VISITOR}", bot)
    await grant_button(call, "en")
    assert await access.role_of(VISITOR) == "user"
    assert call.edits == ["✅ Ali V — access granted"]
    assert bot.sent[0][0] == VISITOR and "You now have access" in bot.sent[0][1]
    again = FakeCall(caller, f"acc:grant:{VISITOR}", bot)
    await grant_button(again, "en")
    assert again.answers == [("This person already has access", True)]


def shared_message(sender, payload):
    return types.Message.to_object({"message_id": 5, "date": 0, "chat": {"id": sender, "type": "private"},
                                    "from": {"id": sender, "is_bot": False, "first_name": "S"}, **payload})


def test_users_shared_is_read_from_the_raw_message():
    from handlers.users.access import has_shared_users, shared_users

    new = shared_message(OWNER, {"users_shared": {"request_id": 4207, "users": [
        {"user_id": VISITOR, "first_name": "Ali", "last_name": "V", "username": "ali_v"}]}})
    assert has_shared_users(new)
    assert shared_users(new) == [{"user_id": VISITOR, "first_name": "Ali", "last_name": "V", "username": "ali_v"}]
    ids_only = shared_message(OWNER, {"users_shared": {"request_id": 4207, "user_ids": [VISITOR]}})
    assert shared_users(ids_only) == [{"user_id": VISITOR}]
    old = shared_message(OWNER, {"user_shared": {"request_id": 4207, "user_id": VISITOR}})
    assert shared_users(old) == [{"user_id": VISITOR}]
    other = shared_message(OWNER, {"users_shared": {"request_id": 1, "users": [{"user_id": VISITOR}]}})
    assert shared_users(other) is None and not has_shared_users(other)
    assert shared_users(shared_message(OWNER, {"text": "hello"})) is None


class SharedChat:
    def __init__(self, sender, payload, bot):
        self.message = shared_message(sender, payload)
        self.replies = []
        outer = self

        class Proxy:
            from_user = self.message.from_user

            def to_python(self):
                return outer.message.to_python()

            async def answer(self, text, reply_markup=None, **kwargs):
                outer.replies.append((text, reply_markup))

        self.proxy = Proxy()
        self.proxy.bot = bot


async def test_shared_contact_is_granted_by_a_manager(bot):
    from handlers.users.access import contact_shared

    chat = SharedChat(SUPER, {"users_shared": {"request_id": 4207, "users": [
        {"user_id": VISITOR, "first_name": "Ali", "last_name": "V", "username": "Ali_V"}]}}, bot)
    await contact_shared(chat.proxy, "en")
    [grant] = await access.list_grants()
    assert grant.user_id == VISITOR and grant.username == "ali_v" and grant.display_name == "Ali V"
    [(text, markup)] = chat.replies
    assert text == "✅ Ali V — access granted" and isinstance(markup, types.ReplyKeyboardRemove)
    assert bot.sent[0][0] == VISITOR

    again = SharedChat(OWNER, {"user_shared": {"request_id": 4207, "user_id": VISITOR}}, bot)
    await contact_shared(again.proxy, "en")
    assert again.replies[0][0] == "This person already has access"


async def test_shared_contact_from_a_regular_user_is_refused(bot):
    from handlers.users.access import contact_shared

    await access.grant_by_id(USER_ID, OWNER)
    chat = SharedChat(USER_ID, {"users_shared": {"request_id": 4207, "users": [{"user_id": VISITOR}]}}, bot)
    await contact_shared(chat.proxy, "en")
    assert await access.role_of(VISITOR) is None and bot.sent == []
    assert chat.replies[0][0] == "Only an admin can grant access"


async def test_picker_cancel_only_for_managers():
    from handlers.users.access import is_picker_cancel

    def msg(user_id, text):
        return SimpleNamespace(text=text, from_user=SimpleNamespace(id=user_id))

    assert await is_picker_cancel(msg(OWNER, "❌ Bekor qilish"))
    assert await is_picker_cancel(msg(SUPER, "❌ Отмена"))
    assert not await is_picker_cancel(msg(USER_ID, "❌ Bekor qilish"))
    assert not await is_picker_cancel(msg(OWNER, "taxi 25000"))


def test_access_handlers_run_before_ai_input():
    from loader import dp
    import handlers  # noqa: F401

    names = [h.handler.__module__ + "." + h.handler.__name__ for h in dp.message_handlers.handlers]
    assert names.index("handlers.users.access.contact_shared") < names.index("handlers.users.ai_input.text_input")
    assert names.index("handlers.users.access.picker_cancel") < names.index("handlers.users.ai_input.text_input")
    callbacks = [h.handler.__module__ + "." + h.handler.__name__ for h in dp.callback_query_handlers.handlers]
    assert callbacks.index("handlers.users.access.grant_button") < callbacks.index("handlers.users.echo.stale_button")


async def test_menu_buttons_cover_owners_superadmins_and_granted_users(bot):
    from utils.miniapp import server

    await access.grant_by_id(USER_ID, OWNER)
    await access.grant_by_username("still_pending", OWNER)
    assert await server.menu_user_ids() == [OWNER, SUPER, USER_ID]
    await server.set_menu_buttons(bot)
    assert [chat for chat, _ in bot.menus] == [OWNER, SUPER, USER_ID]
