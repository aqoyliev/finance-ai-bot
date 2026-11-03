import uuid
from collections import namedtuple
from decimal import Decimal, InvalidOperation

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text

from keyboards.inline import finance as kb
from loader import dp
from states.finance import FinanceForm
from utils.db_api import finance as db
from utils.misc.money import money_text, parse_amount

SESSION_LOST = "Session expired. Start again: /start"

Choice = namedtuple("Choice", "id name")  # item shape expected by kb.choices


async def ask_amount(message: types.Message, split: bool = False):
    await FinanceForm.amount.set()
    text = ("Enter the amount of the next part of the purchase:" if split
            else "Enter the amount. Send a number, e.g. 10000 or 12500.50:")
    await message.edit_text(text, reply_markup=kb.amount_prompt())


async def ask_currency(message: types.Message, amount_minor: int, state: FSMContext, edit: bool):
    await state.update_data(amount_minor=amount_minor)
    send = message.edit_text if edit else message.answer
    await send("Choose the operation currency:", reply_markup=kb.currencies())


@dp.message_handler(Command("salaryday"), state="*")
async def salaryday(message: types.Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)
    arg = message.get_args().strip()
    if not arg.isdigit() or not 1 <= int(arg) <= 28:
        await message.answer("Enter a salary day from 1 to 28. Example: /salaryday 5")
        return
    await db.set_salary_day(message.from_user.id, int(arg))
    await message.answer(f"Your financial month will start on day {int(arg)}.")


@dp.message_handler(Command("rate"), state="*")
async def rate_command(message: types.Message):
    await db.ensure_user(message.from_user.id, message.from_user.username)
    args = message.get_args().split()
    if len(args) != 4 or args[1].upper() != "USD" or args[3].upper() != "UZS":
        await message.answer("Format: /rate 1 USD 12700 UZS")
        return
    try:
        rate = Decimal(args[2])
        if not rate.is_finite() or rate <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer("The rate must be a positive number.")
        return
    await db.set_usd_rate(message.from_user.id, rate)
    await message.answer(f"Rate saved: 1 USD = {rate} UZS")


# ---- Menu ----

