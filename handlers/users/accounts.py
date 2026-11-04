from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import accounts as acc_kb
from keyboards.inline import finance as kb
from loader import dp
from states.finance import AccountEdit, AccountForm
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import parse_amount
from utils.misc.texts import account_details, balance_line

from .finance import session_lost


def account_id_of(call: types.CallbackQuery) -> int:
    return int(call.data.split(":")[2])


async def render_list(message: types.Message, user_id: int, lang: str, edit: bool = True):
    accounts = await db.list_accounts(user_id)
    lines = [t("accounts_title", lang)] + [balance_line(a, lang) for a in accounts]
    if not accounts:
        lines.append(t("accounts_empty", lang))
    send = message.edit_text if edit else message.answer
    await send("\n".join(lines), reply_markup=acc_kb.account_list(accounts, lang))


async def render_account(message: types.Message, account, lang: str, edit: bool = True, notice: str = ""):
    text = account_details(account, lang)
    if notice:
        text = f"{notice}\n\n{text}"
    send = message.edit_text if edit else message.answer
    await send(text, reply_markup=acc_kb.account_actions(account, lang))


@dp.callback_query_handler(Text(equals="menu:accounts"), state="*")
async def show_accounts(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await render_list(call.message, call.from_user.id, lang)


@dp.callback_query_handler(Text(startswith="acs:view:"), state="*")
async def show_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    account = await db.get_account(call.from_user.id, account_id_of(call))
    if account is None:
        await render_list(call.message, call.from_user.id, lang)
        return
    await render_account(call.message, account, lang)


# ---- Add an account: name -> kind -> currency -> opening balance (or limit + debt) ----

@dp.callback_query_handler(Text(equals="acs:add"), state="*")
async def add_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await AccountForm.name.set()
    await call.message.edit_text(t("ask_account_name", lang), reply_markup=kb.amount_prompt(lang, quick=False))


@dp.message_handler(state=AccountForm.name)
async def new_account_name(message: types.Message, state: FSMContext, lang: str):
    name = " ".join((message.text or "").split())
    if not name or len(name) > 40:
        await message.answer(t("bad_account_name", lang))
        return
    await state.update_data(new_name=name)
    await state.reset_state(with_data=False)
    await message.answer(t("ask_account_kind", lang), reply_markup=acc_kb.account_kinds(lang))


@dp.callback_query_handler(Text(startswith="nakind:"), state="*")
async def new_account_kind(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    kind = call.data.split(":")[1]
    if kind not in db.ACCOUNT_KINDS or "new_name" not in await state.get_data():
        await session_lost(call, state, lang)
        return
    await state.update_data(new_kind=kind)
    await call.message.edit_text(t("ask_account_currency", lang), reply_markup=kb.currencies(lang, "nacur"))


@dp.callback_query_handler(Text(startswith="nacur:"), state="*")
async def new_account_currency(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    currency = call.data.split(":")[1]
    data = await state.get_data()
    if currency not in db.CURRENCIES or "new_kind" not in data:
        await session_lost(call, state, lang)
        return
    await state.update_data(new_currency=currency)
    if data["new_kind"] == "credit":
        await AccountForm.limit.set()
        await call.message.edit_text(t("ask_credit_limit", lang), reply_markup=kb.amount_prompt(lang, quick=False))
    else:
        await AccountForm.opening.set()
        await call.message.edit_text(t("ask_opening_balance", lang),
                                     reply_markup=kb.amount_prompt(lang, quick=False))


@dp.message_handler(state=AccountForm.limit)
async def new_account_limit(message: types.Message, state: FSMContext, lang: str):
    limit = parse_amount(message.text or "", allow_zero=True)
    if limit is None:
        await message.answer(t("bad_amount_zero", lang))
        return
    await state.update_data(new_limit=limit)
    await AccountForm.debt.set()
    await message.answer(t("ask_current_debt", lang), reply_markup=kb.amount_prompt(lang, quick=False))


async def create_from_form(message: types.Message, state: FSMContext, lang: str, opening: int):
    data = await state.get_data()
    await state.finish()
    try:
        account = await db.create_account(message.from_user.id, data["new_name"], data["new_kind"],
                                          data["new_currency"], opening, data.get("new_limit", 0))
    except (KeyError, db.FinanceError):
        await message.answer(t("session_lost", lang))
        return
    await render_account(message, account, lang, edit=False, notice=t("account_created", lang))


@dp.message_handler(state=AccountForm.debt)
async def new_account_debt(message: types.Message, state: FSMContext, lang: str):
    debt = parse_amount(message.text or "", allow_zero=True)
    if debt is None:
        await message.answer(t("bad_amount_zero", lang))
        return
    await create_from_form(message, state, lang, -debt)  # debt is stored as a negative balance


@dp.message_handler(state=AccountForm.opening)
async def new_account_opening(message: types.Message, state: FSMContext, lang: str):
    opening = parse_amount(message.text or "", allow_zero=True)
    if opening is None:
        await message.answer(t("bad_amount_zero", lang))
        return
    await create_from_form(message, state, lang, opening)


# ---- Edit ----

EDIT_PROMPTS = {"ren": (AccountEdit.name, "ask_new_name"),
                "open": (AccountEdit.opening, "ask_new_opening"),
                "lim": (AccountEdit.limit, "ask_new_limit")}


@dp.callback_query_handler(Text(startswith=["acs:ren:", "acs:open:", "acs:lim:"]), state="*")
async def edit_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    account = await db.get_account(call.from_user.id, account_id_of(call))
    if account is None:
        await render_list(call.message, call.from_user.id, lang)
        return
    form_state, key = EDIT_PROMPTS[call.data.split(":")[1]]
    if form_state is AccountEdit.opening and account.kind == "credit":
        key = "ask_new_opening_debt"
    await state.update_data(edit_account=account.id)
    await form_state.set()
    await call.message.edit_text(t(key, lang, name=account.name), reply_markup=kb.amount_prompt(lang, quick=False))


async def finish_edit(message: types.Message, state: FSMContext, lang: str, change):
    """Run change(user_id, account_id) and show the updated account."""
    account_id = (await state.get_data()).get("edit_account")
    await state.finish()
    try:
        account = await change(message.from_user.id, account_id)
    except db.FinanceError:
        await message.answer(t("account_not_found", lang))
        return
    await render_account(message, account, lang, edit=False, notice=t("account_updated", lang))


@dp.message_handler(state=AccountEdit.name)
async def edit_name(message: types.Message, state: FSMContext, lang: str):
    name = " ".join((message.text or "").split())
    if not name or len(name) > 40:
        await message.answer(t("bad_account_name", lang))
        return
    await finish_edit(message, state, lang, lambda uid, aid: db.rename_account(uid, aid, name))


@dp.message_handler(state=AccountEdit.opening)
async def edit_opening(message: types.Message, state: FSMContext, lang: str):
    value = parse_amount(message.text or "", allow_zero=True)
    if value is None:
        await message.answer(t("bad_amount_zero", lang))
        return
    account = await db.get_account(message.from_user.id, (await state.get_data()).get("edit_account") or 0)
    # For a credit account the user enters the opening debt, stored as a negative balance
    opening = -value if account is not None and account.kind == "credit" else value
    await finish_edit(message, state, lang, lambda uid, aid: db.set_opening_balance(uid, aid, opening))


@dp.message_handler(state=AccountEdit.limit)
async def edit_limit(message: types.Message, state: FSMContext, lang: str):
    value = parse_amount(message.text or "", allow_zero=True)
    if value is None:
        await message.answer(t("bad_amount_zero", lang))
        return
    await finish_edit(message, state, lang, lambda uid, aid: db.set_credit_limit(uid, aid, value))


# ---- Deactivate ----

@dp.callback_query_handler(Text(startswith="acs:off:"), state="*")
async def ask_deactivate(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    account = await db.get_account(call.from_user.id, account_id_of(call))
    if account is None:
        await render_list(call.message, call.from_user.id, lang)
        return
    text = f"{balance_line(account, lang, with_limit=False)}\n\n{t('confirm_deactivate', lang)}"
    await call.message.edit_text(text, reply_markup=acc_kb.confirm_deactivate(account.id, lang))


@dp.callback_query_handler(Text(startswith="acs:offok:"), state="*")
async def deactivate(call: types.CallbackQuery, lang: str):
    try:
        account = await db.deactivate_account(call.from_user.id, account_id_of(call))
    except db.AccountNotFound:
        await call.answer()
        await render_list(call.message, call.from_user.id, lang)
        return
    await call.answer(t("account_deactivated", lang, name=account.name, _escape=False), show_alert=True)
    await render_list(call.message, call.from_user.id, lang)
