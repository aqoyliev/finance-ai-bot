"""Bot messages of the access flow (utils/db_api/access.py): "somebody wants in" to the managers, "you have access"
to a newly granted user, the contact picker keyboard and the chat menu button of a granted / revoked user.

Every function takes the Bot explicitly (the Mini App server and the middleware pass theirs) and never raises:
a failed Telegram call is logged and skipped.
"""
import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonDefault

from keyboards.inline import app as app_kb
from utils.db_api import access
from utils.db_api import finance as db
from utils.i18n import guess_language, t

log = logging.getLogger(__name__)

GRANT_PREFIX = "acc:grant:"
PICK_REQUEST_ID = 4207  # request_id of the "pick a contact" button (any int32)


async def language_of(user_id: int, language_code: Optional[str] = None) -> str:
    """The chosen language of a user, else a guess from their Telegram client (stored on the visitor row)."""
    lang = await db.get_language(user_id)
    if lang:
        return lang
    if not language_code:
        visitor = await access.get_visitor(user_id)
        language_code = visitor.language_code if visitor else None
    return guess_language(language_code)


def grant_keyboard(user_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(t("btn_grant", lang, _escape=False), callback_data=f"{GRANT_PREFIX}{user_id}")]])


def picker_keyboard(lang: str) -> dict:
    """One-time reply keyboard with a request_users button (Bot API 7; aiogram 2 has no type for it)."""
    return {
        "keyboard": [
            [{"text": t("picker_btn", lang, _escape=False),
              "request_users": {"request_id": PICK_REQUEST_ID, "user_is_bot": False, "max_quantity": 1,
                                "request_name": True, "request_username": True}}],
            [{"text": t("picker_cancel", lang, _escape=False)}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


async def notify_managers(bot: Bot, user_id: int, username: Optional[str], name: str) -> int:
    """Tell every owner and superadmin that an unknown person wrote to the bot. Returns how many got it."""
    sent = 0
    for manager in access.manager_ids():
        lang = await language_of(manager)
        login = f"@{username}" if username else t("no_username", lang, _escape=False)
        try:
            await bot.send_message(manager, t("visitor_knocks", lang, name=name or str(user_id), username=login),
                                   reply_markup=grant_keyboard(user_id, lang))
            sent += 1
        except Exception:  # noqa: BLE001  e.g. the manager never opened the bot
            log.warning("Could not tell %s about a new visitor", manager, exc_info=True)
    return sent


async def notify_granted(bot: Bot, user_id: int) -> None:
    """"You have access" with the Mini App button, and the chat menu button that opens the Mini App."""
    from utils.miniapp.server import set_menu_button

    lang = await language_of(user_id)
    try:
        await bot.send_message(user_id, t("access_granted", lang), reply_markup=app_kb.open_app(lang))
    except Exception:  # noqa: BLE001  the person may have blocked the bot
        log.warning("Could not tell %s about the new access", user_id, exc_info=True)
    await set_menu_button(bot, user_id, lang)


async def reset_menu_button(bot: Bot, user_id: Optional[int]) -> None:
    if user_id is None:
        return
    try:
        await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonDefault())
    except Exception:  # noqa: BLE001
        log.warning("Could not reset the menu button of %s", user_id, exc_info=True)


async def send_picker(bot: Bot, chat_id: int) -> None:
    """The contact picker keyboard in the manager's chat (raises if Telegram refuses, so the API can say so)."""
    lang = await language_of(chat_id)
    await bot.send_message(chat_id, t("picker_prompt", lang), reply_markup=picker_keyboard(lang))
