"""The persistent reply keyboard under the input field: Report, Balance, Settings."""
from typing import Callable, List, Optional

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


def normalize(text: Optional[str]) -> str:
    """Lower-case letters and digits only: "⚙️ Sozlamalar" -> "sozlamalar", "📊 Отчёт" -> "отчет"."""
    text = (text or "").lower().replace("ё", "е")
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def is_menu_text(key: str) -> Callable:
    """Filter: the text is the button label or its plain word, in any language, any case, with or without emoji."""
    words = {normalize(label) for label in labels(key)}
    return lambda message: normalize(message.text) in words
