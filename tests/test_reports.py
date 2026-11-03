"""Category reports, budgets, limit alerts and charts."""
import warnings
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from utils import charts, notify_alerts
from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.db_api.base import session_factory
from utils.db_api.models import AlertSent
from utils.i18n import LANGUAGES
from utils.misc import texts
from utils.misc.money import short_money

from test_services import USER, setup_user

TODAY = date(2026, 3, 20)  # with salary day 5 the current period is 05.03 - 04.04


async def expense(account, amount, category="Food", sub=None, when=None, currency="UZS"):
    return await db.record_operation(USER, "expense", currency, [db.Leg(account.id, amount)], category, sub,
                                     occurred_at=when)


def at(month, day, year=2026, hour=12):
    return datetime(year, month, day, hour)


async def seed_period_data():
    """Salary day 5. Current period: Food 300k + Taxi 100k UZS, 20 USD Food. Previous: Food 200k, Taxi 50k."""
    cash, card, credit, usd = await setup_user()
    await db.set_salary_day(USER, 5)
    categories = {c.name for c in await db.list_categories(USER, "expense")}
    return cash, card, credit, usd, categories


# ---- Period math ----

def test_shift_period_wraps_years():
    assert rep.shift_period(date(2026, 1, 5), -1) == date(2025, 12, 5)
    assert rep.shift_period(date(2026, 12, 5), 1) == date(2027, 1, 5)
    assert rep.shift_period(date(2026, 3, 28), -14) == date(2025, 1, 28)


@pytest.mark.parametrize("salary_day, today, offset, expected", [
    (5, date(2026, 3, 20), 0, (date(2026, 3, 5), date(2026, 4, 5))),
    (5, date(2026, 3, 20), -1, (date(2026, 2, 5), date(2026, 3, 5))),
    (5, date(2026, 3, 4), 0, (date(2026, 2, 5), date(2026, 3, 5))),  # before the salary day: still last period
    (5, date(2026, 1, 3), -1, (date(2025, 11, 5), date(2025, 12, 5))),
    (25, date(2026, 1, 10), 0, (date(2025, 12, 25), date(2026, 1, 25))),  # year wrap
    (25, date(2026, 1, 10), -2, (date(2025, 10, 25), date(2025, 11, 25))),
    (31, date(2026, 2, 28), 0, (date(2026, 2, 28), date(2026, 3, 28))),  # salary day capped at 28
    (1, date(2026, 12, 31), 0, (date(2026, 12, 1), date(2027, 1, 1))),
])
def test_period_bounds(salary_day, today, offset, expected):
    assert rep.period_bounds(salary_day, today, offset) == expected


def test_periods_are_contiguous():
    start, end = rep.period_bounds(17, date(2026, 5, 3), 0)
    assert rep.period_bounds(17, date(2026, 5, 3), -1)[1] == start
    assert rep.period_bounds(17, date(2026, 5, 3), 1)[0] == end


def test_comparison_window_uses_same_days_while_period_runs():
    start, end = rep.period_bounds(5, TODAY)
    # 16 days elapsed (05.03 .. 20.03 inclusive) -> 05.02 .. 20.02 inclusive
    assert rep.comparison_window(start, end, TODAY) == (date(2026, 2, 5), date(2026, 2, 21))
    # First day of a period compares with the first day of the previous one
    assert rep.comparison_window(start, end, date(2026, 3, 5)) == (date(2026, 2, 5), date(2026, 2, 6))
    # Never extends into the current period (previous period is shorter than elapsed days)
    start, end = rep.period_bounds(5, date(2026, 4, 4))
    assert rep.comparison_window(start, end, date(2026, 4, 4)) == (date(2026, 2, 5), date(2026, 3, 5))


def test_comparison_window_for_completed_period_is_whole_previous_period():
    start, end = rep.period_bounds(5, TODAY, -1)
    assert rep.comparison_window(start, end, TODAY) == (date(2026, 1, 5), date(2026, 2, 5))


@pytest.mark.parametrize("current, previous, expected", [
    (150, 100, 50), (50, 100, -50), (100, 100, 0), (100, 0, None), (0, 0, None), (1, 3, -67),
])
def test_change_percent(current, previous, expected):
    assert rep.change_percent(current, previous) == expected


