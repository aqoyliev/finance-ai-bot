"""Mini App API of the screens Home, NewOp, History, Report, Settings and Budgets (aiohttp test client)."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from aiohttp.test_utils import TestClient, TestServer

from utils import rates
from utils.db_api import finance as db
from utils.i18n import LANGUAGES, WEBAPP_TEXTS
from utils.miniapp import screens
from utils.miniapp.api import create_app

from test_miniapp import ADMIN, STRANGER, TOKEN, auth, init_data
from test_services import USER, balance, setup_user

assert USER == ADMIN


@pytest.fixture
async def alerts():
    return []


@pytest.fixture
async def client(alerts):
    async def sender(user_id, lang, *saved):
        alerts.append((user_id, lang, saved))

    async with TestClient(TestServer(create_app(TOKEN, alert_sender=sender))) as test_client:
        yield test_client


def official(monkeypatch, rate="12500"):
    async def fetch():
        return rates.OfficialUsd(Decimal(rate), date(2026, 11, 5))

    monkeypatch.setattr(rates, "fetch_cbu", fetch)


async def call(client, method, path, status=200, **kwargs):
    res = await client.request(method, path, headers=auth(), **kwargs)
    assert res.status == status, (method, path, res.status, await res.text())
    return await res.json()


EXPENSE = {"kind": "expense", "currency": "UZS", "category": "Transport", "subcategory": "Taxi"}


# ---- Auth on every endpoint ----

ENDPOINTS = [("GET", "/api/home"), ("GET", "/api/form"), ("GET", "/api/operations"), ("POST", "/api/operations"),
             ("GET", "/api/operations/1"), ("PUT", "/api/operations/1"), ("DELETE", "/api/operations/1"),
             ("GET", "/api/report"), ("GET", "/api/report/subcategories"), ("GET", "/api/advice"),
             ("GET", "/api/settings"), ("PUT", "/api/settings"), ("GET", "/api/budgets"), ("PUT", "/api/budgets"),
             ("DELETE", "/api/budgets")]


@pytest.mark.parametrize("method, path", ENDPOINTS)
async def test_every_endpoint_needs_valid_init_data_of_an_admin(client, method, path):
    await setup_user()
    assert (await client.request(method, path)).status == 401
    bad = init_data().replace("Owner", "Admin")
    assert (await client.request(method, path, headers={"X-Telegram-Init-Data": bad})).status == 401
    res = await client.request(method, path, headers=auth(STRANGER), json={})
    assert res.status == 403 and (await res.json())["error"] == "forbidden"


async def test_admin_without_a_user_row_is_told_to_start(client):
    res = await client.get("/api/home", headers=auth())
    assert res.status == 409 and (await res.json())["error"] == "start"


async def test_texts_exist_in_every_language():
    for key, variants in WEBAPP_TEXTS.items():
        assert set(variants) == set(LANGUAGES) and all(variants.values()), key
    for lang in LANGUAGES:
        assert len(WEBAPP_TEXTS["months"][lang].split(",")) == 12


# ---- Operations: create, edit, delete ----

async def test_create_expense_reuses_the_service_and_sends_alerts(client, alerts):
    cash, card, credit, usd = await setup_user()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    data = await call(client, "POST", "/api/operations", 201,
                      json={**EXPENSE, "amount_minor": 90_000, "account_id": card.id, "note": "  to  the airport "})
    op = data["operation"]
    assert op["kind"] == "expense" and op["category"] == "Transport" and op["subcategory"] == "Taxi"
    assert op["note"] == "to the airport" and op["account"]["id"] == card.id and data["over_limit"] == []
    assert await balance(card.id) == 500_000 - 90_000
    [(user_id, lang, saved)] = alerts
    assert user_id == USER and lang == "en" and saved[0].transactions[0].category == "Transport"
    # the real alert service: 90% of the budget -> the 80% alert, exactly as after a save in the bot
    assert [(a.kind, a.threshold) for a in await db.check_alerts(USER, ["Transport"])] == [("budget", 80)]


async def test_income_and_a_past_date(client):
    cash, card, credit, usd = await setup_user()
    moment = (db.now() - timedelta(days=3)).replace(second=0, microsecond=0)
    data = await call(client, "POST", "/api/operations", 201, json={
        "kind": "income", "currency": "USD", "category": "Salary", "amount_minor": 12_345, "account_id": usd.id,
        "occurred_at": moment.strftime("%Y-%m-%dT%H:%M")})
    assert data["operation"]["occurred_at"] == moment.strftime("%Y-%m-%dT%H:%M")
    assert await balance(usd.id) == 10_000 + 12_345


async def test_credit_card_expense_reports_the_limit(client, alerts):
    cash, card, credit, usd = await setup_user()
    data = await call(client, "POST", "/api/operations", 201,
                      json={**EXPENSE, "amount_minor": 900_000, "account_id": credit.id})
    assert data["over_limit"] == ["Visa"]  # debt 200 000 + 900 000 > limit 1 000 000
    assert await balance(credit.id) == -1_100_000
    assert alerts and alerts[0][2][0].accounts[0].id == credit.id


async def test_transfer_create_edit_and_delete(client, alerts):
    cash, card, credit, usd = await setup_user()
    data = await call(client, "POST", "/api/operations", 201, json={
        "kind": "transfer", "amount_minor": 150_000, "from_account_id": card.id, "to_account_id": credit.id})
    op = data["operation"]
    assert op["kind"] == "transfer" and op["account"]["id"] == card.id and op["to_account"]["id"] == credit.id
    assert await balance(card.id) == 350_000 and await balance(credit.id) == -50_000  # repays the debt
    assert alerts  # a transfer touching a credit card is checked, like in the bot

    body = {"amount_minor": 100_000, "from_account_id": card.id, "to_account_id": credit.id, "note": "repay"}
    data = await call(client, "PUT", f"/api/operations/{op['id']}", json=body)
    assert data["operation"]["amount_minor"] == 100_000 and data["operation"]["note"] == "repay"
    assert await balance(card.id) == 400_000 and await balance(credit.id) == -100_000
    # the accounts of a transfer stay
    await call(client, "PUT", f"/api/operations/{op['id']}", 400, json={**body, "to_account_id": cash.id})

    # opening the incoming leg gives the same transfer
    incoming = [r for r in (await db.search_transactions(USER, kind="transfer")).rows]
    assert len(incoming) == 1
    await call(client, "DELETE", f"/api/operations/{op['id']}")
    assert await balance(card.id) == 500_000 and await balance(credit.id) == -200_000
    assert (await db.search_transactions(USER, kind="transfer")).count == 0


async def test_edit_amount_category_account_note_and_date(client, alerts):
    cash, card, credit, usd = await setup_user()
    op = (await call(client, "POST", "/api/operations", 201,
                     json={**EXPENSE, "amount_minor": 50_000, "account_id": cash.id}))["operation"]
    alerts.clear()
    moment = (db.now() - timedelta(days=1)).replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
    data = await call(client, "PUT", f"/api/operations/{op['id']}", json={
        "currency": "UZS", "category": "Health", "subcategory": None, "amount_minor": 70_000,
        "account_id": credit.id, "note": "pharmacy", "occurred_at": moment})
    new = data["operation"]
    assert (new["amount_minor"], new["category"], new["subcategory"], new["account"]["id"], new["note"],
            new["occurred_at"]) == (70_000, "Health", None, credit.id, "pharmacy", moment)
    assert await balance(cash.id) == 100_000 and await balance(credit.id) == -270_000
    assert len(alerts) == 1 and len(alerts[0][2]) == 3  # amount, category and account changes, sent once
    # unchanged fields change nothing and send nothing
    alerts.clear()
    await call(client, "PUT", f"/api/operations/{op['id']}", json={**{k: new[k] for k in (
        "currency", "category", "subcategory", "amount_minor", "note", "occurred_at")}, "account_id": credit.id})
    assert alerts == []
    # kind and currency cannot change; an account of another currency is refused
    await call(client, "PUT", f"/api/operations/{op['id']}", 400, json={
        "currency": "USD", "category": "Health", "amount_minor": 1, "account_id": usd.id})
    res = await call(client, "PUT", f"/api/operations/{op['id']}", 409, json={
        "currency": "UZS", "category": "Health", "amount_minor": 1, "account_id": usd.id})
    assert res["error"] == "currency_mismatch"


async def test_get_and_delete_operation(client):
    cash, card, credit, usd = await setup_user()
    op = (await call(client, "POST", "/api/operations", 201,
                     json={**EXPENSE, "amount_minor": 50_000, "account_id": cash.id}))["operation"]
    data = await call(client, "GET", f"/api/operations/{op['id']}")
    assert data["operation"]["account"]["name"] == "Wallet"
    await call(client, "DELETE", f"/api/operations/{op['id']}")
    assert await balance(cash.id) == 100_000
    await call(client, "GET", f"/api/operations/{op['id']}", 404)
    await call(client, "DELETE", f"/api/operations/{op['id']}", 404)
    await call(client, "GET", "/api/operations/abc", 404)


@pytest.mark.parametrize("patch, code", [
    ({"amount_minor": 0}, "amount"), ({"amount_minor": -5}, "amount"), ({"amount_minor": "100"}, "amount"),
    ({"amount_minor": True}, "amount"), ({"amount_minor": 10 ** 15}, "amount"),
    ({"kind": "loan"}, "invalid"), ({"currency": "EUR"}, "invalid"),
    ({"category": "Nope"}, "category"), ({"category": None}, "category"), ({"subcategory": "Doctor"}, "category"),
    ({"account_id": "1"}, "account"), ({"account_id": None}, "account"),
    ({"note": "x" * 201}, "note"), ({"note": 5}, "note"),
    ({"occurred_at": "2099-01-01T10:00"}, "date"), ({"occurred_at": "yesterday"}, "date"),
    ({"occurred_at": "1999-12-31T10:00"}, "date"),
])
async def test_operation_input_is_validated(client, patch, code):
    cash, *_ = await setup_user()
    res = await call(client, "POST", "/api/operations", 400,
                     json={**EXPENSE, "amount_minor": 1_000, "account_id": cash.id, **patch})
    assert res["error"] == code
    assert await balance(cash.id) == 100_000


async def test_operations_touch_only_own_data(client):
    cash, card, credit, usd = await setup_user()
    await db.set_language(STRANGER, "other", "en")
    foreign = (await db.list_accounts(STRANGER))[0]
    res = await call(client, "POST", "/api/operations", 404,
                     json={**EXPENSE, "amount_minor": 1_000, "account_id": foreign.id})
    assert res["error"] == "not_found"
    saved = await db.record_operation(STRANGER, "expense", "UZS", [db.Leg(foreign.id, 500)], "Transport")
    tx_id = saved.transactions[0].id
    for method in ("GET", "DELETE"):
        await call(client, method, f"/api/operations/{tx_id}", 404)
    await call(client, "PUT", f"/api/operations/{tx_id}", 404, json={**EXPENSE, "amount_minor": 1, "account_id": cash.id})
    assert (await db.search_transactions(STRANGER)).count == 1
    await call(client, "POST", "/api/operations", 400, json={
        "kind": "transfer", "amount_minor": 1, "from_account_id": cash.id, "to_account_id": cash.id})
    await call(client, "POST", "/api/operations", 409, json={
        "kind": "transfer", "amount_minor": 1, "from_account_id": cash.id, "to_account_id": usd.id})


async def test_form_lists_categories_with_subcategories_and_accounts(client):
    await setup_user()
    data = await call(client, "GET", "/api/form")
    transport = next(c for c in data["categories"]["expense"] if c["name"] == "Transport")
    assert "Taxi" in transport["subcategories"]
    assert "Salary" in [c["name"] for c in data["categories"]["income"]]
    assert [a["name"] for a in data["accounts"]] == ["Cash", "Wallet", "Card", "Visa", "Dollars"]


# ---- History ----

async def test_history_search_filter_and_paging(client):
    cash, card, credit, usd = await setup_user()
    now = db.now()
    for i in range(7):
        await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id if i % 2 else card.id, 1_000 + i)],
                                  "Transport", "Taxi", note="taxi home" if i == 3 else None,
                                  occurred_at=now - timedelta(hours=i))
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 5_000)], "Salary",
                              occurred_at=now - timedelta(minutes=30))
    await db.record_transfer(USER, card.id, cash.id, 2_000, occurred_at=now - timedelta(minutes=10))

    page = await call(client, "GET", "/api/operations?limit=4")
    assert page["total"] == 9 and len(page["operations"]) == 4 and page["next_offset"] == 4
    transfer = next(op for op in page["operations"] if op["kind"] == "transfer")
    assert transfer["account"] == "Card" and transfer["to_account"] == "Wallet"
    rest = await call(client, "GET", "/api/operations?limit=4&offset=8")
    assert len(rest["operations"]) == 1 and rest["next_offset"] is None
    moments = [op["occurred_at"] for op in page["operations"]]
    assert moments == sorted(moments, reverse=True)  # newest first

    assert (await call(client, "GET", "/api/operations?kind=income"))["total"] == 1
    assert (await call(client, "GET", "/api/operations?kind=expense"))["total"] == 7
    by_account = await call(client, "GET", f"/api/operations?account_id={cash.id}")
    assert by_account["total"] == 4  # 3 expenses + the transfer to it
    found = await call(client, "GET", "/api/operations?q=HOME")
    assert found["total"] == 1 and found["operations"][0]["note"] == "taxi home"
    for bad in ("kind=loan", "offset=-1", "limit=0", "limit=1000", "account_id=x", "q=" + "x" * 101):
        await call(client, "GET", f"/api/operations?{bad}", 400)


# ---- Home ----

async def test_home_totals_rate_limit_and_recent(client, monkeypatch):
    official(monkeypatch)
    cash, card, credit, usd = await setup_user()
    data = await call(client, "GET", "/api/home")
    assert data["rate"] == {"rate": "12500", "source": "cbu", "date": "2026-11-05"}
    # 1 000 + 5 000 - 2 000 (credit debt) so'm + $100.00 at 12 500 = 1 250 000 so'm (all in minor units)
    assert data["balance"] == {"uzs_minor": 400_000 + 125_000_000, "usd_minor": 0, "converted": True}
    assert data["limit"] is None and data["recent"] == []

    await db.set_budget(USER, "Transport", "UZS", 1_000_000)
    await db.set_budget(USER, "Health", "USD", 10_000)  # $100 -> 1 250 000 so'm
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 50_000)], "Transport")
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 1_000)], "Health")
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 300_000)], "Salary")
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 7_000)], "Other")
    data = await call(client, "GET", "/api/home")
    assert data["expense"] == {"uzs_minor": 57_000 + 12_500_000, "usd_minor": 0, "converted": True}
    assert data["income"]["uzs_minor"] == 300_000
    assert data["limit"] == {"limit_minor": 126_000_000, "spent_minor": 12_550_000, "count": 2, "percent": 9,
                             "left_minor": 113_450_000}
    assert len(data["recent"]) == 3 and data["recent"][0]["category"] == "Other"
    assert 1 <= data["month"] <= 12 and len(data["accounts"]) == 5


async def test_home_without_a_rate_keeps_usd_apart(client):
    cash, card, credit, usd = await setup_user()
    await db.set_budget(USER, "Health", "USD", 10_000)
    data = await call(client, "GET", "/api/home")
    assert data["rate"] is None
    assert data["balance"] == {"uzs_minor": 400_000, "usd_minor": 10_000, "converted": False}
    assert data["limit"] is None  # a USD budget cannot be added up without a rate


def test_headline_month():
    assert screens.headline_month(date(2026, 11, 1)) == 11
    assert screens.headline_month(date(2026, 10, 25)) == 11
    assert screens.headline_month(date(2026, 12, 20)) == 1


# ---- Report ----

def test_report_windows():
    wednesday = date(2026, 11, 4)
    assert screens.report_window("week", wednesday, 1) == (
        date(2026, 11, 2), date(2026, 11, 9), date(2026, 10, 26), date(2026, 10, 29))
    assert screens.report_window("month", wednesday, 5) == (
        date(2026, 10, 5), date(2026, 11, 5), date(2026, 9, 5), date(2026, 10, 5))
    assert screens.report_window("year", date(2026, 2, 1), 1) == (
        date(2026, 1, 1), date(2027, 1, 1), date(2025, 1, 1), date(2025, 2, 2))  # Jan 1 - Feb 1 of both


@pytest.mark.parametrize("period", ["week", "month", "year"])
async def test_report_periods(client, period):
    cash, card, credit, usd = await setup_user()
    now = db.now()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 30_000)], "Transport", "Taxi", occurred_at=now)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 10_000)], "Transport", "Fuel", occurred_at=now)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(card.id, 50_000)], "Health", occurred_at=now)
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 200_000)], "Salary", occurred_at=now)
    await db.record_transfer(USER, card.id, cash.id, 99_000, occurred_at=now)  # never counted
    data = await call(client, "GET", f"/api/report?period={period}")
    [sec] = data["sections"]
    assert data["period"] == period and data["last_day"] == now.date().isoformat()
    assert (sec["currency"], sec["expense_minor"], sec["income_minor"], sec["balance_minor"]) == (
        "UZS", 90_000, 200_000, 110_000)
    assert [(c["name"], c["amount_minor"], c["share"]) for c in sec["categories"]] == [
        ("Health", 50_000, 56), ("Transport", 40_000, 44)]
    subs = await call(client, "GET", f"/api/report/subcategories?period={period}&category=Transport&currency=UZS")
    assert subs["subcategories"] == [{"name": "Taxi", "amount_minor": 30_000}, {"name": "Fuel", "amount_minor": 10_000}]


async def test_report_change_against_the_same_days_of_last_month(client):
    cash, *_ = await setup_user()
    user = await db.get_user(USER)
    start, end, cmp_start, cmp_end = screens.report_window("month", db.now().date(), user.salary_day)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 100_000)], "Transport",
                              occurred_at=db.now())
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 80_000)], "Transport",
                              occurred_at=datetime.combine(cmp_start, time(10)))
    [sec] = (await call(client, "GET", "/api/report?period=month"))["sections"]
    assert sec["prev_expense_minor"] == 80_000 and sec["change_percent"] == 25


async def test_report_currencies_combined_with_a_rate_and_apart_without(client, monkeypatch):
    cash, card, credit, usd = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 50_000)], "Transport")
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 1_000)], "Transport", "Taxi")
    apart = (await call(client, "GET", "/api/report"))["sections"]
    assert [(s["currency"], s["expense_minor"], s["converted"]) for s in apart] == [
        ("UZS", 50_000, False), ("USD", 1_000, False)]
    await db.set_usd_rate(USER, Decimal("12500"))
    [merged] = (await call(client, "GET", "/api/report"))["sections"]
    assert merged["converted"] and merged["expense_minor"] == 50_000 + 12_500_000
    subs = await call(client, "GET", "/api/report/subcategories?period=month&category=Transport&converted=1")
    assert {s["name"]: s["amount_minor"] for s in subs["subcategories"]} == {"Taxi": 12_500_000, None: 50_000}


async def test_report_input_is_validated(client):
    await setup_user()
    await call(client, "GET", "/api/report?period=decade", 400)
    await call(client, "GET", "/api/report/subcategories?period=month", 400)
    await call(client, "GET", "/api/report/subcategories?period=month&category=x&currency=EUR", 400)


async def test_advice_is_off_without_ai_and_cached_with_it(client, monkeypatch):
    from types import SimpleNamespace

    from utils.ai import assistant
    from utils.ai import core as ai

    await setup_user()
    monkeypatch.setattr(ai, "get_client", lambda: SimpleNamespace(configured=False))
    assert await call(client, "GET", "/api/advice?period=month") == {"text": None, "reason": "not_configured"}

    calls = []

    async def fake_advice(user_id, kind, lang, *, client=None, today=None):
        calls.append(kind)
        return assistant.Advice("Spend less on taxi.", date.today(), date.today())

    monkeypatch.setattr(ai, "get_client", lambda: SimpleNamespace(configured=True))
    monkeypatch.setattr(assistant, "advice", fake_advice)
    screens._advice_cache.clear()
    assert (await call(client, "GET", "/api/advice?period=month"))["text"] == "Spend less on taxi."
    await call(client, "GET", "/api/advice?period=year")  # the same "now" advice: reused
    await call(client, "GET", "/api/advice?period=week")
    assert calls == ["now", "weekly"]

    async def failing(*args, **kwargs):
        raise ai.AIError("timeout")

    monkeypatch.setattr(assistant, "advice", failing)
    screens._advice_cache.clear()
    assert await call(client, "GET", "/api/advice?period=month") == {"text": None, "reason": "error"}


# ---- Settings ----

async def test_settings_salary_day_advice_and_language(client):
    await setup_user()
    data = await call(client, "GET", "/api/settings")
    assert (data["salary_day"], data["advice_weekly"], data["advice_monthly"], data["lang"]) == (1, True, True, "en")
    assert data["accounts_count"] == 5 and data["budgets_count"] == 0
    data = await call(client, "PUT", "/api/settings", json={"salary_day": 28, "advice_weekly": False,
                                                             "advice_monthly": True})
    assert (data["salary_day"], data["advice_weekly"], data["advice_monthly"]) == (28, False, True)
    user = await db.get_user(USER)
    assert user.salary_day == 28 and not user.advice_weekly and user.advice_monthly

    data = await call(client, "PUT", "/api/settings", json={"lang": "ru"})
    assert data["lang"] == "ru" and await db.get_language(USER) == "ru"
    me = await call(client, "GET", "/api/me")
    assert me["lang"] == "ru" and me["texts"]["tab_home"] == "ГЛАВНАЯ"
    assert len(await db.list_accounts(USER)) == 5  # no re-seeding


async def test_settings_rate_manual_and_auto(client, monkeypatch):
    official(monkeypatch, "12850.37")
    await setup_user()
    data = await call(client, "GET", "/api/settings")
    assert data["rate"] == {"rate": "12850.37", "source": "cbu", "date": "2026-11-05"} and not data["rate_manual"]
    data = await call(client, "PUT", "/api/settings", json={"rate_mode": "manual", "rate": "12 650,5"})
    assert data["rate_manual"] and data["rate"]["rate"] == "12650.5" and data["rate"]["source"] == "manual"
    assert await db.get_usd_rate(USER) == Decimal("12650.5")
    data = await call(client, "PUT", "/api/settings", json={"rate_mode": "auto"})
    assert not data["rate_manual"] and data["rate"]["source"] == "cbu"


@pytest.mark.parametrize("body, code", [
    ({}, "invalid"), ({"salary_day": 0}, "salary_day"), ({"salary_day": 29}, "salary_day"),
    ({"salary_day": "5"}, "salary_day"), ({"salary_day": True}, "salary_day"),
    ({"rate_mode": "manual"}, "rate"), ({"rate_mode": "manual", "rate": "abc"}, "rate"),
    ({"rate_mode": "manual", "rate": "0"}, "rate"), ({"rate_mode": "manual", "rate": "-5"}, "rate"),
    ({"rate_mode": "manual", "rate": "NaN"}, "rate"), ({"rate_mode": "manual", "rate": "1e9"}, "rate"),
    ({"rate_mode": "sometimes"}, "invalid"), ({"advice_weekly": "no"}, "invalid"), ({"lang": "de"}, "invalid"),
    ({"salary_day": 10, "lang": "de"}, "invalid"),
])
async def test_settings_input_is_validated(client, body, code):
    await setup_user()
    res = await call(client, "PUT", "/api/settings", 400, json=body)
    assert res["error"] == code
    user = await db.get_user(USER)
    assert user.salary_day == 1 and user.language == "en"  # nothing saved, not even the valid part
    assert await db.get_usd_rate(USER) is None


# ---- Budgets ----

async def test_budgets_crud(client):
    cash, *_ = await setup_user()
    data = await call(client, "GET", "/api/budgets")
    assert data["budgets"] == [] and "Transport" in data["categories"] and "Salary" not in data["categories"]
    await call(client, "PUT", "/api/budgets", json={"category": "Transport", "currency": "UZS", "amount_minor": 200_000})
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 50_000)], "Transport")
    [budget] = (await call(client, "GET", "/api/budgets"))["budgets"]
    assert budget == {"category": "Transport", "currency": "UZS", "limit_minor": 200_000, "spent_minor": 50_000,
                      "percent": 25}
    await call(client, "PUT", "/api/budgets", json={"category": "Transport", "currency": "UZS", "amount_minor": 60_000})
    assert (await call(client, "GET", "/api/budgets"))["budgets"][0]["percent"] == 83
    assert (await call(client, "GET", "/api/settings"))["budgets_count"] == 1
    await call(client, "DELETE", "/api/budgets?category=Transport")
    assert (await call(client, "GET", "/api/budgets"))["budgets"] == []
    await call(client, "DELETE", "/api/budgets?category=Transport", 404)


@pytest.mark.parametrize("body, code", [
    ({"category": "Salary", "currency": "UZS", "amount_minor": 1}, "category"),  # an income category
    ({"category": "Nope", "currency": "UZS", "amount_minor": 1}, "category"),
    ({"category": "Transport", "currency": "EUR", "amount_minor": 1}, "invalid"),
    ({"category": "Transport", "currency": "UZS", "amount_minor": 0}, "amount"),
    ({"category": "Transport", "currency": "UZS", "amount_minor": "5"}, "amount"),
    ({"currency": "UZS", "amount_minor": 1}, "invalid"),
])
async def test_budget_input_is_validated(client, body, code):
    await setup_user()
    assert (await call(client, "PUT", "/api/budgets", 400, json=body))["error"] == code
    assert await db.list_budgets(USER) == {}
    await call(client, "DELETE", "/api/budgets", 400)


async def test_budgets_are_per_user(client):
    await setup_user()
    await db.set_language(STRANGER, "other", "en")
    await db.set_budget(STRANGER, "Transport", "UZS", 1_000)
    assert (await call(client, "GET", "/api/budgets"))["budgets"] == []
    await call(client, "DELETE", "/api/budgets?category=Transport", 404)
    assert "Transport" in await db.list_budgets(STRANGER)
