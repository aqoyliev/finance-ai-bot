"""The persistent reply keyboard under the input field: Report, Balance, Settings."""
from typing import List

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from utils.i18n import LANGUAGES, t

MENU_KEYS = ("kb_report", "kb_balance", "kb_settings")


def main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(t(key, lang)) for key in MENU_KEYS]],
        resize_keyboard=True, is_persistent=True)


def labels(key: str) -> List[str]:
    """The button text in every language, so an old keyboard still works after a language change."""
    return [t(key, lang) for lang in LANGUAGES]
