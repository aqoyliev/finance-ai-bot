"""Mini App: initData validation, the JSON API (aiohttp test client) and SMS matching by the saved last4."""
import json
import time
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer

from utils.ai.parser import AccountRef, UserContext, load_context, match_account
from utils.db_api import finance as db
from utils.i18n import LANGUAGES, WEBAPP_TEXTS
from utils.miniapp.api import INIT_DATA_HEADER, create_app
from utils.miniapp.auth import InitDataError, sign, validate_init_data

TOKEN = "123456:TEST-TOKEN-FOR-TESTS-ONLY-0000000000"
ADMIN, STRANGER = 7, 999


def init_data(user_id: int = ADMIN, auth_date: int = None, token: str = TOKEN, **extra) -> str:
    fields = {"auth_date": str(auth_date if auth_date is not None else int(time.time())),
              "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
              "user": json.dumps({"id": user_id, "first_name": "Owner", "language_code": "en"},
                                 separators=(",", ":")),
              **extra}
    fields["hash"] = sign(fields, token)
    return urlencode(fields)


# ---- initData validation ----

def test_valid_init_data():
    fields = validate_init_data(init_data(), TOKEN)
    assert fields["user_id"] == ADMIN and fields["user"]["first_name"] == "Owner"


def test_tampered_init_data_is_refused():
    data = init_data().replace("Owner", "Admin")
    with pytest.raises(InitDataError):
        validate_init_data(data, TOKEN)


def test_init_data_signed_with_another_token_is_refused():
    with pytest.raises(InitDataError):
        validate_init_data(init_data(token="999:OTHER"), TOKEN)


def test_expired_init_data_is_refused():
    old = int(time.time()) - 25 * 3600
    with pytest.raises(InitDataError):
        validate_init_data(init_data(auth_date=old), TOKEN)
    # just under a day is still fine
    validate_init_data(init_data(auth_date=int(time.time()) - 23 * 3600), TOKEN)


@pytest.mark.parametrize("raw", ["", "garbage", "hash=abc", "auth_date=1&auth_date=2&hash=x"])
def test_malformed_init_data_is_refused(raw):
    with pytest.raises(InitDataError):
        validate_init_data(raw, TOKEN)


def test_init_data_without_hash_is_refused():
    data = init_data()
    stripped = "&".join(p for p in data.split("&") if not p.startswith("hash="))
    with pytest.raises(InitDataError):
        validate_init_data(stripped, TOKEN)


# ---- API ----

@pytest.fixture
async def client():
    server = TestServer(create_app(TOKEN, {ADMIN}))
    async with TestClient(server) as test_client:
        yield test_client


def auth(user_id: int = ADMIN) -> dict:
    return {INIT_DATA_HEADER: init_data(user_id)}


CARD = {"card_type": "uzcard", "name": "Kapitalbank", "last4": "4417", "currency": "UZS",
        "is_credit": False, "balance_minor": 125_000_000}


async def test_api_requires_init_data(client):
    response = await client.get("/api/accounts")
    assert response.status == 401
    assert (await response.json())["error"] == "auth"
    tampered = {INIT_DATA_HEADER: init_data().replace("Owner", "Other")}
    assert (await client.get("/api/accounts", headers=tampered)).status == 401
    expired = {INIT_DATA_HEADER: init_data(auth_date=int(time.time()) - 2 * 86400)}
    assert (await client.get("/api/accounts", headers=expired)).status == 401


async def test_api_refuses_non_admin(client):
    response = await client.get("/api/accounts", headers=auth(STRANGER))
    assert response.status == 403
    body = await response.json()
    assert body["error"] == "forbidden" and body["message"]
    assert (await client.post("/api/accounts", json=CARD, headers=auth(STRANGER))).status == 403
    assert await db.list_accounts(STRANGER) == []


async def test_static_page_and_fonts_need_no_auth(client):
    response = await client.get("/")
    assert response.status == 200 and "telegram-web-app.js" in await response.text()
    assert (await client.get("/static/app.js")).status == 200
    assert (await client.get("/fonts/JetBrainsMono-Bold.woff2")).status == 200


async def test_me_returns_language_and_texts(client):
    await db.set_language(ADMIN, "owner", "ru")
    body = await (await client.get("/api/me", headers=auth())).json()
    assert body["lang"] == "ru" and body["texts"]["add_card"] == "ДОБАВИТЬ КАРТУ"


def test_webapp_texts_are_complete():
    for key, variants in WEBAPP_TEXTS.items():
        assert set(variants) == set(LANGUAGES), key


