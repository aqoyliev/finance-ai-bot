"""Inline keyboards of the chat: the language picker and the buttons that open the Mini App.

Everything except /start, /help, AI input and Ask AI lives in the Mini App now. Web App buttons are only
built when WEBAPP_URL is an https:// address (Telegram rejects any other), otherwise these return None.
"""
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from data import config
from utils.i18n import LANGUAGE_NAMES, t

# Mini App routes (webapp/app.js)
HOME = ""
NEW_CARD = "#/new"
SETTINGS = "#/settings"


def languages() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(name, callback_data=f"lang:{code}")] for code, name in LANGUAGE_NAMES.items()
    ])


def app_button(text: str, route: str = HOME) -> Optional[InlineKeyboardButton]:
    if not config.WEBAPP_ENABLED:
        return None
    return InlineKeyboardButton(text, web_app=WebAppInfo(url=config.WEBAPP_URL.rstrip("/") + "/" + route))


def open_app(lang: str, route: str = HOME, key: str = "btn_open_app") -> Optional[InlineKeyboardMarkup]:
    """One "📱 Open the app" button, or None without a Mini App."""
    button = app_button(t(key, lang, _escape=False), route)
    return InlineKeyboardMarkup(inline_keyboard=[[button]]) if button else None