def test_share_percent_and_conversion():
    assert rep.share_percent(1, 3) == 33 and rep.share_percent(5, 0) == 0
    rate = Decimal("12500")
    assert rep.convert(200, "USD", "UZS", rate) == 2_500_000
    assert rep.convert(2_500_000, "UZS", "USD", rate) == 200
    assert rep.convert(100, "USD", "UZS", None) == 0
    assert rep.spent_in_currency({"UZS": 1_000_000, "USD": 100}, "UZS", rate) == 2_250_000
    assert rep.spent_in_currency({"UZS": 1_000_000, "USD": 100}, "UZS", None) == 1_000_000


# ---- Aggregation ----

async def test_report_by_category_excludes_transfers_and_splits_currencies():
    cash, card, credit, usd, _ = await seed_period_data()
    await expense(cash, 300_000, "Transport", "Taxi", at(3, 10))
    await expense(card, 100_000, "Health", None, at(3, 12))
    await expense(usd, 2_000, "Transport", "Taxi", at(3, 11), "USD")
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 900_000)], "Salary", occurred_at=at(3, 6))
    await db.record_transfer(USER, card.id, credit.id, 50_000, occurred_at=at(3, 15))  # not income / expense
    await expense(cash, 999_000, "Transport", "Taxi", at(4, 6))  # next period: excluded

    report = await db.build_period_report(USER, 0, today=TODAY)
    assert [c.currency for c in report.currencies] == ["UZS", "USD"]
    uzs, usd_summary = report.currencies
    assert (uzs.income, uzs.expense, uzs.balance) == (900_000, 400_000, 500_000)
    assert [(r.name, r.amount, r.share) for r in uzs.categories] == [("Transport", 300_000, 75), ("Health", 100_000, 25)]
    assert (usd_summary.income, usd_summary.expense) == (0, 2_000)
    assert [(r.name, r.share) for r in usd_summary.categories] == [("Transport", 100)]
    assert report.combined is None  # no USD rate yet

    await db.set_usd_rate(USER, Decimal("12500"))
    report = await db.build_period_report(USER, 0, today=TODAY)
    assert report.combined.expense == 400_000 + 25_000_000
    assert report.combined.income == 900_000
    series = report.chart_series()
    assert series[0] == "UZS" and series[2] is True
    assert dict(series[1]) == {"Transport": 300_000 + 25_000_000, "Health": 100_000}


async def test_report_comparison_with_previous_period():
    cash, *_ = await seed_period_data()
    await expense(cash, 300_000, "Food", None, at(3, 8))
    await expense(cash, 100_000, "Transport", None, at(3, 9))
    await expense(cash, 200_000, "Food", None, at(2, 10))  # inside the compared window (05.02 - 20.02)
    await expense(cash, 50_000, "Transport", None, at(2, 20))  # last compared day
    await expense(cash, 900_000, "Food", None, at(2, 21))  # outside it: the same days only

    report = await db.build_period_report(USER, 0, today=TODAY)
    uzs = report.currencies[0]
    assert uzs.prev_expense == 250_000 and uzs.expense_change == 60  # 400k vs 250k
    food = next(r for r in uzs.categories if r.name == "Food")
    assert (food.prev_amount, food.change) == (0 + 200_000, 50)
    assert report.compare_start == date(2026, 2, 5) and report.compare_last_day == date(2026, 2, 20)

    # The previous period viewed on its own is compared with the whole one before it
    past = await db.build_period_report(USER, -1, today=TODAY)
    assert past.currencies[0].expense == 200_000 + 50_000 + 900_000 and not past.is_current
    assert past.compare_start == date(2026, 1, 5) and past.compare_end == date(2026, 2, 5)


async def test_report_navigation_boundaries():
    cash, *_ = await seed_period_data()
    await expense(cash, 10_000, "Food", None, at(2, 5, hour=0))  # first second of the previous period
    await expense(cash, 20_000, "Food", None, at(3, 4, hour=23))  # last day of the previous period
    await expense(cash, 30_000, "Food", None, at(3, 5, hour=0))  # first second of the current one

    current = await db.build_period_report(USER, 0, today=TODAY)
    previous = await db.build_period_report(USER, -1, today=TODAY)
    assert current.currencies[0].expense == 30_000
    assert previous.currencies[0].expense == 30_000
    assert current.has_earlier and not previous.has_earlier
    assert (previous.start, previous.end) == (date(2026, 2, 5), date(2026, 3, 5))
    # The future is clamped to the current period
    assert (await db.build_period_report(USER, 3, today=TODAY)).offset == 0
    empty = await db.build_period_report(USER, -5, today=TODAY)
    assert not empty.has_data and empty.currencies == []


