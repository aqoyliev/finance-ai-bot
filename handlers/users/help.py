from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandHelp

from keyboards.inline import app as kb
from loader import dp
from utils.i18n import t


@dp.message_handler(CommandHelp(), state="*")
async def bot_help(message: types.Message, lang: str):
    await message.answer(t("help", lang), reply_markup=kb.open_app(lang))
