"""Opening a recent operation from Settings -> History to edit or delete it."""
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import finance as kb
from keyboards.inline import operations as op_kb
from loader import dp
from states.finance import OperationEdit
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import parse_amount
from utils.misc.texts import balance_line, operation_details, over_limit_warning
from utils.notify_alerts import send_alerts

from .finance import Choice, session_lost


def tx_id_of(call: types.CallbackQuery) -> int:
    return int(call.data.split(":")[1])


async def load_view(user_id: int, tx_id: int):
    try:
        return await db.get_operation(user_id, tx_id)
    except db.FinanceError:
        return None


async def render_operation(message: types.Message, view, lang: str, edit: bool = True, notice: str = ""):
    text = operation_details(view, lang)
    if notice:
        text = f"{notice}\n\n{text}"
    send = message.edit_text if edit else message.answer
    await send(text, reply_markup=op_kb.operation_actions(view.tx.id, view.is_transfer, lang))


def saved_notice(saved, lang: str) -> str:
    """'Saved' plus new balances of the touched accounts and any credit limit warnings."""
    lines = [t("operation_updated", lang)] + [balance_line(a, lang) for a in saved.accounts]
    return "\n".join(lines + over_limit_warning(saved.over_limit, lang))


async def not_found(call: types.CallbackQuery, state: FSMContext, lang: str):
    await state.finish()
    await call.message.edit_text(t("operation_not_found", lang), reply_markup=op_kb.back_to_history(lang))


@dp.callback_query_handler(Text(startswith="opv:"), state="*")
async def show_operation(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    view = await load_view(call.from_user.id, tx_id_of(call))
    if view is None:
        await not_found(call, state, lang)
        return
    await render_operation(call.message, view, lang)


# ---- Amount ----

@dp.callback_query_handler(Text(startswith="opa:"), state="*")
async def ask_new_amount(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await state.update_data(edit_tx=tx_id_of(call))
    await OperationEdit.amount.set()
    await call.message.edit_text(t("ask_new_amount", lang), reply_markup=kb.amount_prompt(lang, quick=False))


@dp.message_handler(state=OperationEdit.amount)
async def new_amount(message: types.Message, state: FSMContext, lang: str):
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(t("bad_amount", lang))
        return
    tx_id = (await state.get_data()).get("edit_tx")
    await state.finish()
    try:
        saved = await db.update_amount(message.from_user.id, tx_id, amount)
    except db.FinanceError:
        await message.answer(t("operation_not_found", lang), reply_markup=op_kb.back_to_history(lang))
        return
    view = await db.get_operation(message.from_user.id, tx_id)
    await render_operation(message, view, lang, edit=False, notice=saved_notice(saved, lang))
    await send_alerts(message.from_user.id, lang, saved)


# ---- Category / subcategory ----

@dp.callback_query_handler(Text(startswith="opc:"), state="*")
async def ask_new_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    view = await load_view(call.from_user.id, tx_id_of(call))
    if view is None or view.is_transfer:
        await not_found(call, state, lang)
        return
    await state.update_data(edit_tx=view.tx.id, edit_kind=view.tx.kind)
    categories = await db.list_categories(call.from_user.id, view.tx.kind)
    await call.message.edit_text(t("ask_new_category", lang), reply_markup=kb.choices(categories, "opcat", lang))


async def apply_category(call: types.CallbackQuery, state: FSMContext, lang: str, subcategory):
    data = await state.get_data()
    await state.finish()
    try:
        tx = await db.update_category(call.from_user.id, data.get("edit_tx"), data.get("edit_category"), subcategory)
        view = await db.get_operation(call.from_user.id, data.get("edit_tx"))
    except db.FinanceError:
        await not_found(call, state, lang)
        return
    await render_operation(call.message, view, lang, notice=t("operation_updated", lang))
    await send_alerts(call.from_user.id, lang, db.SavedOperation(tx.group_id, [tx]))


@dp.callback_query_handler(Text(startswith="opcat:"), state="*")
async def new_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    data = await state.get_data()
    category = await db.get_category(call.from_user.id, int(call.data.split(":")[1]))
    if category is None or "edit_tx" not in data:
        await session_lost(call, state, lang)
        return
    await state.update_data(edit_category=category.name)
    if data.get("edit_kind") == "expense":
        subcategories = await db.list_subcategories(category.id)
        await call.message.edit_text(t("ask_subcategory", lang),
                                     reply_markup=kb.subcategories(subcategories, lang, "opsub"))
    else:
        await apply_category(call, state, lang, None)


@dp.callback_query_handler(Text(startswith="opsub:"), state="*")
async def new_subcategory(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if "edit_category" not in await state.get_data():
        await session_lost(call, state, lang)
        return
    subcategory_id = int(call.data.split(":")[1])
    subcategory = await db.get_subcategory(call.from_user.id, subcategory_id) if subcategory_id else None
    await apply_category(call, state, lang, subcategory.name if subcategory else None)


# ---- Account ----

@dp.callback_query_handler(Text(startswith="opk:"), state="*")
async def ask_new_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    view = await load_view(call.from_user.id, tx_id_of(call))
    if view is None or view.is_transfer:
        await not_found(call, state, lang)
        return
    accounts = await db.list_accounts(call.from_user.id, view.tx.currency)
    await state.update_data(edit_tx=view.tx.id)
    labels = [Choice(a.id, f"{a.name} ({a.currency})") for a in accounts]
    await call.message.edit_text(t("ask_new_account", lang, currency=view.tx.currency),
                                 reply_markup=kb.choices(labels, "opacc", lang))


@dp.callback_query_handler(Text(startswith="opacc:"), state="*")
async def new_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    tx_id = (await state.get_data()).get("edit_tx")
    await state.finish()
    if tx_id is None:
        await session_lost(call, state, lang)
        return
    try:
        saved = await db.update_account(call.from_user.id, tx_id, int(call.data.split(":")[1]))
        view = await db.get_operation(call.from_user.id, tx_id)
    except db.FinanceError:
        await not_found(call, state, lang)
        return
    await render_operation(call.message, view, lang, notice=saved_notice(saved, lang))
    await send_alerts(call.from_user.id, lang, saved)


# ---- Delete ----

@dp.callback_query_handler(Text(startswith="opd:"), state="*")
async def ask_delete(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    view = await load_view(call.from_user.id, tx_id_of(call))
    if view is None:
        await not_found(call, state, lang)
        return
    key = "confirm_delete_transfer" if view.is_transfer else "confirm_delete"
    await call.message.edit_text(f"{operation_details(view, lang)}\n\n{t(key, lang)}",
                                 reply_markup=op_kb.confirm_delete(view.tx.id, lang))


@dp.callback_query_handler(Text(startswith="opdy:"), state="*")
async def delete(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    try:
        accounts = await db.delete_operation(call.from_user.id, tx_id_of(call))
    except db.FinanceError:
        await not_found(call, state, lang)
        return
    lines = [t("operation_deleted", lang)] + [balance_line(a, lang) for a in accounts]
    await call.message.edit_text("\n".join(lines), reply_markup=op_kb.back_to_history(lang))
