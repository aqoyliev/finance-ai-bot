import logging
from typing import Optional, Set

from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware

from utils.i18n import guess_language, t

# Update fields that carry the acting user (as .from_user or .user)
USER_FIELDS = ("message", "edited_message", "callback_query", "inline_query", "chosen_inline_result",
               "shipping_query", "pre_checkout_query", "poll_answer", "my_chat_member", "chat_member",
               "chat_join_request")


def update_user(update: types.Update) -> Optional[types.User]:
    for name in USER_FIELDS:
        obj = getattr(update, name, None)
        if obj is not None:
            return getattr(obj, "from_user", None) or getattr(obj, "user", None)
    return None


class AccessMiddleware(BaseMiddleware):
    """Private bot: only users listed in ADMINS get through; others get one short notice."""

    def __init__(self, allowed_ids: Set[int]):
        self.allowed_ids = allowed_ids
        self.notified: Set[int] = set()
        super().__init__()

    async def on_pre_process_update(self, update: types.Update, data: dict):
        user = update_user(update)
        if user is not None and user.id in self.allowed_ids:
            return
        if user is not None and user.id not in self.notified and (update.message or update.callback_query):
            self.notified.add(user.id)
            logging.info("Ignoring user %s: not in ADMINS", user.id)
            await self.notify(update, t("private_bot", guess_language(user.language_code)))
        elif update.callback_query:
            await update.callback_query.answer()
        raise CancelHandler()

    @staticmethod
    async def notify(update: types.Update, text: str):
        try:
            if update.message:
                await update.message.answer(text)
            else:
                await update.callback_query.answer(text, show_alert=True)
        except Exception as err:  # never let a stranger's update break the bot
            logging.warning("Could not notify unauthorized user: %s", err)
