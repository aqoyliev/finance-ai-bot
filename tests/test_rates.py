"""Official USD rate (CBU): parsing, cache, failure fallback, manual override vs auto, /rate, migration 0006."""
import asyncio
import json
import logging
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from aiohttp import web
from aiohttp.test_utils import TestServer

from handlers.users import settings
from utils import rates
from utils.ai import assistant, tools
from utils.db_api import finance as db
from utils.db_api.base import alembic_config
from utils.i18n import LANGUAGES, t

from test_services import USER, setup_user

PAYLOAD = [{"id": 69, "Code": "840", "Ccy": "USD", "CcyNm_UZ": "AQSh dollari", "Nominal": "1",
            "Rate": "12850.37", "Diff": "-1.2", "Date": "05.11.2026"}]
REAL_FETCH = rates.fetch_cbu  # the autouse fixture replaces rates.fetch_cbu (no network in tests)
OFFICIAL = rates.OfficialUsd(Decimal("12850.37"), date(2026, 11, 5))


def mock_fetch(monkeypatch, *outcomes):
    """Replace the CBU fetch: each call returns/raises the next outcome (the last one repeats)."""
    calls = []

    async def fetch():
        calls.append(1)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(rates, "fetch_cbu", fetch)
    return calls


# ---- Parsing and fetching ----

def test_parse_cbu():
    assert rates.parse_cbu(PAYLOAD) == OFFICIAL
    other = [{"Ccy": "EUR", "Rate": "14000.00", "Date": "05.11.2026"}] + PAYLOAD
    assert rates.parse_cbu(other) == OFFICIAL
    assert rates.parse_cbu([{"Ccy": "USD", "Rate": "12850,5", "Date": "01.01.2027"}]).rate == Decimal("12850.5")


@pytest.mark.parametrize("payload", [
    None, {}, [], "oops", [{"Ccy": "EUR", "Rate": "1", "Date": "05.11.2026"}],
    [{"Ccy": "USD", "Rate": "abc", "Date": "05.11.2026"}],
    [{"Ccy": "USD", "Rate": "0", "Date": "05.11.2026"}],
    [{"Ccy": "USD", "Rate": "-5", "Date": "05.11.2026"}],
    [{"Ccy": "USD", "Rate": "NaN", "Date": "05.11.2026"}],
    [{"Ccy": "USD", "Rate": "12850", "Date": "2026-11-05"}],
    [{"Ccy": "USD", "Date": "05.11.2026"}],
])
def test_parse_cbu_rejects_bad_payloads(payload):
    with pytest.raises(rates.RateError):
        rates.parse_cbu(payload)


async def test_fetch_cbu_over_http_against_a_local_server(monkeypatch):
    async def ok(request):
        return web.Response(text=json.dumps(PAYLOAD), content_type="text/html")  # the content type may be odd

    async def broken(request):
        return web.Response(status=503)

    app = web.Application()
    app.router.add_get("/ok", ok)
    app.router.add_get("/down", broken)
    async with TestServer(app) as server:
        monkeypatch.setattr(rates, "CBU_URL", str(server.make_url("/ok")))
        assert await REAL_FETCH() == OFFICIAL
        monkeypatch.setattr(rates, "CBU_URL", str(server.make_url("/down")))
        with pytest.raises(rates.RateError):
            await REAL_FETCH()
    assert rates.CBU_URL.startswith("http")
    assert rates.TIMEOUT_SECONDS == 10 and rates.CACHE_TTL == timedelta(hours=6)


# ---- Cache, persistence and failure fallback ----

async def test_rate_is_cached_in_memory(monkeypatch):
    calls = mock_fetch(monkeypatch, OFFICIAL)
    assert await rates.get_official() == OFFICIAL
    assert await rates.get_official() == OFFICIAL
    assert len(calls) == 1


async def test_expired_cache_keeps_the_value_and_refresh_updates_it(monkeypatch):
    calls = mock_fetch(monkeypatch, OFFICIAL)
    await rates.get_official()
    rates._state.fetched_at -= rates.CACHE_TTL + timedelta(minutes=1)
    assert await rates.get_official() == OFFICIAL  # the stale value is served; the periodic task refreshes
    assert len(calls) == 1
    newer = rates.OfficialUsd(Decimal("12900"), date(2026, 11, 6))
    mock_fetch(monkeypatch, newer)
    assert await rates.refresh() == newer
    assert await rates.get_official() == newer


async def test_failure_keeps_last_value_and_logs_warning(monkeypatch, caplog):
    mock_fetch(monkeypatch, OFFICIAL)
    await rates.refresh()
    mock_fetch(monkeypatch, rates.RateError("HTTP 500"))
    with caplog.at_level(logging.WARNING, logger="utils.rates"):
        assert await rates.refresh() == OFFICIAL
    assert any("CBU" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)
    assert await rates.get_official() == OFFICIAL


