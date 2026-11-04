from aiogram import types

from keyboards.default.menu import main_keyboard
from loader import dp
from utils.i18n import t


# Anything not handled elsewhere: show how to add an operation and the reply keyboard
@dp.message_handler(state=None, content_types=types.ContentTypes.ANY)
async def bot_fallback(message: types.Message, lang: str):
    await message.answer(t("use_menu", lang), reply_markup=main_keyboard(lang))


# A button of a removed menu (e.g. the old inline main menu still in the chat history)
@dp.callback_query_handler(state="*")
async def stale_button(call: types.CallbackQuery, lang: str):
    await call.answer()
    await call.message.answer(t("use_menu", lang), reply_markup=main_keyboard(lang))
