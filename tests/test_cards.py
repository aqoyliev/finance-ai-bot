"""Receipt cards: view-model building (pure), loading from the DB, fallbacks and one real Chromium render."""
import struct
from datetime import date, datetime, timedelta

import pytest
from aiogram.utils.exceptions import TelegramAPIError

from utils import advice_scheduler as sched
from utils import cards
from utils.ai import assistant
from utils.db_api import finance as db
from utils.i18n import LANGUAGES

from test_services import USER, setup_user

NB = " "
MONDAY = date(2026, 11, 2)
WEEK_START = date(2026, 10, 26)


def summary(start, end, totals=None, categories=None):
    return db.RangeSummary(start, end, dict(totals or {}), dict(categories or {}))


def expense(day, amount, currency="UZS", category="Food", note=None, group=None, kind="cash"):
    return db.ExpenseRow(datetime.combine(day, datetime.min.time()), amount, currency, category, note,
                         group or f"g{day}{amount}{currency}{category}", kind)


def weekly_data(rows, previous_categories=None, budgets=(), kind="weekly", start=WEEK_START, end=MONDAY,
                compare=(date(2026, 10, 19), WEEK_START)):
    totals, categories = {}, {}
    for row in rows:
        totals[("expense", row.currency)] = totals.get(("expense", row.currency), 0) + row.amount_minor
        key = (row.currency, row.category)
        categories[key] = categories.get(key, 0) + row.amount_minor
    prev_categories = dict(previous_categories or {})
    prev_totals = {}
    for (currency, _), amount in prev_categories.items():
        prev_totals[("expense", currency)] = prev_totals.get(("expense", currency), 0) + amount
    return cards.CardData(kind, start, end, compare[0], compare[1], summary(start, end, totals, categories),
                          summary(*compare, prev_totals, prev_categories), list(rows), list(budgets))


# ---- Formatting ----

def test_money_and_grouping():
    assert cards.money(99_999_999_900, "UZS") == f"999{NB}999{NB}999"
    assert cards.money(124_050, "USD") == f"$1{NB}240.50"
    assert cards.money(-1_244_000_000, "UZS") == f"−12{NB}440{NB}000"
    assert cards.money(1_450_000_000, "UZS", sign=True) == f"+14{NB}500{NB}000"
    assert cards.money(150, "UZS") == "2"  # whole sum, rounded half up
    assert cards.unit_value(98_000_000, "UZS") == "980" and cards.unit_value(261_049_000, "UZS") == f"2{NB}610"
    assert cards.unit_value(64_050, "USD") == "641"


def test_change_badge_and_stamp():
    assert cards.change_badge(118, 100, "uz") == {"text": "▲ 18%", "tone": "up"}
    assert cards.change_badge(94, 100, "uz") == {"text": "▼ 6%", "tone": "dn"}
    assert cards.change_badge(5, 0, "ru") == {"text": "новое", "tone": "mute"}
    assert cards.change_badge(0, 0, "en") is None
    assert cards.stamp(3_860_000, 3_420_000, "uz") == {"main": "▲ 12,9%", "sub": "KOʻPROQ", "tone": "up"}
    assert cards.stamp(90, 100, "en") == {"main": "▼ 10.0%", "sub": "LESS", "tone": "dn"}
    assert cards.stamp(331, 100, "ru")["main"] == "▲ 231%"
    assert cards.stamp(100, 100, "ru")["tone"] == "ink"
    assert cards.stamp(100, 0, "uz") is None


def test_fold_categories_keeps_limit_and_merges_other():
    items = [(f"c{i}", 1000 - i * 10, 50) for i in range(10)] + [("Other", 5, 7)]
    folded = cards.fold_categories(items, 8, "Other")
    assert len(folded) == 8 and folded[-1][0] == "Other"
    assert [name for name, _, _ in folded[:7]] == [f"c{i}" for i in range(7)]
    assert folded[-1][1] == sum(1000 - i * 10 for i in range(7, 10)) + 5
    assert folded[-1][2] == 3 * 50 + 7
    assert sum(a for _, a, _ in folded) == sum(a for _, a, _ in items)
    few = [("a", 10, 0), ("b", 30, 0), ("zero", 0, 5)]
    assert cards.fold_categories(few, 8, "Other") == [("b", 30, 0), ("a", 10, 0)]
    one = cards.fold_categories([("a", 10, 0)], 1, "Other")
    assert one == [("a", 10, 0)]


