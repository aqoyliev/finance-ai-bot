import asyncio
import logging

from aiogram import executor

from loader import dp
import middlewares, filters, handlers
from utils import cards
from utils.advice_scheduler import scheduler
from utils.db_api.base import init_db
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

    # Weekly / monthly AI advice (also sends advice missed today while the bot was down)
    scheduler.start()


async def on_shutdown(dispatcher):
    await scheduler.stop()
    # The headless Chromium of the report cards (started on the first card)
    await cards.close_renderer()


if __name__ == '__main__':
    # Newer uvloop (used by aiogram 2 in Docker) no longer creates a loop implicitly, so set one explicitly
    asyncio.set_event_loop(asyncio.new_event_loop())
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
