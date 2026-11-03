import re
from datetime import date

import pytest

from utils.db_api import finance as db
from utils.i18n import LANGUAGES, TEXTS
from utils.misc.money import parse_amount

USER = 7


async def setup_user(lang: str = "en"):
    await db.set_language(USER, "owner", lang)
    cash = await db.create_account(USER, "Wallet", "cash", "UZS", opening_minor=100_000)
    card = await db.create_account(USER, "Card", "debit", "UZS", opening_minor=500_000)
    credit = await db.create_account(USER, "Visa", "credit", "UZS", opening_minor=-200_000,
                                     credit_limit_minor=1_000_000)
    usd = await db.create_account(USER, "Dollars", "cash", "USD", opening_minor=10_000)
    return cash, card, credit, usd


async def balance(account_id: int) -> int:
    from utils.db_api.base import session_factory
    from utils.db_api.models import Account
    async with session_factory() as session:
        return (await session.get(Account, account_id)).balance_minor


# ---- Pure helpers ----

@pytest.mark.parametrize("salary_day, today, expected", [
    (5, date(2026, 3, 10), date(2026, 3, 5)),
    (5, date(2026, 3, 5), date(2026, 3, 5)),
    (5, date(2026, 3, 4), date(2026, 2, 5)),
    (10, date(2026, 1, 3), date(2025, 12, 10)),
    (31, date(2026, 2, 28), date(2026, 2, 28)),  # capped at 28
    (1, date(2026, 7, 1), date(2026, 7, 1)),
])
def test_period_start(salary_day, today, expected):
    assert db.period_start(salary_day, today) == expected


def test_parse_amount():
    assert parse_amount("12 500,50") == 1_250_050
    assert parse_amount("0") is None
    assert parse_amount("0", allow_zero=True) == 0
    assert parse_amount("-5") is None
    assert parse_amount("abc") is None


def test_translations_complete():
    for key, variants in TEXTS.items():
        assert set(variants) == set(LANGUAGES), key
        placeholders = {lang: set(re.findall(r"{(\w+)}", text)) for lang, text in variants.items()}
        assert len({frozenset(p) for p in placeholders.values()}) == 1, key


# ---- Users and seeding ----

async def test_language_seeds_once_in_chosen_language():
    assert await db.set_language(USER, "owner", "ru") is True
    names = [c.name for c in await db.list_categories(USER, "expense")]
    assert "Транспорт" in names
    assert any(a.name == "Наличные" for a in await db.list_accounts(USER))

    # Changing the language later does not seed again or rename user data
    assert await db.set_language(USER, "owner", "uz") is False
    assert (await db.get_user(USER)).language == "uz"
    assert len(await db.list_categories(USER, "expense")) == len(names)


# ---- Expenses and incomes ----

async def test_expense_and_income_update_balances():
    cash, card, credit, usd = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 30_000)], "Food", "Coffee")
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 250_000)], "Salary")
    await db.record_operation(USER, "expense", "UZS", [db.Leg(credit.id, 50_000)], "Food")
    assert await balance(cash.id) == 70_000
    assert await balance(card.id) == 750_000
    assert await balance(credit.id) == -250_000  # debt grows


async def test_split_purchase_shares_group():
    cash, card, *_ = await setup_user()
    first = await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 10_000)], "Food")
    second = await db.record_operation(USER, "expense", "UZS", [db.Leg(card.id, 5_000)], "Food",
                                       group_id=first.group_id)
    assert first.group_id == second.group_id
    assert len(await db.recent_operations(USER)) == 2


async def test_currency_mismatch_and_inactive_account_rejected():
    cash, card, credit, usd = await setup_user()
    with pytest.raises(db.CurrencyMismatch):
        await db.record_operation(USER, "expense", "UZS", [db.Leg(usd.id, 100)], "Food")
    await db.deactivate_account(USER, cash.id)
    with pytest.raises(db.AccountNotFound):
        await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 100)], "Food")
    assert await balance(usd.id) == 10_000


async def test_credit_limit_warning():
    cash, card, credit, usd = await setup_user()
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(credit.id, 700_000)], "Food")
    assert saved.over_limit == []  # debt 900k of 1m
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(credit.id, 200_000)], "Food")
    assert [a.id for a in saved.over_limit] == [credit.id]
    assert db.debt(saved.over_limit[0]) == 1_100_000
    assert db.available_credit(saved.over_limit[0]) == -100_000


# ---- Transfers ----