def test_bar_heights_scale_to_the_biggest():
    bars = cards.bar_heights([420, 310, 980, 260, 540, 870, 480])
    assert [b["h"] for b in bars] == [56, 41, 130, 34, 72, 115, 64]  # the mockup's numbers
    assert [b["hi"] for b in bars] == [False, False, True, False, False, False, False]
    assert [b["hi"] for b in cards.bar_heights([5, 5])] == [True, False]  # one highlight only
    assert cards.bar_heights([0, 0]) == [{"h": 0, "hi": False}, {"h": 0, "hi": False}]


def test_ascii_and_share_bars():
    assert cards.ascii_bar(94, 100) == "[##########]"  # ceil(9.4)
    assert cards.ascii_bar(86, 100) == "[#########-]"
    assert cards.ascii_bar(90, 100) == "[#########-]"
    assert cards.ascii_bar(1, 100) == "[#---------]"
    assert cards.ascii_bar(0, 100) == "[----------]"
    assert cards.ascii_bar(1180, 1000) == "[##########]"  # capped
    assert cards.ascii_bar(5, 0) == "[----------]"
    assert cards.share_bar(4_120, 4_120) == "█" * 20
    assert cards.share_bar(1_860, 4_120) == "█" * 9 + "░" * 11
    assert cards.share_bar(780, 4_120) == "█" * 4 + "░" * 16
    assert cards.share_bar(1, 4_120) == "█" + "░" * 19  # any spending shows
    assert len(cards.share_bar(0, 0)) == 20


def test_names_plurals_and_uzbek_letters():
    long_name = "Uy-ro'zg'or va ta'mirlash ishlari " * 4 + "🍔"
    cleaned = cards.clean_name(long_name, lang="uz")
    assert len(cleaned) == cards.MAX_NAME and cleaned.endswith("…") and cleaned.startswith("UY-ROʻZGʻOR VA TAʼMIR")
    assert cards.clean_name("Транспорт 🚗") == "ТРАНСПОРТ"
    assert cards.clean_name(None) == "—"
    assert cards.plural("expenses", 1, "ru") == "1 трата" and cards.plural("expenses", 3, "ru") == "3 траты"
    assert cards.plural("expenses", 38, "ru") == "38 трат" and cards.plural("expenses", 11, "ru") == "11 трат"
    assert cards.plural("expenses", 38, "uz") == "38 ta xarajat" and cards.plural("days", 1, "en") == "1 day"


# ---- View-models ----

def test_weekly_view_model():
    rows = [expense(date(2026, 10, 26), 42_000_000), expense(date(2026, 10, 28), 64_000_000, note="Korzinka"),
            expense(date(2026, 10, 28), 34_000_000, category="Taxi", kind="credit"),
            expense(date(2026, 11, 1), 10_000_000, category="Taxi")]
    budget = db.BudgetUsage("Food", "UZS", 100_000_000, 106_000_000)
    data = weekly_data(rows, {("UZS", "Food"): 90_000_000, ("UZS", "Taxi"): 50_000_000}, [budget])
    vm = cards.build_view(data, "uz", "my_bot")
    assert vm["template"] == "weekly" and not vm["mixed"]
    assert vm["title"] == "HAFTALIK CHEK" and vm["dates"] == "26.10.2026 — 01.11.2026"
    assert vm["meta"] == "№ 44 · 4 ta xarajat"
    section = vm["sections"][0]
    assert [r["name"] for r in section["rows"]] == ["FOOD", "TAXI"]
    assert section["rows"][0]["change"] == {"text": "▲ 18%", "tone": "up"}
    assert section["rows"][1]["change"] == {"text": "▼ 12%", "tone": "dn"}
    assert section["total"] == f"1{NB}500{NB}000" and section["prev_total"] == f"1{NB}400{NB}000"
    assert vm["stamp"]["sub"] == "KOʻPROQ"
    bars = section["bars"]["bars"]
    assert [b["label"] for b in bars] == ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    assert [b["value"] for b in bars] == ["420", "0", "980", "0", "0", "0", "100"]
    assert bars[2]["hi"] and bars[2]["h"] == 130
    assert vm["biggest"] == {"name": "KORZINKA", "suffix": " · CHOR", "amount": f"640{NB}000"}
    assert vm["budget_note"] == {"text": "* Food byudjeti: 106% ishlatildi", "over": True}
    assert vm["footer_left"] == "@my_bot" and vm["footer_right"] == "RAHMAT!"
    assert cards.build_view(data, "ru")["footer_left"] == ""


