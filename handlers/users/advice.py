"""AI advice: Settings -> AI advice (weekly / monthly toggles) and the manual "Get advice now" button.

The automatic weekly and monthly advice is sent by utils/advice_scheduler.py. Both send the advice with its
receipt card (the running-period report card for "Get advice now").
"""
import contextlib
import logging

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import TelegramAPIError

from keyboards.inline import ai as ai_kb
from loader import dp
from utils import cards
from utils.advice_scheduler import advice_header, advice_message, send_advice
from utils.ai import assistant, claude
from utils.db_api import finance as db
from utils.i18n import t

from .ai_common import error_text, typing

log = logging.getLogger(__name__)


def settings_text(user, lang: str) -> str:
    def status(on: bool) -> str:
        return t("advice_on" if on else "advice_off", lang)

    return t("advice_settings", lang, weekly=status(user.advice_weekly), monthly=status(user.advice_monthly),
             salary_day=user.salary_day)


@dp.callback_query_handler(Text(equals="set:advice"), state="*")
async def show_advice_settings(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    user = await db.get_user(call.from_user.id)
    await call.message.edit_text(settings_text(user, lang), reply_markup=ai_kb.advice_settings(user, lang))


@dp.callback_query_handler(Text(startswith="adv:toggle:"), state="*")
async def toggle(call: types.CallbackQuery, lang: str):
    kind = call.data.split(":")[2]
    if kind not in db.ADVICE_KINDS:
        await call.answer()
        return
    user = await db.toggle_advice(call.from_user.id, kind)
    await call.answer()
    await call.message.edit_text(settings_text(user, lang), reply_markup=ai_kb.advice_settings(user, lang))


@dp.callback_query_handler(Text(equals="ask:advice"), state="*")
async def advice_now(call: types.CallbackQuery, lang: str):
    """Advice on the running period, sent as a new message (the screen it was asked from stays)."""
    await call.answer()
    client = claude.get_client()
    if not client.configured:
        await call.message.answer(t("ai_not_configured", lang))
        return
    status = await call.message.answer(t("advice_preparing", lang))
    try:
        async with typing(call.message.chat.id):
            result = await assistant.advice(call.from_user.id, "now", lang, client=client)
    except claude.AIError as err:
        log.info("Advice failed: %s", err)
        await status.edit_text(error_text(err.code, lang, prefix="ask_error_"))
        return
    if result is None:
        await status.edit_text(t("advice_no_data", lang))
        return
    text, markup = advice_message(result, "now", lang), ai_kb.after_advice(lang)
    card = await cards.advice_card(call.from_user.id, "now", lang)
    if card is None:
        await status.edit_text(text, reply_markup=markup)
        return
    with contextlib.suppress(TelegramAPIError):
        await status.delete()
    await send_advice(call.message.chat.id, text, advice_header(result, "now", lang), card, markup)
