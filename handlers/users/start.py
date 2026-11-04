import contextlib

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.dispatcher.filters.builtin import CommandStart
from aiogram.utils.exceptions import TelegramAPIError

from keyboards.default.menu import main_keyboard
from keyboards.inline import finance as kb
from loader import dp
from utils.db_api import finance as db
from utils.i18n import LANGUAGES, t


@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state: FSMContext, lang: str):
    await state.finish()
    if await db.get_language(message.from_user.id) is None:
        # First contact: the language decides how starter accounts and categories are named
        await message.answer(t("choose_language", lang), reply_markup=kb.languages())
        return
    await message.answer(t("start", lang), reply_markup=main_keyboard(lang))


@dp.callback_query_handler(Text(startswith="lang:"), state="*")
async def choose_language(call: types.CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    if lang not in LANGUAGES:
        await call.answer()
        return
    seeded = await db.set_language(call.from_user.id, call.from_user.username, lang)
    await call.answer()
    await state.finish()
    # A reply keyboard cannot be attached to an edited message: replace the picker with a new message
    with contextlib.suppress(TelegramAPIError):
        await call.message.delete()
    await call.message.answer(t("start" if seeded else "language_changed", lang), reply_markup=main_keyboard(lang))
