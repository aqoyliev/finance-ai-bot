from aiogram import types

from keyboards.inline import finance as kb
from loader import dp
from utils.i18n import t


# Anything not handled elsewhere: point the user back to the menu
@dp.message_handler(state=None, content_types=types.ContentTypes.ANY)
async def bot_fallback(message: types.Message, lang: str):
    await message.answer(t("use_menu", lang), reply_markup=kb.main_menu(lang))
