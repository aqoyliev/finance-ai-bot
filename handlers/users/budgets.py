"""Settings -> Budgets: a monthly limit per expense category."""
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import reports as kb
from loader import dp
from states.finance import BudgetForm
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import money_text, parse_amount
from utils.misc.texts import progress_bar

from .finance import session_lost


def ids_of(call: types.CallbackQuery) -> list:
    return call.data.split(":")[2:]


async def render_list(message: types.Message, user_id: int, lang: str, edit: bool = True, notice: str = ""):
    categories = await db.list_categories(user_id, "expense")
    budgets = await db.list_budgets(user_id)
    labels = {c.name: t("budget_button", lang, _escape=False, category=c.name, limit=(
        money_text(budgets[c.name].amount_minor, budgets[c.name].currency) if c.name in budgets
        else t("budget_not_set", lang))) for c in categories}
    text = t("budgets_title", lang)
    if notice:
        text = f"{notice}\n\n{text}"
    send = message.edit_text if edit else message.answer
    await send(text, reply_markup=kb.budget_categories(categories, labels, lang))


async def render_category(message: types.Message, user_id: int, category, lang: str, edit: bool = True,
                          notice: str = ""):
    usage = next((u for u in await db.budget_usages(user_id) if u.category == category.name), None)
    if usage:
        text = t("budget_details", lang, category=category.name, limit=money_text(usage.limit, usage.currency),
                 spent=money_text(usage.spent, usage.currency), percent=str(usage.percent),
                 bar=progress_bar(usage.percent))
    else:
        text = t("budget_details_none", lang, category=category.name)
    if notice:
        text = f"{notice}\n\n{text}"
    send = message.edit_text if edit else message.answer
    await send(text, reply_markup=kb.budget_actions(category.id, usage is not None, lang))


async def category_of(call: types.CallbackQuery):
    return await db.get_category(call.from_user.id, int(ids_of(call)[0]))


@dp.callback_query_handler(Text(equals="bud:list"), state="*")
async def show_budgets(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await render_list(call.message, call.from_user.id, lang)


@dp.callback_query_handler(Text(startswith="bud:cat:"), state="*")
async def show_budget(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    category = await category_of(call)
    if category is None:
        await render_list(call.message, call.from_user.id, lang)
        return
    await render_category(call.message, call.from_user.id, category, lang)


@dp.callback_query_handler(Text(startswith="bud:set:"), state="*")
async def ask_currency(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    category = await category_of(call)
    if category is None:
        await render_list(call.message, call.from_user.id, lang)
        return
    await call.message.edit_text(t("budget_ask_currency", lang, category=category.name),
                                 reply_markup=kb.budget_currencies(category.id, lang))


@dp.callback_query_handler(Text(startswith="bud:cur:"), state="*")
async def ask_amount(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    category, currency = await category_of(call), ids_of(call)[1]
    if category is None or currency not in db.CURRENCIES:
        await render_list(call.message, call.from_user.id, lang)
        return
    await state.update_data(budget_category=category.id, budget_currency=currency)
    await BudgetForm.amount.set()
    await call.message.edit_text(t("budget_ask_amount", lang, category=category.name, currency=currency),
                                 reply_markup=kb.budget_amount_prompt(category.id, lang))


@dp.message_handler(state=BudgetForm.amount)
async def typed_limit(message: types.Message, state: FSMContext, lang: str):
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(t("bad_amount", lang))
        return
    data = await state.get_data()
    await state.finish()
    category = await db.get_category(message.from_user.id, data.get("budget_category") or 0)
    if category is None or data.get("budget_currency") not in db.CURRENCIES:
        await message.answer(t("session_lost", lang))
        return
    await db.set_budget(message.from_user.id, category.name, data["budget_currency"], amount)
    await render_category(message, message.from_user.id, category, lang, edit=False,
                          notice=t("budget_saved", lang))


@dp.callback_query_handler(Text(startswith="bud:del:"), state="*")
async def remove(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    category = await category_of(call)
    if category is None:
        await session_lost(call, state, lang)
        return
    await db.remove_budget(call.from_user.id, category.name)
    await render_list(call.message, call.from_user.id, lang, notice=t("budget_removed", lang))
