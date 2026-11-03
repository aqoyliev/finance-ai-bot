from aiogram import executor

from loader import dp
import middlewares, filters, handlers
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

    # Weekly / monthly AI advice (also sends advice missed today while the bot was down)
    scheduler.start()


async def on_shutdown(dispatcher):
    await scheduler.stop()


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)