async def test_report_year_wrap_navigation():
    cash, *_ = await seed_period_data()
    await db.set_salary_day(USER, 25)
    await expense(cash, 70_000, "Food", None, datetime(2025, 12, 28, 10))
    jan = date(2026, 1, 10)
    current = await db.build_period_report(USER, 0, today=jan)
    assert (current.start, current.end) == (date(2025, 12, 25), date(2026, 1, 25))
    assert current.currencies[0].expense == 70_000
    previous = await db.build_period_report(USER, -1, today=jan)
    assert (previous.start, previous.end) == (date(2025, 11, 25), date(2025, 12, 25))


async def test_subcategory_breakdown():
    cash, card, *_ = await seed_period_data()
    await expense(cash, 30_000, "Transport", "Taxi", at(3, 8))
    await expense(card, 20_000, "Transport", "Taxi", at(3, 9))
    await expense(cash, 10_000, "Transport", "Fuel", at(3, 9))
    await expense(cash, 5_000, "Transport", None, at(3, 9))
    await expense(cash, 99_000, "Health", "Doctor", at(3, 9))
    await expense(cash, 44_000, "Transport", "Taxi", at(2, 9))  # previous period
    by_currency = await db.expense_by_subcategory(USER, "Transport", date(2026, 3, 5), date(2026, 4, 5))
    assert by_currency == {"UZS": [("Taxi", 50_000), ("Fuel", 10_000), (rep.NO_CATEGORY, 5_000)]}
    report = await db.build_period_report(USER, 0, today=TODAY)
    for lang in LANGUAGES:
        text = texts.subcategory_text(report, "Transport", by_currency, lang)
        assert "Taxi" in text and "500.00 UZS" in text


# ---- Budgets ----

async def test_budget_crud_and_validation():
    await seed_period_data()
    assert await db.get_budget(USER, "Food") is None
    budget = await db.set_budget(USER, "Transport", "UZS", 500_000)
    assert (budget.currency, budget.amount_minor) == ("UZS", 500_000)
    await db.set_budget(USER, "Transport", "USD", 10_000)  # change
    assert (await db.list_budgets(USER))["Transport"].currency == "USD"
    for args in (("Transport", "EUR", 100), ("Transport", "UZS", 0), ("Salary", "UZS", 100),  # income category
                 ("Nope", "UZS", 100)):
        with pytest.raises(db.InvalidValue):
            await db.set_budget(USER, *args)
    assert await db.remove_budget(USER, "Transport") is True
    assert await db.remove_budget(USER, "Transport") is False
    assert await db.list_budgets(USER) == {}


async def test_budget_usage_in_report_converts_other_currency():
    cash, card, credit, usd, _ = await seed_period_data()
    today = db.now().date()
    await db.set_budget(USER, "Transport", "UZS", 1_000_000)
    await expense(cash, 600_000, "Transport")
    await expense(usd, 1_000, "Transport", currency="USD")  # 10 USD, ignored without a rate
    usage = (await db.budget_usages(USER))[0]
    assert (usage.spent, usage.percent) == (600_000, 60)
    await db.set_usd_rate(USER, Decimal("100"))
    usage = (await db.build_period_report(USER, 0, today=today)).budgets[0]
    assert (usage.limit, usage.spent, usage.percent) == (1_000_000, 700_000, 70)


# ---- Alerts ----

async def alerts_for(*categories, accounts=(), warned=()):
    return await db.check_alerts(USER, categories, accounts, already_warned=warned)


async def test_budget_alerts_at_80_and_100_once_per_period():
    cash, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 1_000_000)
    await expense(cash, 700_000, "Transport")
    assert await alerts_for("Transport") == []

    await expense(cash, 100_000, "Transport")  # 80%
    first = await alerts_for("Transport")
    assert [(a.kind, a.threshold, a.name, a.percent) for a in first] == [("budget", 80, "Transport", 80)]
    assert await alerts_for("Transport") == []  # same state, no repeat

    await expense(cash, 50_000, "Transport")  # 85%: nothing new
    assert await alerts_for("Transport") == []
    await expense(cash, 150_000, "Transport")  # 100%
    second = await alerts_for("Transport")
    assert [(a.threshold, a.percent) for a in second] == [(100, 100)]
    await expense(cash, 500_000, "Transport")  # 150%: already told at 100
    assert await alerts_for("Transport") == []
    assert await alerts_for("Food") == []  # other categories without a budget are never alerted