async def test_create_list_and_totals(client):
    await db.set_language(ADMIN, "owner", "uz")
    response = await client.post("/api/accounts", json=CARD, headers=auth())
    assert response.status == 201
    card = (await response.json())["account"]
    assert card["card_type"] == "uzcard" and card["last4"] == "4417" and card["kind"] == "debit"

    credit = dict(CARD, card_type="visa", name="Visa", last4="9012", is_credit=True,
                  balance_minor=30_000_000, credit_limit_minor=100_000_000)
    assert (await client.post("/api/accounts", json=credit, headers=auth())).status == 201
    usd = dict(CARD, card_type="mastercard", name="USD card", last4="5555", currency="USD", balance_minor=12_345)
    assert (await client.post("/api/accounts", json=usd, headers=auth())).status == 201

    body = await (await client.get("/api/accounts", headers=auth())).json()
    assert body["count"] == 4  # the seeded cash account too
    by_name = {a["name"]: a for a in body["accounts"]}
    visa = by_name["Visa"]
    assert visa["is_credit"] and visa["kind"] == "credit"
    assert visa["debt_minor"] == 30_000_000 and visa["balance_minor"] == -30_000_000
    assert visa["credit_limit_minor"] == 100_000_000 and visa["available_minor"] == 70_000_000
    cash = next(a for a in body["accounts"] if a["kind"] == "cash")
    assert cash["card_type"] == "cash"  # accounts made in the chat have no card_type saved
    assert body["totals"] == {"UZS": 125_000_000 - 30_000_000, "USD": 12_345}


@pytest.mark.parametrize("change, code", [
    ({"name": "  "}, "name"),
    ({"name": "x" * 41}, "name"),
    ({"last4": ""}, "last4"),
    ({"last4": "12a4"}, "last4"),
    ({"last4": "12345"}, "last4"),
    ({"balance_minor": -5}, "amount"),
    ({"balance_minor": "100"}, "amount"),
    ({"card_type": "amex"}, "invalid"),
    ({"currency": "EUR"}, "invalid"),
])
async def test_create_validation(client, change, code):
    response = await client.post("/api/accounts", json=dict(CARD, **change), headers=auth())
    assert response.status == 400 and (await response.json())["error"] == code


async def test_cash_needs_no_last4_and_cannot_be_credit(client):
    body = dict(CARD, card_type="cash", name="Wallet", last4="", is_credit=True, credit_limit_minor=5)
    account = (await (await client.post("/api/accounts", json=body, headers=auth())).json())["account"]
    assert account["kind"] == "cash" and account["last4"] is None and account["credit_limit_minor"] == 0


async def test_duplicate_last4_is_refused(client):
    assert (await client.post("/api/accounts", json=CARD, headers=auth())).status == 201
    response = await client.post("/api/accounts", json=dict(CARD, name="Other"), headers=auth())
    assert response.status == 409 and (await response.json())["error"] == "last4_taken"


async def test_account_details_month_totals_and_recent(client):
    await db.set_language(ADMIN, "owner", "en")
    card = (await (await client.post("/api/accounts", json=CARD, headers=auth())).json())["account"]
    await db.record_operation(ADMIN, "expense", "UZS", [db.Leg(card["id"], 2_500_000)], "Transport", "Taxi")
    await db.record_operation(ADMIN, "income", "UZS", [db.Leg(card["id"], 10_000_000)], "Salary")
    for _ in range(11):
        await db.record_operation(ADMIN, "expense", "UZS", [db.Leg(card["id"], 100_00)], "Food")

    body = await (await client.get(f"/api/accounts/{card['id']}", headers=auth())).json()
    assert body["account"]["balance_minor"] == 125_000_000 - 2_500_000 + 10_000_000 - 11 * 100_00
    assert body["month"]["expense_minor"] == 2_500_000 + 11 * 100_00
    assert body["month"]["income_minor"] == 10_000_000
    assert len(body["operations"]) == 10 and body["has_operations"] is True
    assert body["operations"][0]["kind"] == "expense" and body["operations"][0]["direction"] == "out"


async def test_other_users_account_is_not_found(client):
    other = await db.create_account(STRANGER, "Theirs", "debit", "UZS")
    assert (await client.get(f"/api/accounts/{other.id}", headers=auth())).status == 404
    assert (await client.put(f"/api/accounts/{other.id}", json=CARD, headers=auth())).status == 404
    assert (await client.delete(f"/api/accounts/{other.id}", headers=auth())).status == 404
    assert (await client.get("/api/accounts/abc", headers=auth())).status == 404