@pytest.mark.parametrize("lang, title, total, thanks", [
    ("uz", "HAFTALIK CHEK", "JAMI", "RAHMAT!"), ("ru", "НЕДЕЛЬНЫЙ ЧЕК", "ИТОГО", "СПАСИБО!"),
    ("en", "WEEKLY RECEIPT", "TOTAL", "THANK YOU!")])
def test_labels_are_localized(lang, title, total, thanks):
    vm = cards.build_view(weekly_data([expense(WEEK_START, 100)]), lang)
    assert (vm["title"], vm["sections"][0]["total_label"], vm["footer_right"]) == (title, total, thanks)
    html = cards.render_html(vm)
    assert title in html and thanks in html and "@font-face" in html


def test_monthly_view_model_folds_and_splits_payments():
    start, end = date(2026, 10, 5), date(2026, 11, 5)
    rows = [expense(date(2026, 10, 5 + i), (i + 1) * 1_000_000, category=f"Cat{i}",
                    kind=("cash", "debit", "credit")[i % 3]) for i in range(10)]
    data = weekly_data(rows, kind="monthly", start=start, end=end, compare=(date(2026, 9, 5), start))
    data.current.totals[("income", "UZS")] = 100_000_000
    data.credit = [("UZS", 3_200_000, 10_000_000), ("UZS", 100, 0), ("USD", 5, 100)]
    data.budgets = [db.BudgetUsage("Cat9", "UZS", 5_000_000, 10_000_000), db.BudgetUsage("Cat0", "UZS", 0, 5)]
    vm = cards.build_view(data, "en")
    rows_vm = vm["sections"][0]["rows"]
    assert len(rows_vm) == 8 and rows_vm[-1]["name"] == "OTHER"
    assert rows_vm[-1]["amount"] == f"60{NB}000"  # Cat0 + Cat1 + Cat2
    assert vm["meta"] == "31 days · 10 expenses"
    labels = [b["label"] for b in vm["sections"][0]["bars"]["bars"]]
    assert labels == ["Week 1", "Week 2", "Week 3", "Week 4", "3 days"]
    assert vm["balances"][0]["income"] == f"+1{NB}000{NB}000" and vm["balances"][0]["balance"] == f"+450{NB}000"
    assert [r["name"] for r in vm["top"]] == ["1. CAT9", "2. CAT8", "3. CAT7"]
    assert vm["budgets"]["rows"] == [{"name": "CAT9", "ascii": "[##########]", "percent": "! 200%", "over": True}]
    assert vm["budgets"]["over"] == "! 1 over"
    payments = vm["payments"][0]
    assert [p["kind"] for p in payments["parts"]] == ["cash", "debit", "credit"]
    assert sum(int(p["percent"].rstrip("%")) for p in payments["parts"]) == 100
    assert payments["credit"] == {"used": f"32{NB}000 / 100{NB}000", "ascii": "[####------]", "percent": "32%",
                                  "over": False}
    html = cards.render_html(vm)
    assert "MONTHLY RECEIPT" in html and "PAYMENT METHOD" in html and "[####------]" in html


