"""The Mini App web server, run inside the bot process next to long polling.

start() is called from on_startup in app.py, stop() from on_shutdown. A server that cannot start (e.g. the
port is taken) is logged and skipped, so the bot keeps working without the Mini App.
"""
import logging
from typing import Iterable, Optional

from aiogram import Bot
from aiogram.types import MenuButtonDefault, MenuButtonWebApp, WebAppInfo
from aiohttp import web

from data import config
from utils.db_api import finance as db
from utils.i18n import t

from .api import create_app

log = logging.getLogger(__name__)
_runner: Optional[web.AppRunner] = None


async def start(bot_token: str, allowed_ids: Iterable[int], host: str, port: int) -> None:
    global _runner
    runner = web.AppRunner(create_app(bot_token, allowed_ids), access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, host, port).start()
    except OSError:
        log.exception("Mini App web server could not listen on %s:%s; the bot runs without it", host, port)
        await runner.cleanup()
        return
    _runner = runner
    log.info("Mini App web server listening on %s:%s", host, port)


async def stop() -> None:
    global _runner
    if _runner is not None:
        await _runner.cleanup()
        _runner = None


async def set_menu_buttons(bot: Bot, allowed_ids: Iterable[int]) -> None:
    """The chat menu button of every admin opens the Mini App's Home (or is reset when WEBAPP_URL is not set)."""
    if config.WEBAPP_URL and not config.WEBAPP_ENABLED:
        log.warning("WEBAPP_URL must start with https:// for Telegram; Mini App buttons are off")
    for user_id in allowed_ids:
        try:
            if config.WEBAPP_ENABLED:
                lang = await db.get_language(user_id)
                button = MenuButtonWebApp(text=t("menu_miniapp", lang, _escape=False),
                                          web_app=WebAppInfo(url=config.WEBAPP_URL))
            else:
                button = MenuButtonDefault()
            await bot.set_chat_menu_button(chat_id=user_id, menu_button=button)
        except Exception:  # noqa: BLE001  e.g. the admin never opened a chat with the bot
            log.warning("Could not set the Mini App menu button for %s", user_id, exc_info=True)
