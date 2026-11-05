import asyncio
import logging

from aiogram import executor

from data import config
from loader import dp
import middlewares, filters, handlers
from utils import cards
from utils.advice_scheduler import scheduler
from utils.db_api.base import init_db
from utils.miniapp import server as miniapp
from utils.rates import updater as rate_updater
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands


async def on_startup(dispatcher):
    # Apply database migrations (alembic upgrade head)
    await init_db()

    # Bot commands in every supported language
    await set_default_commands(dispatcher)

    # Notify admin that the bot has started
    await on_startup_notify(dispatcher)

    # The @username printed on report cards (the cards just leave it out if this fails)
    try:
        cards.set_bot_username((await dispatcher.bot.get_me()).username)
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Could not read the bot username for report cards", exc_info=True)

    # Official USD rate of the Central Bank: fetched now, then every 6 hours (a failure keeps the last value)
    rate_updater.start()

    # Weekly / monthly AI advice (also sends advice missed today while the bot was down)
    scheduler.start()

    # Mini App: web server on PORT (always) and the chat menu button of every owner, superadmin and granted
    # user (when WEBAPP_URL is set)
    await miniapp.start(config.BOT_TOKEN, config.WEBAPP_HOST, config.PORT, bot=dispatcher.bot)
    await miniapp.set_menu_buttons(dispatcher.bot)


async def on_shutdown(dispatcher):
    await scheduler.stop()
    await rate_updater.stop()
    await miniapp.stop()
    # The headless Chromium of the report cards (started on the first card)
    await cards.close_renderer()


if __name__ == '__main__':
    # Newer uvloop (used by aiogram 2 in Docker) no longer creates a loop implicitly, so set one explicitly
    asyncio.set_event_loop(asyncio.new_event_loop())
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