def test_report_view_model_shares_and_over_budget():
    start, end = date(2026, 10, 5), date(2026, 11, 5)
    rows = [expense(start, 412_000_000), expense(start, 186_000_000, category="Utilities")]
    data = weekly_data(rows, {("UZS", "Food"): 400_000_000}, kind="report", start=start, end=end,
                       compare=(date(2026, 9, 5), date(2026, 9, 25)))
    data.partial, data.through = True, date(2026, 10, 24)
    data.budgets = [db.BudgetUsage("Food", "UZS", 400_000_000, 412_000_000)]
    vm = cards.build_view(data, "uz")
    assert vm["dates"] == "05.10.2026 — 24.10.2026" and vm["meta"] == "Kategoriyalar · 2 ta xarajat"
    first = vm["sections"][0]["rows"][0]
    assert first["share"] == "68,9%" and first["bar"] == "█" * 20
    assert vm["sections"][0]["rows"][1]["change"]["text"] == "yangi"
    assert vm["sections"][0]["prev_label"] == "OLDINGI DAVR, SHU 20 KUN"
    assert vm["over_budget"]["rows"] == [{"name": "FOOD", "amount": f"+120{NB}000", "percent": "103%"}]
    assert vm["footer_right"] == "▲ koʻp · ▼ kam"
    assert "OLDINGI DAVR, SHU 20 KUN" in cards.render_html(vm)


def test_mixed_currencies_get_separate_sections_without_conversion():
    rows = [expense(WEEK_START, 986_000_000), expense(WEEK_START, 64_000, "USD", "Clothes"),
            expense(WEEK_START, 60_050, "USD")]
    data = weekly_data(rows, {("USD", "Food"): 53_600}, kind="report")
    vm = cards.build_view(data, "uz")
    assert vm["mixed"] and [s["currency"] for s in vm["sections"]] == ["UZS", "USD"]
    assert vm["stamp"] == {"main": "UZS+USD", "sub": "ALOHIDA", "tone": "ink"}
    uzs, usd = vm["sections"]
    assert uzs["total"] == f"9{NB}860{NB}000" and uzs["total_label"] == "JAMI, SOʻM"
    assert usd["total"] == f"$1{NB}240.50" and usd["total_label"] == "JAMI, USD"
    assert usd["prev_change"] == {"text": "▲ 131%", "tone": "up"}
    assert vm["meta"] == "2 valyuta · 3 ta xarajat" and vm["footer_right"] == "RAHMAT!"
    html = cards.render_html(vm)
    assert "SOʻMDA" in html and "DOLLARDA" in html and "kurs boʻyicha qoʻshilmagan" in html


def test_empty_period_card():
    data = weekly_data([])
    data.current.totals[("income", "UZS")] = 5_000_000  # income alone is still an empty receipt
    for lang in LANGUAGES:
        vm = cards.build_view(data, lang)
        assert vm["template"] == "empty" and vm["stamp"] is None
        assert cards.render_html(vm).count("— — —") == 4
    vm = cards.build_view(data, "uz")
    assert vm["meta"] == "№ 44 · 0 ta xarajat" and vm["empty"]["stamp"] == "XARAJAT YOʻQ"
    assert vm["empty"]["when"] == "BU HAFTA"


def test_long_names_and_huge_amounts_render_into_html():
    name = "Very long category name that never ends " * 3
    rows = [expense(WEEK_START, 99_999_999_900, category=name, note="<script>alert(1)</script>")]
    html = cards.render_html(cards.build_view(weekly_data(rows), "en"))
    assert f"999{NB}999{NB}999" in html
    assert "&lt;SCRIPT&gt;" in html and "<script>" not in html  # user text is escaped
    assert "VERY LONG CATEGORY NAME THAT NEVER ENDS VERY LO…" in html


# ---- Loading from the DB ----

async def test_load_card_data_reads_rows_and_counts_operations():
    cash, card, credit, usd = await setup_user()
    await db.set_credit_limit(USER, credit.id, 1_000_000)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 30_000), db.Leg(credit.id, 20_000)],
                              "Food", note="Split", occurred_at=datetime(2026, 10, 27, 12))
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 500)], "Food", occurred_at=datetime(2026, 10, 28))
    await db.record_transfer(USER, card.id, cash.id, 10_000, occurred_at=datetime(2026, 10, 27, 13))
    await db.record_operation(USER, "expense", "UZS", [db.Leg(card.id, 70_000)], "Taxi",
                              occurred_at=datetime(2026, 10, 20, 12))
    start, end, cmp_start, cmp_end = assistant.advice_windows("weekly", MONDAY, 1)
    data = await cards.load_card_data(USER, "weekly", start, end, cmp_start, cmp_end, budgets=[])
    assert len(data.rows) == 3 and {r.account_kind for r in data.rows} == {"cash", "credit"}  # no transfer
    assert data.spent_currencies() == ["UZS", "USD"] and data.previous.total("expense", "UZS") == 70_000
    vm = cards.build_view(data, "en")
    assert vm["mixed"] and vm["meta"] == "№ 44 · 2 expenses"  # the split purchase is one expense
    assert vm["biggest"]["name"] == "SPLIT" and vm["biggest"]["amount"] == "500"
    assert ("UZS", 220_000, 1_000_000) in data.credit  # opening debt + the credit leg


