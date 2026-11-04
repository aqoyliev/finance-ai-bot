"""Manual transfer between own accounts (/transfer); a transfer to a credit card repays its debt."""
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text

from keyboards.inline import finance as kb
from loader import dp
from states.finance import TransferForm
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import parse_amount
from utils.misc.texts import operation_card, over_limit_warning
from utils.notify_alerts import send_alerts

from .finance import Choice, session_lost


def account_choices(accounts):
    return [Choice(a.id, f"{a.name} ({a.currency})") for a in accounts]


@dp.message_handler(Command("transfer"), state="*")
async def start_transfer(message: types.Message, state: FSMContext, lang: str):
    await state.finish()
    accounts = await db.list_accounts(message.from_user.id)
    if len(accounts) < 2:
        await message.answer(t("transfer_need_two", lang))
        return
    await message.answer(t("transfer_from", lang),
                         reply_markup=kb.choices(account_choices(accounts), "trf:from", lang))


@dp.callback_query_handler(Text(startswith="trf:from:"), state="*")
async def choose_source(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    source = await db.get_account(call.from_user.id, int(call.data.split(":")[2]))
    if source is None:
        await session_lost(call, state, lang)
        return
    # Only accounts of the same currency can receive the money
    targets = [a for a in await db.list_accounts(call.from_user.id, source.currency) if a.id != source.id]
    if not targets:
        await call.message.edit_text(t("transfer_no_target", lang, currency=source.currency))
        return
    await state.update_data(transfer_from=source.id)
    await call.message.edit_text(t("transfer_to", lang, name=source.name),
                                 reply_markup=kb.choices(account_choices(targets), "trf:to", lang))


@dp.callback_query_handler(Text(startswith="trf:to:"), state="*")
async def choose_target(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if "transfer_from" not in await state.get_data():
        await session_lost(call, state, lang)
        return
    await state.update_data(transfer_to=int(call.data.split(":")[2]))
    await TransferForm.amount.set()
    await call.message.edit_text(t("transfer_amount", lang), reply_markup=kb.amount_prompt(lang))


async def save_transfer(message: types.Message, state: FSMContext, lang: str, amount: int, user_id: int,
                        edit: bool):
    data = await state.get_data()
    await state.finish()
    send = message.edit_text if edit else message.answer
    try:
        saved = await db.record_transfer(user_id, data["transfer_from"], data["transfer_to"], amount)
    except (KeyError, db.FinanceError):
        await send(t("transfer_failed", lang))
        return
    await send("\n\n".join([operation_card(saved, lang)] + over_limit_warning(saved.over_limit, lang)))
    await send_alerts(user_id, lang, saved)


@dp.callback_query_handler(Text(startswith="quick:"), state=TransferForm.amount)
async def quick_transfer_amount(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await save_transfer(call.message, state, lang, parse_amount(call.data.split(":", 1)[1]),
                        call.from_user.id, edit=True)


@dp.message_handler(state=TransferForm.amount)
async def typed_transfer_amount(message: types.Message, state: FSMContext, lang: str):
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(t("bad_amount", lang))
        return
    await save_transfer(message, state, lang, amount, message.from_user.id, edit=False)
