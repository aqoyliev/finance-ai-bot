from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.builtin import CommandStart

from keyboards.inline import finance as kb
from loader import dp
from utils.db_api import finance as db


@dp.message_handler(CommandStart(), state="*")
async def bot_start(message: types.Message, state: FSMContext):
    await state.finish()
    await db.ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "FINANCE BOT\n\nChoose an action. Set your salary day: /salaryday 5\n"
        "Set the USD rate: /rate 1 USD 12700 UZS",
        reply_markup=kb.main_menu())