async def test_transfer_and_repayment_excluded_from_report():
    cash, card, credit, usd = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 20_000)], "Food")
    await db.record_transfer(USER, card.id, cash.id, 50_000)
    await db.record_transfer(USER, card.id, credit.id, 200_000)  # repay the whole debt
    assert await balance(card.id) == 250_000
    assert await balance(cash.id) == 130_000
    assert await balance(credit.id) == 0

    report = await db.build_report(USER)
    assert report.totals == {("expense", "UZS"): 20_000}

    views = await db.recent_operations(USER)
    assert len(views) == 3  # each transfer shown once
    assert views[0].is_transfer and views[0].counterpart_account.id == credit.id


async def test_transfer_validation():
    cash, card, credit, usd = await setup_user()
    with pytest.raises(db.SameAccount):
        await db.record_transfer(USER, cash.id, cash.id, 100)
    with pytest.raises(db.CurrencyMismatch):
        await db.record_transfer(USER, cash.id, usd.id, 100)
    with pytest.raises(db.InvalidValue):
        await db.record_transfer(USER, cash.id, card.id, 0)


# ---- Edit / delete ----

async def test_edit_amount_and_account():
    cash, card, *_ = await setup_user()
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 30_000)], "Food")
    tx_id = saved.transactions[0].id

    await db.update_amount(USER, tx_id, 45_000)
    assert await balance(cash.id) == 55_000

    await db.update_account(USER, tx_id, card.id)
    assert await balance(cash.id) == 100_000
    assert await balance(card.id) == 455_000

    await db.update_category(USER, tx_id, "Transport", "Taxi")
    view = await db.get_operation(USER, tx_id)
    assert (view.tx.category, view.tx.subcategory, view.account.id) == ("Transport", "Taxi", card.id)


async def test_edit_transfer_amount_changes_both_legs():
    cash, card, *_ = await setup_user()
    saved = await db.record_transfer(USER, card.id, cash.id, 50_000)
    incoming = saved.transactions[1]
    await db.update_amount(USER, incoming.id, 80_000)  # opened via either leg
    assert await balance(card.id) == 420_000
    assert await balance(cash.id) == 180_000
    with pytest.raises(db.InvalidValue):
        await db.update_account(USER, incoming.id, card.id)


async def test_delete_operation_and_transfer():
    cash, card, credit, _ = await setup_user()
    expense = await db.record_operation(USER, "expense", "UZS", [db.Leg(credit.id, 40_000)], "Food")
    transfer = await db.record_transfer(USER, card.id, credit.id, 100_000)

    await db.delete_operation(USER, expense.transactions[0].id)
    assert await balance(credit.id) == -100_000

    await db.delete_operation(USER, transfer.transactions[1].id)  # deleting one leg removes both
    assert await balance(credit.id) == -200_000
    assert await balance(card.id) == 500_000
    assert await db.recent_operations(USER) == []
    with pytest.raises(db.OperationNotFound):
        await db.get_operation(USER, transfer.transactions[0].id)


async def test_edit_on_deactivated_account_still_corrects_balance():
    cash, card, *_ = await setup_user()
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 10_000)], "Food")
    await db.deactivate_account(USER, cash.id)
    assert cash.id not in [a.id for a in await db.list_accounts(USER)]
    assert len(await db.recent_operations(USER)) == 1  # history kept
    await db.delete_operation(USER, saved.transactions[0].id)
    assert await balance(cash.id) == 100_000


# ---- Accounts ----

async def test_account_edits():
    cash, card, credit, _ = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 30_000)], "Food")
    account = await db.set_opening_balance(USER, cash.id, 150_000)
    assert (account.opening_balance_minor, account.balance_minor) == (150_000, 120_000)

    account = await db.rename_account(USER, cash.id, "  Pocket   money ")
    assert account.name == "Pocket money"
    with pytest.raises(db.InvalidValue):
        await db.rename_account(USER, cash.id, "   ")

    account = await db.set_credit_limit(USER, credit.id, 2_000_000)
    assert db.available_credit(account) == 1_800_000
    with pytest.raises(db.InvalidValue):
        await db.set_credit_limit(USER, cash.id, 1)


async def test_other_user_cannot_touch_data():
    cash, *_ = await setup_user()
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 1_000)], "Food")
    await db.set_language(99, "stranger", "en")
    with pytest.raises(db.AccountNotFound):
        await db.record_operation(99, "expense", "UZS", [db.Leg(cash.id, 1_000)], "Food")
    with pytest.raises(db.OperationNotFound):
        await db.delete_operation(99, saved.transactions[0].id)
