"""Inline keyboards for AI advice (callback data prefixes 'adv:', 'ask:' and 'set:advice')."""
from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import t


def _button(key: str, data: str, lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(t(key, lang), callback_data=data)


def after_advice(lang: str, settings: bool = False) -> Optional[InlineKeyboardMarkup]:
    """Under an automatic advice: a way to its settings; the manual advice gets no buttons."""
    if not settings:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[_button("btn_ai_advice", "set:advice", lang)]])


def advice_settings(user, lang: str) -> InlineKeyboardMarkup:
    def toggle(kind: str, on: bool) -> InlineKeyboardButton:
        mark = "✅" if on else "⬜"
        return InlineKeyboardButton(f"{mark} {t(f'btn_advice_{kind}', lang)}", callback_data=f"adv:toggle:{kind}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [toggle("weekly", user.advice_weekly)],
        [toggle("monthly", user.advice_monthly)],
        [_button("btn_advice_now", "ask:advice", lang)],
        [_button("btn_back", "menu:settings", lang)],
    ])