async def test_update_sets_current_balance_through_opening(client):
    card = (await (await client.post("/api/accounts", json=CARD, headers=auth())).json())["account"]
    await db.record_operation(ADMIN, "expense", "UZS", [db.Leg(card["id"], 5_000_000)], "Food")
    update = dict(CARD, name="Kapital", last4="1111", balance_minor=200_000_000)
    response = await client.put(f"/api/accounts/{card['id']}", json=update, headers=auth())
    assert response.status == 200
    saved = await db.get_account(ADMIN, card["id"])
    assert saved.name == "Kapital" and saved.last4 == "1111" and saved.balance_minor == 200_000_000
    assert saved.opening_balance_minor == 205_000_000  # balance = opening + operations

    # turn it into a credit card: the entered value is the debt
    credit = dict(update, is_credit=True, balance_minor=1_000_000, credit_limit_minor=50_000_000)
    assert (await client.put(f"/api/accounts/{card['id']}", json=credit, headers=auth())).status == 200
    saved = await db.get_account(ADMIN, card["id"])
    assert saved.kind == "credit" and saved.balance_minor == -1_000_000 and saved.credit_limit_minor == 50_000_000


async def test_currency_of_account_with_operations_is_locked(client):
    card = (await (await client.post("/api/accounts", json=CARD, headers=auth())).json())["account"]
    fresh = dict(CARD, last4="2222")
    other = (await (await client.post("/api/accounts", json=fresh, headers=auth())).json())["account"]
    await db.record_operation(ADMIN, "expense", "UZS", [db.Leg(card["id"], 1_000)], "Food")
    response = await client.put(f"/api/accounts/{card['id']}", json=dict(CARD, currency="USD"), headers=auth())
    assert response.status == 409 and (await response.json())["error"] == "currency_locked"
    # without operations the currency can change
    assert (await client.put(f"/api/accounts/{other['id']}", json=dict(fresh, currency="USD"),
                             headers=auth())).status == 200


async def test_delete_without_operations_removes_the_account(client):
    card = (await (await client.post("/api/accounts", json=CARD, headers=auth())).json())["account"]
    body = await (await client.delete(f"/api/accounts/{card['id']}", headers=auth())).json()
    assert body["result"] == "deleted"
    assert await db.get_account(ADMIN, card["id"]) is None


async def test_delete_with_operations_archives_the_account(client):
    card = (await (await client.post("/api/accounts", json=CARD, headers=auth())).json())["account"]
    await db.record_operation(ADMIN, "expense", "UZS", [db.Leg(card["id"], 1_000)], "Food")
    body = await (await client.delete(f"/api/accounts/{card['id']}", headers=auth())).json()
    assert body["result"] == "archived"
    names = [a["name"] for a in (await (await client.get("/api/accounts", headers=auth())).json())["accounts"]]
    assert "Kapitalbank" not in names
    assert len((await db.search_transactions(ADMIN)).rows) == 1  # history is kept
    # its digits are free again for a new card
    assert (await client.post("/api/accounts", json=CARD, headers=auth())).status == 201


# ---- SMS matching by the saved last4 ----

def test_match_account_prefers_saved_last4():
    ctx = UserContext([AccountRef(1, "Naqd pul", "cash", "UZS"),
                       AccountRef(2, "Kapitalbank", "debit", "UZS", "4417"),
                       AccountRef(3, "Old 4417", "debit", "UZS")], {})
    assert match_account(ctx, card_last4="*4417").id == 2
    # an account without saved digits still matches by the digits in its name
    ctx = UserContext([AccountRef(3, "UOB 9012", "debit", "UZS"),
                       AccountRef(4, "Hamkor", "debit", "UZS", "1111")], {})
    assert match_account(ctx, card_last4="8600 **** **** 9012").id == 3
    assert match_account(ctx, card_last4="5555") is None


async def test_load_context_carries_last4():
    await db.set_language(ADMIN, "owner", "en")
    account = await db.create_account(ADMIN, "Kapitalbank", "debit", "UZS", card_type="humo", last4="4417")
    ctx = await load_context(ADMIN)
    assert match_account(ctx, card_last4="*4417").id == account.id


# ---- Bot button ----

def test_accounts_keyboard_has_mini_app_button_only_with_https_url(monkeypatch):
    from data import config
    from keyboards.inline.accounts import account_list

    monkeypatch.setattr(config, "WEBAPP_ENABLED", False)
    assert all(b.web_app is None for row in account_list([], "uz").inline_keyboard for b in row)

    monkeypatch.setattr(config, "WEBAPP_URL", "https://finance.example.com")
    monkeypatch.setattr(config, "WEBAPP_ENABLED", True)
    first = account_list([], "uz").inline_keyboard[0][0]
    assert first.web_app.url == "https://finance.example.com" and first.text == "💳 Kartalarim (Mini App)"