async def test_last_good_value_survives_a_restart_and_an_outage(monkeypatch):
    mock_fetch(monkeypatch, OFFICIAL)
    await rates.refresh()
    rates.reset()  # "restart": memory is empty, the database row stays
    mock_fetch(monkeypatch, OSError("cbu.uz unreachable"))
    assert await rates.get_official() == OFFICIAL
    assert await rates.refresh() == OFFICIAL


async def test_no_rate_at_all_is_none_and_retries_are_throttled(monkeypatch):
    calls = mock_fetch(monkeypatch, OSError("down"))
    assert await rates.get_official() is None
    assert await rates.get_official() is None
    assert len(calls) == 1  # not hammering CBU on every request
    rates._state.last_attempt -= rates.RETRY_AFTER + timedelta(seconds=1)
    mock_fetch(monkeypatch, OFFICIAL)
    assert await rates.get_official() == OFFICIAL


async def test_updater_starts_and_stops(monkeypatch):
    calls = mock_fetch(monkeypatch, OFFICIAL)
    updater = rates.Updater()
    task = updater.start()
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0.01)
    assert len(calls) == 1
    await updater.stop()
    assert task.done()


# ---- Manual override vs the official rate ----

async def test_default_is_official_override_wins_and_auto_removes_it(monkeypatch):
    await setup_user()
    mock_fetch(monkeypatch, OFFICIAL)
    info = await db.get_usd_rate_info(USER)
    assert (info.rate, info.source, info.day) == (Decimal("12850.37"), "cbu", date(2026, 11, 5))
    assert await db.get_usd_rate(USER) == Decimal("12850.37")

    await db.set_usd_rate(USER, Decimal("12600"))
    info = await db.get_usd_rate_info(USER)
    assert (info.rate, info.source) == (Decimal("12600"), "manual")

    assert await db.clear_usd_rate(USER) is True
    assert await db.clear_usd_rate(USER) is False
    assert (await db.get_usd_rate_info(USER)).source == "cbu"


async def test_nothing_breaks_when_there_is_no_rate_at_all(monkeypatch):
    cash, card, credit, usd = await setup_user()
    mock_fetch(monkeypatch, OSError("down"))
    assert await db.get_usd_rate(USER) is None
    await db.set_budget(USER, "Transport", "UZS", 5_000_000)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 100_000)], "Transport", "Taxi")
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 1_000)], "Transport", "Taxi")
    report = await db.build_period_report(USER, 0)
    assert report.combined is None and len(report.currencies) == 2
    [usage] = await db.budget_usages(USER)
    assert usage.spent == 100_000  # USD spending is simply not converted
    await db.check_alerts(USER, ["Transport"], [])


async def test_budgets_and_report_convert_by_default(monkeypatch):
    cash, card, credit, usd = await setup_user()
    mock_fetch(monkeypatch, rates.OfficialUsd(Decimal("12500"), date(2026, 11, 5)))
    await db.set_budget(USER, "Transport", "UZS", 5_000_000_000)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 100_000)], "Transport", "Taxi")
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 1_000)], "Transport", "Taxi")
    [usage] = await db.budget_usages(USER)
    assert usage.spent == 100_000 + 12_500_000  # $10.00 at 12 500 (minor units)
    report = await db.build_period_report(USER, 0)
    assert report.combined.rate == Decimal("12500") and report.combined.expense == 100_000 + 12_500_000


# ---- /rate command ----

class Msg:
    def __init__(self, args=""):
        self._args, self.sent = args, []
        self.from_user = SimpleNamespace(id=USER)

    def get_args(self):
        return self._args

    async def answer(self, text, **kwargs):
        self.sent.append(text)


async def rate(args, lang="en"):
    msg = Msg(args)
    await settings.rate_command(msg, lang)
    [text] = msg.sent
    return text


async def test_rate_command_shows_official_then_manual(monkeypatch):
    await setup_user()
    mock_fetch(monkeypatch, OFFICIAL)
    assert "1 USD = 12850.37 UZS (Central Bank, 05.11.2026)" in await rate("")
    assert "Markaziy bank, 05.11.2026" in await rate("", "uz")
    assert "Центральный банк, 05.11.2026" in await rate("", "ru")

    assert "Rate saved: 1 USD = 12650 UZS" in await rate("1 USD 12650 UZS")
    assert "1 USD = 12650 UZS (manual)" in await rate("")
    assert "qo'lda" in await rate("", "uz") and "вручную" in await rate("", "ru")


@pytest.mark.parametrize("word", ["auto", "AUTO", "avto", "Avto", "авто", "Авто"])
async def test_rate_auto_removes_the_override(monkeypatch, word):
    await setup_user()
    mock_fetch(monkeypatch, OFFICIAL)
    await rate("1 USD 12650 UZS")
    assert "Central Bank rate is used again" in await rate(word)
    assert (await db.get_usd_rate_info(USER)).source == "cbu"
    assert "no own rate" in await rate(word)  # nothing left to remove


