from aiogram import types
from aiogram.dispatcher.filters.builtin import CommandHelp

from loader import dp


@dp.message_handler(CommandHelp())
async def bot_help(message: types.Message):
    text = ("Commands: ",
            "/start - Open the main menu",
            "/salaryday 5 - Set the day your financial month starts",
            "/rate 1 USD 12700 UZS - Set the USD to UZS rate",
            "/help - Help")
    
    await message.answer("\n".join(text))
