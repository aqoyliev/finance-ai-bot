from aiogram import types

from utils.i18n import LANGUAGES, t

COMMANDS = ("start", "salaryday", "rate", "help")


async def set_default_commands(dp):
    # Default list (English) plus one per supported Telegram client language
    for lang in (None,) + LANGUAGES:
        commands = [types.BotCommand(name, t(f"cmd_{name}", lang or "en")) for name in COMMANDS]
        await dp.bot.set_my_commands(commands, language_code=lang)