async def test_budget_alert_jump_reports_only_highest_and_marks_both():
    cash, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    await expense(cash, 120_000, "Transport")
    assert [a.threshold for a in await alerts_for("Transport")] == [100]
    assert await alerts_for("Transport") == []
    async with session_factory() as session:
        sent = {row.threshold for row in await session.scalars(select(AlertSent))}
    assert sent == {80, 100}


async def test_alerts_restart_in_a_new_period():
    cash, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    # An alert that was sent in an earlier period does not suppress this period's alert
    async with session_factory() as session, session.begin():
        session.add(AlertSent(user_id=USER, kind="budget", ref="Transport", threshold=100,
                              period_start=date(2020, 1, 1), sent_at=datetime(2020, 1, 2)))
    await expense(cash, 120_000, "Transport")
    assert [a.threshold for a in await alerts_for("Transport")] == [100]


async def test_deleting_and_recrossing_does_not_repeat_in_the_same_period():
    cash, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    saved = await expense(cash, 90_000, "Transport")
    assert [a.threshold for a in await alerts_for("Transport")] == [80]
    await db.update_amount(USER, saved.transactions[0].id, 10_000)  # edited down below the threshold
    assert await alerts_for("Transport") == []
    await db.update_amount(USER, saved.transactions[0].id, 95_000)  # crossing again: not announced again
    assert await alerts_for("Transport") == []


async def test_changing_a_budget_limit_starts_alerts_over():
    cash, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    await expense(cash, 90_000, "Transport")
    assert len(await alerts_for("Transport")) == 1
    await db.set_budget(USER, "Transport", "UZS", 110_000)  # 82%: a fresh 80% alert
    assert [a.threshold for a in await alerts_for("Transport")] == [80]


async def test_credit_card_alerts():
    cash, card, credit, usd, _ = await seed_period_data()  # Visa: debt 200k, limit 1m
    assert await alerts_for(accounts=[credit.id]) == []
    await expense(credit, 600_000)  # debt 800k = 80%
    alerts = await alerts_for(accounts=[credit.id])
    assert [(a.kind, a.threshold, a.name, a.used, a.limit) for a in alerts] == [
        ("credit", 80, "Visa", 800_000, 1_000_000)]
    assert await alerts_for(accounts=[credit.id]) == []
    await expense(credit, 250_000)  # debt 1.05m: over the limit
    over = await alerts_for(accounts=[credit.id], warned=[credit.id])
    assert over == []  # the save confirmation already warned about it; recorded, not repeated
    assert await alerts_for(accounts=[credit.id]) == []
    # Cash/debit accounts and credit cards without a limit never alert
    assert await alerts_for(accounts=[cash.id, card.id]) == []
    no_limit = await db.create_account(USER, "Loose", "credit", "UZS", opening_minor=-5_000_000)
    assert await alerts_for(accounts=[no_limit.id]) == []


async def test_credit_repayment_does_not_alert():
    cash, card, credit, *_ = await seed_period_data()
    await db.record_transfer(USER, card.id, credit.id, 100_000)
    assert await alerts_for(accounts=[credit.id]) == []


async def test_send_alerts_hook(monkeypatch):
    """One call after a save: budget + credit alerts are sent; an over-limit card is not said twice."""
    cash, card, credit, *_ = await seed_period_data()
    await db.set_budget(USER, "Transport", "UZS", 100_000)
    sent = []

    async def fake_send(chat_id, text, **kwargs):
        sent.append((chat_id, text))

    monkeypatch.setattr(notify_alerts.bot, "send_message", fake_send)
    saved = await expense(cash, 85_000, "Transport")
    await notify_alerts.send_alerts(USER, "en", saved)
    assert len(sent) == 1 and sent[0][0] == USER and "85%" in sent[0][1] and "Transport" in sent[0][1]

    sent.clear()
    saved = await expense(credit, 900_000, "Food")  # debt 1.1m of 1m: confirmation shows the warning
    assert saved.over_limit
    await notify_alerts.send_alerts(USER, "ru", saved)
    assert sent == []

    sent.clear()
    saved = await expense(credit, 1, "Food")  # no new threshold
    await notify_alerts.send_alerts(USER, "uz", saved)
    assert sent == []


async def test_send_alerts_never_raises(monkeypatch):
    cash, *_ = await seed_period_data()

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "check_alerts", boom)
    await notify_alerts.send_alerts(USER, "en", await expense(cash, 1_000, "Transport"))


