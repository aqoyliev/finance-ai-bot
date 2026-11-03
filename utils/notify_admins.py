import logging

from aiogram import Dispatcher

from data.config import ADMINS
from utils.db_api.finance import get_language
from utils.i18n import t


async def on_startup_notify(dp: Dispatcher):
    for admin in ADMINS:
        try:
            await dp.bot.send_message(admin, t("bot_started", await get_language(int(admin))))

        except Exception as err:
            logging.exception(err)