# ---- Fallbacks ----

async def test_render_failure_returns_none_and_advice_falls_back_to_chart(monkeypatch):
    async def broken(html):
        raise RuntimeError("chromium crashed")

    monkeypatch.setattr(cards.renderer, "render", broken)
    data = weekly_data([expense(WEEK_START, 100_000)])
    assert await cards.render_card(data, "uz") is None
    png = await cards.card_or_chart(data, "uz")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # the matplotlib chart
    assert await cards.card_or_chart(weekly_data([]), "uz") is None  # nothing to chart: text only


async def test_missing_playwright_disables_rendering_for_a_while(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    renderer = cards.CardRenderer(timeout=5)
    monkeypatch.setattr(builtins, "__import__", no_playwright)
    with pytest.raises(cards.RenderUnavailable):
        await renderer.render("<html></html>")
    monkeypatch.setattr(builtins, "__import__", real_import)
    with pytest.raises(cards.RenderUnavailable, match="recently"):  # not retried on every report
        await renderer.render("<html></html>")
    await renderer.close()


async def test_render_timeout_is_handled(monkeypatch):
    import asyncio

    async def slow(html):
        await asyncio.sleep(10)

    monkeypatch.setattr(cards.renderer, "_render", slow)
    monkeypatch.setattr(cards.renderer, "timeout", 0.05)
    assert await cards.render_card(weekly_data([expense(WEEK_START, 100)]), "en") is None


async def test_card_falls_back_to_matplotlib_chart(monkeypatch):
    cash, *_ = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 50_000)], "Food")

    async def no_card(*args, **kwargs):
        return None

    monkeypatch.setattr(cards, "render_card", no_card)
    report = await db.build_period_report(USER, 0)
    png = await cards.card_or_chart(await cards.report_data(USER, report), "en")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


class PhotoBot:
    def __init__(self, fail_photo=False):
        self.calls = []
        self.fail_photo = fail_photo

    async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, parse_mode=None):
        if self.fail_photo:
            raise TelegramAPIError("PHOTO_INVALID_DIMENSIONS")
        self.calls.append(("photo", caption, reply_markup, parse_mode))

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.calls.append(("text", text, reply_markup, parse_mode))


async def test_send_advice_caption_limit_and_photo_failure(monkeypatch):
    bot = PhotoBot()
    monkeypatch.setattr(sched, "bot", bot)
    await sched.send_advice(1, "short <b>advice</b>", "Header", b"png", "kb")
    assert bot.calls == [("photo", "short <b>advice</b>", "kb", "html")]

    bot.calls.clear()
    long_text = "x" * 1500
    await sched.send_advice(1, long_text, "Header", b"png", "kb")
    assert bot.calls == [("photo", "Header", None, "html"), ("text", long_text, "kb", "html")]

    bot.calls.clear()
    await sched.send_advice(1, "text", "Header", None, "kb")
    assert bot.calls == [("text", "text", "kb", "html")]

    failing = PhotoBot(fail_photo=True)
    monkeypatch.setattr(sched, "bot", failing)
    await sched.send_advice(1, "text", "Header", b"png", "kb")
    assert failing.calls == [("text", "text", "kb", "html")]


# ---- Real render ----

async def test_real_render_smoke():
    rows = [expense(WEEK_START + timedelta(days=i), (i + 1) * 10_000_000, category=f"Category {i}") for i in range(7)]
    html = cards.render_html(cards.build_view(weekly_data(rows), "ru"))
    renderer = cards.CardRenderer(timeout=60)
    try:
        png = await renderer.render(html)
    except cards.RenderUnavailable as err:
        pytest.skip(f"Chromium is not available: {err}")
    finally:
        await renderer.close()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", png[16:24])
    assert width == cards.WIDTH and 1000 < height < 2500  # full page, content-driven height