# ---- Text rendering ----

async def test_report_text_all_languages():
    cash, card, credit, usd, _ = await seed_period_data()
    await db.set_usd_rate(USER, Decimal("12500"))
    await db.set_budget(USER, "Transport", "UZS", 400_000)
    await expense(cash, 300_000, "Transport", "Taxi", at(3, 8))
    await expense(cash, 100_000, "Transport", "Taxi", at(2, 8))
    await expense(usd, 2_000, "Health", None, at(3, 9), "USD")
    report = await db.build_period_report(USER, 0, today=TODAY)
    for lang in LANGUAGES:
        text = texts.report_text(report, lang)
        assert "3 000.00 UZS" in text and "75%" in text and "▲ 200%" in text  # 300k vs 100k
        assert "USD" in text and "▓" in text and "UZS" in text
        assert "12500" in text  # combined total is labeled with the rate
        assert "05.03.2026" in text
    past = await db.build_period_report(USER, -1, today=TODAY)
    assert "05.02.2026" in texts.report_text(past, "en") and "04.03.2026" in texts.report_text(past, "en")


async def test_empty_report_and_html_escape():
    cash, *_ = await seed_period_data()
    empty = await db.build_period_report(USER, 0, today=TODAY)
    assert "No income or expenses" in texts.report_text(empty, "en")
    await expense(cash, 1_000, "<b>x</b>", None, at(3, 8))
    text = texts.report_text(await db.build_period_report(USER, 0, today=TODAY), "en")
    assert "&lt;b&gt;x&lt;/b&gt;" in text


def test_progress_bar_and_alert_text():
    assert texts.progress_bar(0) == "░" * 10
    assert texts.progress_bar(80) == "▓" * 8 + "░" * 2
    assert texts.progress_bar(250) == "▓" * 10
    for lang in LANGUAGES:
        for kind in ("budget", "credit"):
            for threshold in (80, 100):
                alert = db.Alert(kind, threshold, "Food <1>", "UZS", 85_000, 100_000)
                text = texts.alert_text(alert, lang)
                assert "85%" in text and "Food &lt;1&gt;" in text and "▓" in text


def test_short_money():
    assert short_money(125_000_000) == "1.25M"
    assert short_money(250_000_00) == "250K"
    assert short_money(12_345) == "123"
    assert short_money(2_500_000_000_00) == "2.5B"


# ---- Chart ----

LABELS = [("Транспорт", 5_000_000), ("Oziq-ovqat 🍔", 3_000_000), ("O'yinlar G'ʻ", 1_000_000), ("Sog'liq", 500_000)]


@pytest.mark.parametrize("items", [LABELS, [(f"Категория {i}", 100_000 * (i + 1)) for i in range(14)]],
                         ids=["donut", "bars"])
def test_chart_is_png_and_renders_cyrillic_without_glyph_warnings(items):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        png = charts.render_expense_chart(items, "Расходы по категориям", "9.5M UZS", "Другое", short_money)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5_000
    assert [str(w.message) for w in caught if "missing from font" in str(w.message) or "Glyph" in str(w.message)] == []


def test_chart_item_grouping():
    many = [(f"c{i}", 1_000 + i) for i in range(14)]
    bars = charts.group_items(many, "Other", donut=False)
    assert len(bars) == charts.MAX_BARS + 1 and bars[-1][0] == "Other"
    assert bars[-1][1] == sum(v for _, v in sorted(many, key=lambda i: -i[1])[charts.MAX_BARS:])
    donut = charts.group_items([("a", 900), ("b", 80), ("c", 10), ("d", 10)], "Other", donut=True)
    assert donut == [("a", 900), ("b", 80), ("Other", 20)]
    assert charts.group_items([("a", 99), ("b", 1)], "Other", donut=True) == [("a", 99), ("b", 1)]
    assert charts.group_items([("a", 0)], "Other", donut=True) == []
    with pytest.raises(ValueError):
        charts.render_expense_chart([("a", 0)], "t", "0", "Other", short_money)


def test_printable_drops_emoji_but_keeps_cyrillic_and_uzbek():
    assert charts.printable("Oziq-ovqat 🍔") == "Oziq-ovqat"
    assert charts.printable("Транспорт 🚗") == "Транспорт"
    assert charts.printable("O‘zbek G‘isht") == "O‘zbek G‘isht"