@dp.callback_query_handler(Text(equals=["menu:expense", "menu:income"]), state="*")
async def choose_kind(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    kind = call.data.split(":")[1]
    await db.ensure_user(call.from_user.id, call.from_user.username)
    await state.finish()
    await state.update_data(kind=kind)
    categories = await db.list_categories(call.from_user.id, kind)
    title = "Choose an expense category:" if kind == "expense" else "Choose the income source:"
    await call.message.edit_text(title, reply_markup=kb.choices(categories, "cat"))


@dp.callback_query_handler(Text(startswith="cat:"), state="*")
async def choose_category(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    category = await db.get_category(call.from_user.id, int(call.data.split(":")[1]))
    if category is None or "kind" not in data:
        await call.message.edit_text(SESSION_LOST)
        return
    await state.update_data(category=category.name, subcategory=None)
    if data["kind"] == "expense":
        subcategories = await db.list_subcategories(category.id)
        await call.message.edit_text("Choose a subcategory:", reply_markup=kb.subcategories(subcategories))
    else:
        await ask_amount(call.message)


@dp.callback_query_handler(Text(startswith="sub:"), state="*")
async def choose_subcategory(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    if "category" not in await state.get_data():
        await call.message.edit_text(SESSION_LOST)
        return
    subcategory_id = int(call.data.split(":")[1])
    subcategory = await db.get_subcategory(subcategory_id) if subcategory_id else None
    await state.update_data(subcategory=subcategory.name if subcategory else None)
    await ask_amount(call.message)


# ---- Amount, currency, account ----

@dp.callback_query_handler(Text(startswith="quick:"), state=FinanceForm.amount)
async def quick_amount(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    amount = parse_amount(call.data.split(":", 1)[1])
    await state.reset_state(with_data=False)
    await ask_currency(call.message, amount, state, edit=True)


@dp.message_handler(state=FinanceForm.amount)
async def typed_amount(message: types.Message, state: FSMContext):
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer("Could not read the amount. Enter a positive number, e.g. 15000 or 12500.50.")
        return
    await state.reset_state(with_data=False)
    await ask_currency(message, amount, state, edit=False)


@dp.callback_query_handler(Text(startswith="cur:"), state="*")
async def choose_currency(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    currency = call.data.split(":")[1]
    data = await state.get_data()
    if currency not in db.CURRENCIES or not data.get("amount_minor"):
        await call.message.edit_text(SESSION_LOST)
        return
    await state.update_data(currency=currency)
    accounts = await db.list_accounts(call.from_user.id, currency)
    if not accounts:
        await state.finish()
        await call.message.edit_text(f"You have no {currency} accounts yet.", reply_markup=kb.main_menu())
        return
    labels = [Choice(a.id, f"{a.name} ({a.currency})") for a in accounts]
    await call.message.edit_text(
        f"Which account? Operation currency: {currency}.",
        reply_markup=kb.choices(labels, "acc"))


@dp.callback_query_handler(Text(startswith="acc:"), state="*")
async def choose_account(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    if not data.get("amount_minor") or "currency" not in data:
        await call.message.edit_text(SESSION_LOST)
        return

    group_id = data.get("group_id") or str(uuid.uuid4())
    await state.update_data(group_id=group_id)
    amount, currency, kind = data["amount_minor"], data["currency"], data["kind"]
    try:
        await db.add_transaction(
            call.from_user.id, int(call.data.split(":")[1]), kind, amount, currency,
            data.get("category"), data.get("subcategory"), group_id)
    except db.AccountNotFound:
        await call.message.edit_text("Account not found.", reply_markup=kb.main_menu())
        await state.finish()
        return
    except db.CurrencyMismatch as err:
        await call.message.edit_text(
            f"The account currency is {err.account_currency}, but the operation is in {currency}.",
            reply_markup=kb.main_menu())
        await state.finish()
        return

    await state.update_data(amount_minor=None)
    if kind == "expense":
        await call.message.edit_text(
            f"Expense part saved: {money_text(amount, currency)} · {data.get('category')} / "
            f"{data.get('subcategory') or '—'}.\nAdd a payment from another account?",
            reply_markup=kb.split_or_finish())
    else:
        await state.finish()
        await call.message.edit_text(
            f"Income saved: +{money_text(amount, currency)} · {data.get('category')}.",
            reply_markup=kb.main_menu())


@dp.callback_query_handler(Text(equals="split:more"), state="*")
async def split_more(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    if "group_id" not in await state.get_data():
        await call.message.edit_text(SESSION_LOST)
        return
    await ask_amount(call.message, split=True)


@dp.callback_query_handler(Text(equals="split:finish"), state="*")
async def split_finish(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    await call.message.edit_text("Operation saved.", reply_markup=kb.main_menu())


@dp.callback_query_handler(Text(equals="cancel"), state="*")
async def cancel(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.finish()
    await call.message.edit_text("Operation cancelled.", reply_markup=kb.main_menu())


# ---- Accounts, report, history, settings ----

def balance_line(account, with_limit: bool = True) -> str:
    if account.kind == "credit":
        line = f"• {account.name}: debt {money_text(-account.balance_minor, account.currency)}"
        if with_limit:
            line += f"; limit {money_text(account.credit_limit_minor, account.currency)}"
        return line
    return f"• {account.name}: {money_text(account.balance_minor, account.currency)}"


@dp.callback_query_handler(Text(equals="menu:accounts"), state="*")
async def show_accounts(call: types.CallbackQuery):
    await call.answer()
    await db.ensure_user(call.from_user.id, call.from_user.username)
    accounts = await db.list_accounts(call.from_user.id)
    lines = ["Your accounts:"] + [balance_line(a) for a in accounts]
    lines.append("\nManaging accounts and credit limits is the next step.")
    await call.message.edit_text("\n".join(lines), reply_markup=kb.main_menu())


@dp.callback_query_handler(Text(equals="menu:report"), state="*")
async def show_report(call: types.CallbackQuery):
    await call.answer()
    await db.ensure_user(call.from_user.id, call.from_user.username)
    report = await db.build_report(call.from_user.id)

    lines = [f"Report from {report.start.strftime('%d.%m.%Y')} to today", ""]
    for currency in db.CURRENCIES:
        income = report.totals.get(("income", currency), 0)
        expense = report.totals.get(("expense", currency), 0)
        if income or expense:
            lines.append(f"{currency}: income {money_text(income, currency)} · "
                         f"expenses {money_text(expense, currency)} · "
                         f"balance {money_text(income - expense, currency)}")
    lines += ["", "Balances:"] + [balance_line(a, with_limit=False) for a in report.accounts]
    if report.usd_rate:
        lines += ["", f"Current rate: 1 USD = {report.usd_rate} UZS"]
    else:
        lines += ["", "To see one total in UZS, set the rate: /rate 1 USD 12700 UZS"]
    await call.message.edit_text("\n".join(lines), reply_markup=kb.main_menu())


@dp.callback_query_handler(Text(equals="menu:history"), state="*")
async def show_history(call: types.CallbackQuery):
    await call.answer()
    await db.ensure_user(call.from_user.id, call.from_user.username)
    rows = await db.recent_transactions(call.from_user.id)
    if not rows:
        await call.message.edit_text("No operations yet.", reply_markup=kb.main_menu())
        return
    lines = ["Last 10 operations:"]
    for tx, account_name in rows:
        sign = "−" if tx.kind == "expense" else "+"
        lines.append(f"{sign}{money_text(tx.amount_minor, tx.currency)} · {tx.category or 'Transfer'} · {account_name}")
    await call.message.edit_text("\n".join(lines), reply_markup=kb.main_menu())


@dp.callback_query_handler(Text(equals="menu:settings"), state="*")
async def show_settings(call: types.CallbackQuery):
    await call.answer()
    await call.message.edit_text(
        "Settings:\n/salaryday 5 — salary day\n/rate 1 USD 12700 UZS — exchange rate\n\n"
        "Next we will add management of accounts, limits and categories.",
        reply_markup=kb.main_menu())
