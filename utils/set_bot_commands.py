import logging

from aiogram import types
from aiogram.types import BotCommandScopeDefault

from utils.i18n import LANGUAGES, t

# Everything else (reports, balances, manual entry, settings) is in the Mini App
COMMANDS = ("start", "help")

log = logging.getLogger(__name__)


async def set_default_commands(dp):
    """Default list (English) plus one per supported Telegram client language.

    Earlier versions registered many more commands per language; they are deleted first for the default scope and
    every language code, so no stale command stays in a client's menu."""
    for lang in (None,) + LANGUAGES:
        try:
            await dp.bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code=lang)
        except Exception:  # noqa: BLE001  nothing to delete is fine; setting below still runs
            log.warning("Could not delete the old bot commands for %s", lang or "default", exc_info=True)
    for lang in (None,) + LANGUAGES:
        commands = [types.BotCommand(name, t(f"cmd_{name}", lang or "en")) for name in COMMANDS]
        await dp.bot.set_my_commands(commands, scope=BotCommandScopeDefault(), language_code=lang)
