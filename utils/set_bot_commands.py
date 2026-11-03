from aiogram import types


async def set_default_commands(dp):
    await dp.bot.set_my_commands(
        [
            types.BotCommand("start", "Open the main menu"),
            types.BotCommand("salaryday", "Set salary day, e.g. /salaryday 5"),
            types.BotCommand("rate", "Set USD rate, e.g. /rate 1 USD 12700 UZS"),
            types.BotCommand("help", "Help"),
        ]
    )
