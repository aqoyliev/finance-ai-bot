import logging
from typing import Awaitable, Callable, Optional, Set

from aiogram import Bot, types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware

from utils.db_api import access
from utils.i18n import guess_language, t

# Update fields that carry the acting user (as .from_user or .user)
USER_FIELDS = ("message", "edited_message", "callback_query", "inline_query", "chosen_inline_result",
               "shipping_query", "pre_checkout_query", "poll_answer", "my_chat_member", "chat_member",
               "chat_join_request")

# async (user) -> None: tells the owners / superadmins that an unknown person wrote to the bot
VisitorNotifier = Callable[[types.User], Awaitable[None]]


def update_user(update: types.Update) -> Optional[types.User]:
    for name in USER_FIELDS:
        obj = getattr(update, name, None)
        if obj is not None:
            return getattr(obj, "from_user", None) or getattr(obj, "user", None)
    return None


def is_private(update: types.Update) -> bool:
    """A message / button press / block-unblock in a private chat with the bot."""
    message = update.message or update.edited_message or (update.callback_query and update.callback_query.message)
    chat = message.chat if message else (update.my_chat_member.chat if update.my_chat_member else None)
    return chat is not None and chat.type == types.ChatType.PRIVATE


async def notify_managers(user: types.User) -> None:
    from utils import access_notify
    await access_notify.notify_managers(Bot.get_current(), user.id, user.username, user.full_name)


class AccessMiddleware(BaseMiddleware):
    """Private bot: owners (ADMINS), superadmins (SUPERADMINS) and users granted in the Mini App get through;
    others get one short notice, and the first time they show up the owners / superadmins get an "allow" button.

    Every private-chat user except the owners is recorded as a visitor (the Users screen lists them).
    """

    def __init__(self, notify_visitor: Optional[VisitorNotifier] = None):
        self.notified: Set[int] = set()
        self.notify_visitor = notify_visitor or notify_managers
        super().__init__()

    async def on_pre_process_update(self, update: types.Update, data: dict):
        user = update_user(update)
        if user is None:
            if update.callback_query:
                await update.callback_query.answer()
            raise CancelHandler()
        role = await access.role_of(user.id, user.username, user.full_name)
        private = is_private(update)
        if private:
            await self.record(user)
        if role is not None:
            return
        attempt = update.message or update.callback_query
        if user.id not in self.notified and attempt:
            self.notified.add(user.id)
            logging.info("Ignoring user %s: no access", user.id)
            await self.notify(update, t("private_bot", guess_language(user.language_code)))
        elif update.callback_query:
            await update.callback_query.answer()
        if private and attempt:
            await self.knock(user)
        raise CancelHandler()

    @staticmethod
    async def record(user: types.User) -> None:
        try:
            await access.touch_visitor(user.id, user.username, user.first_name, user.last_name, user.language_code)
        except Exception:  # noqa: BLE001  bookkeeping must never block the bot
            logging.exception("Could not record visitor %s", user.id)

    async def knock(self, user: types.User) -> None:
        """The first time an unknown person writes: the owners and superadmins get an "allow" button."""
        try:
            if await access.claim_notice(user.id):
                await self.notify_visitor(user)
        except Exception:  # noqa: BLE001
            logging.exception("Could not tell the managers about visitor %s", user.id)

    @staticmethod
    async def notify(update: types.Update, text: str):
        try:
            if update.message:
                await update.message.answer(text)
            else:
                await update.callback_query.answer(text, show_alert=True)
        except Exception as err:  # never let a stranger's update break the bot
            logging.warning("Could not notify unauthorized user: %s", err)
