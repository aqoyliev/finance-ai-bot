from collections import namedtuple

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import finance as kb
from keyboards.inline import operations as op_kb
from loader import dp
from states.finance import FinanceForm
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import money_text, parse_amount
from utils.misc.texts import balance_line, operation_line, over_limit_warning

Choice = namedtuple("Choice", "id name")  # item shape expected by kb.choices


async def session_lost(call: types.CallbackQuery, state: FSMContext, lang: str):
    await state.finish()
    await call.message.edit_text(t("session_lost", lang), reply_markup=kb.main_menu(lang))


async def ask_amount(message: types.Message, lang: str, split: bool = False):
    await FinanceForm.amount.set()
    await message.edit_text(t("ask_split_amount" if split else "ask_amount", lang),
                            reply_markup=kb.amount_prompt(lang))


async def ask_currency(message: types.Message, amount_minor: int, state: FSMContext, lang: str, edit: bool):
    await state.update_data(amount_minor=amount_minor)
    send = message.edit_text if edit else message.answer
    await send(t("ask_currency", lang), reply_markup=kb.currencies(lang))


# ---- Expense / income ----

@dp.callback_query_handler(Text(equals=["menu:expense", "menu:income"]), state="*")
async def choose_kind(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    kind = call.data.split(":")[1]
    await state.finish()
    await state.update_data(kind=kind)
    categories = await db.list_categories(call.from_user.id, kind)
    title = t("ask_expense_category" if kind == "expense" else "ask_income_category", lang)
    await call.message.edit_text(title, reply_markup=kb.choices(categories, "cat", lang))


@dp.callback_query_handler(Text(startswith="cat:"), state="*")
async def choose_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    data = await state.get_data()
    category = await db.get_category(call.from_user.id, int(call.data.split(":")[1]))
    if category is None or "kind" not in data:
        await session_lost(call, state, lang)
        return
    await state.update_data(category=category.name, subcategory=None)
    if data["kind"] == "expense":
        subcategories = await db.list_subcategories(category.id)
        await call.message.edit_text(t("ask_subcategory", lang), reply_markup=kb.subcategories(subcategories, lang))
    else:
        await ask_amount(call.message, lang)


@dp.callback_query_handler(Text(startswith="sub:"), state="*")
async def choose_subcategory(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if "category" not in await state.get_data():
        await session_lost(call, state, lang)
        return
    subcategory_id = int(call.data.split(":")[1])
    subcategory = await db.get_subcategory(call.from_user.id, subcategory_id) if subcategory_id else None
    await state.update_data(subcategory=subcategory.name if subcategory else None)
    await ask_amount(call.message, lang)


# ---- Amount, currency, account ----

@dp.callback_query_handler(Text(startswith="quick:"), state=FinanceForm.amount)
async def quick_amount(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    amount = parse_amount(call.data.split(":", 1)[1])
    await state.reset_state(with_data=False)
    await ask_currency(call.message, amount, state, lang, edit=True)


@dp.message_handler(state=FinanceForm.amount)
async def typed_amount(message: types.Message, state: FSMContext, lang: str):
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(t("bad_amount", lang))
        return
    await state.reset_state(with_data=False)
    await ask_currency(message, amount, state, lang, edit=False)


@dp.callback_query_handler(Text(startswith="cur:"), state="*")
async def choose_currency(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    currency = call.data.split(":")[1]
    data = await state.get_data()
    if currency not in db.CURRENCIES or not data.get("amount_minor"):
        await session_lost(call, state, lang)
        return
    await state.update_data(currency=currency)
    accounts = await db.list_accounts(call.from_user.id, currency)
    if not accounts:
        await state.finish()
        await call.message.edit_text(t("no_accounts_in_currency", lang, currency=currency),
                                     reply_markup=kb.main_menu(lang))
        return
    labels = [Choice(a.id, f"{a.name} ({a.currency})") for a in accounts]
    await call.message.edit_text(t("ask_account", lang, currency=currency),
                                 reply_markup=kb.choices(labels, "acc", lang))


@dp.callback_query_handler(Text(startswith="acc:"), state="*")
async def choose_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    data = await state.get_data()
    if not data.get("amount_minor") or "currency" not in data or "kind" not in data:
        await session_lost(call, state, lang)
        return

    amount, currency, kind = data["amount_minor"], data["currency"], data["kind"]
    try:
        saved = await db.record_operation(
            call.from_user.id, kind, currency, [db.Leg(int(call.data.split(":")[1]), amount)],
            category=data.get("category"), subcategory=data.get("subcategory"), group_id=data.get("group_id"))
    except db.AccountNotFound:
        await state.finish()
        await call.message.edit_text(t("account_not_found", lang), reply_markup=kb.main_menu(lang))
        return
    except db.CurrencyMismatch as err:
        await state.finish()
        await call.message.edit_text(
            t("currency_mismatch", lang, account_currency=err.account_currency, currency=currency),
            reply_markup=kb.main_menu(lang))
        return

    await state.update_data(amount_minor=None, group_id=saved.group_id)
    warnings = over_limit_warning(saved.over_limit, lang)
    if kind == "expense":
        text = t("expense_saved", lang, amount=money_text(amount, currency), category=data.get("category"),
                 subcategory=data.get("subcategory") or "—")
        await call.message.edit_text("\n\n".join([text] + warnings), reply_markup=kb.split_or_finish(lang))
    else:
        await state.finish()
        text = t("income_saved", lang, amount=money_text(amount, currency), category=data.get("category"))
        await call.message.edit_text("\n\n".join([text] + warnings), reply_markup=kb.main_menu(lang))


@dp.callback_query_handler(Text(equals="split:more"), state="*")
async def split_more(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if "group_id" not in await state.get_data():
        await session_lost(call, state, lang)
        return
    await ask_amount(call.message, lang, split=True)


@dp.callback_query_handler(Text(equals="split:finish"), state="*")
async def split_finish(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await call.message.edit_text(t("operation_saved", lang), reply_markup=kb.main_menu(lang))


@dp.callback_query_handler(Text(equals="cancel"), state="*")
async def cancel(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await call.message.edit_text(t("cancelled", lang), reply_markup=kb.main_menu(lang))


# ---- Report and history ----

@dp.callback_query_handler(Text(equals="menu:report"), state="*")
async def show_report(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    report = await db.build_report(call.from_user.id)

    lines = [t("report_title", lang, start=report.start.strftime("%d.%m.%Y")), ""]
    for currency in db.CURRENCIES:
        income = report.totals.get(("income", currency), 0)
        expense = report.totals.get(("expense", currency), 0)
        if income or expense:
            lines.append(t("report_line", lang, currency=currency, income=money_text(income, currency),
                           expense=money_text(expense, currency), net=money_text(income - expense, currency)))
    if len(lines) == 2:
        lines.append(t("report_empty", lang))
    lines += ["", t("balances", lang)] + [balance_line(a, lang) for a in report.accounts]
    if report.usd_rate:
        lines += ["", t("current_rate", lang, rate=report.usd_rate)]
    else:
        lines += ["", t("rate_hint", lang)]
    await call.message.edit_text("\n".join(lines), reply_markup=kb.main_menu(lang))


@dp.callback_query_handler(Text(equals="menu:history"), state="*")
async def show_history(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    views = await db.recent_operations(call.from_user.id)
    if not views:
        await call.message.edit_text(t("history_empty", lang), reply_markup=kb.main_menu(lang))
        return
    lines = [t("history_title", lang)] + [operation_line(v, lang) for v in views]
    buttons = [(v.tx.id, operation_line(v, lang, escape=False)) for v in views]
    await call.message.edit_text("\n".join(lines), reply_markup=op_kb.history(buttons, lang))