async def test_rate_command_set_variants_and_errors(monkeypatch):
    await setup_user()
    mock_fetch(monkeypatch, OFFICIAL)
    assert "12650.5" in await rate("1 usd 12650,5 uzs")
    assert await db.get_usd_rate(USER) == Decimal("12650.5")
    for bad in ("12650", "1 USD 12650", "1 EUR 12650 UZS", "5 USD 12650 UZS", "1 USD 12650 UZS extra", "auto now"):
        assert "Format: /rate 1 USD" in await rate(bad)
    for bad in ("1 USD abc UZS", "1 USD 0 UZS", "1 USD -5 UZS", "1 USD NaN UZS"):
        assert "positive number" in await rate(bad)
    assert await db.get_usd_rate(USER) == Decimal("12650.5")  # failed commands changed nothing


async def test_rate_command_when_cbu_is_unreachable(monkeypatch):
    await setup_user()
    mock_fetch(monkeypatch, OSError("down"))
    assert "could not be fetched" in await rate("")


def test_rate_texts_exist_in_all_languages_and_mention_auto():
    for lang in LANGUAGES:
        for key in ("cmd_rate", "rate_usage", "rate_current", "rate_unknown", "rate_auto", "rate_auto_none",
                    "rate_source_manual", "rate_hint", "help", "settings"):
            text = t(key, lang, rate="1", source="s", salary_day=1, date="d")
            assert text and "12700" not in text
        assert "/rate auto" in t("help", lang) and "/rate auto" in t("settings", lang, salary_day=1)


# ---- The AI gets the real rate ----

async def test_exchange_rate_tool_reports_source_and_date(monkeypatch):
    await setup_user()
    mock_fetch(monkeypatch, OFFICIAL)
    assert await tools.get_exchange_rate(USER) == {
        "usd_to_uzs": "12850.37", "source": "Central Bank of Uzbekistan official rate", "date": "2026-11-05"}
    await db.set_usd_rate(USER, Decimal("12600"))
    result = await tools.get_exchange_rate(USER)
    assert result["usd_to_uzs"] == "12600" and "manually" in result["source"]


async def test_context_line_carries_the_rate_and_prompts_forbid_guessing(monkeypatch):
    mock_fetch(monkeypatch, OFFICIAL)
    await setup_user()
    info = await db.get_usd_rate_info(USER)
    line = assistant.context_line(date(2026, 11, 5), 1, "uz", info)
    assert "1 USD = 12850.37 UZS (Central Bank of Uzbekistan, 05.11.2026)" in line
    assert "unknown (do not guess one)" in assistant.context_line(date(2026, 11, 5), 1, "uz")
    assert "never state or assume a USD/UZS rate from memory" in assistant.QA_SYSTEM
    assert "dollar kursi qancha?" in assistant.QA_SYSTEM
    assert "never state an exchange rate from memory" in assistant.ADVICE_SYSTEM


# ---- Migration 0006 ----

def test_migration_0006_creates_the_table_and_clears_manual_rates():
    from alembic import command

    path = Path(tempfile.mkdtemp(prefix="finance-bot-mig-")) / "m.db"
    engine = sa.create_engine("sqlite:///" + str(path).replace("\\", "/"))
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "0005")
        assert "official_rates" not in sa.inspect(conn).get_table_names()
        conn.execute(sa.text(
            "INSERT INTO users (id, username, salary_day, base_currency, is_seeded, created_at) "
            "VALUES (1, 'a', 1, 'UZS', 1, '2026-11-01 00:00:00'), (2, 'b', 1, 'UZS', 1, '2026-11-01 00:00:00')"))
        conn.execute(sa.text(
            "INSERT INTO exchange_rates (user_id, from_currency, to_currency, rate, updated_at) VALUES "
            "(1, 'USD', 'UZS', '99999', '2026-11-01 00:00:00'), (1, 'UZS', 'USD', '0.00001', '2026-11-01 00:00:00'), "
            "(2, 'USD', 'UZS', '15000', '2026-11-01 00:00:00')"))
        command.upgrade(alembic_config(conn), "head")
        assert conn.execute(sa.text("SELECT count(*) FROM exchange_rates")).scalar() == 0
        assert conn.execute(sa.text("SELECT count(*) FROM users")).scalar() == 2  # only the rates were cleared
        columns = {c["name"] for c in sa.inspect(conn).get_columns("official_rates")}
        assert columns == {"currency", "rate", "rate_date", "fetched_at"}
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == "0006"
        command.downgrade(alembic_config(conn), "0005")
        assert "official_rates" not in sa.inspect(conn).get_table_names()
    engine.dispose()
