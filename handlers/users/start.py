"""/start: language choice on the first contact, then a short "what to do" text with the Mini App button.

The old persistent reply keyboard (📊 Report, 💳 Balance, ⚙️ Settings) is gone: every /start removes it, so chats
that still show it lose it.
"""
import contextlib

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.exceptions import TelegramAPIError

from keyboards.inline import app as kb
from loader import dp
from utils.db_api import finance as db
from utils.i18n import LANGUAGES, t


async def send_start(message: types.Message, lang: str, key: str = "start") -> None:
    """The start text. It is sent with ReplyKeyboardRemove (the old menu disappears), then the Mini App button is
    attached to it; if Telegram refuses that edit, the button follows in a short second message."""
    sent = await message.answer(t(key, lang), reply_markup=ReplyKeyboardRemove())
    markup = kb.open_app(lang)
    if markup is None:
        return
    try:
        await sent.edit_reply_markup(markup)
    except TelegramAPIError:
        await message.answer(t("open_app_hint", lang), reply_markup=markup)


@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state: FSMContext, lang: str):
    await state.finish()
    if await db.get_language(message.from_user.id) is None:
        # First contact: the language decides how starter accounts and categories are named
        await message.answer(t("choose_language", lang), reply_markup=kb.languages())
        return
    await send_start(message, lang)


@dp.callback_query_handler(Text(startswith="lang:"), state="*")
async def choose_language(call: types.CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    if lang not in LANGUAGES:
        await call.answer()
        return
    seeded = await db.set_language(call.from_user.id, call.from_user.username, lang)
    await call.answer()
    await state.finish()
    with contextlib.suppress(TelegramAPIError):
        await call.message.delete()
    await send_start(call.message, lang, "start" if seeded else "language_changed")
