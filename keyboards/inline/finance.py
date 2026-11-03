from typing import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.db_api.common import CURRENCIES
from utils.i18n import LANGUAGE_NAMES, t

QUICK_AMOUNTS = ("5000", "10000", "20000", "50000", "100000")


def cancel_button(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_cancel", lang), callback_data="cancel")


def back_button(lang: str, callback_data: str = "menu:main") -> InlineKeyboardButton:
    return InlineKeyboardButton(t("btn_back", lang), callback_data=callback_data)


def languages() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(name, callback_data=f"lang:{code}")] for code, name in LANGUAGE_NAMES.items()
    ])


def main_menu(lang: str) -> InlineKeyboardMarkup:
    def button(key: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(t(key, lang), callback_data=f"menu:{action}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [button("btn_expense", "expense"), button("btn_income", "income")],
        [button("btn_transfer", "transfer"), button("btn_accounts", "accounts")],
        [button("btn_report", "report"), button("btn_history", "history")],
        [button("btn_ask_ai", "ask"), button("btn_settings", "settings")],
    ])


def back_to_menu(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(lang)]])


def choices(items: Iterable, prefix: str, lang: str,
            extra: Iterable[InlineKeyboardButton] = ()) -> InlineKeyboardMarkup:
    """One button per item (objects with .id and .name); callback data is '<prefix>:<id>'."""
    rows = [[InlineKeyboardButton(item.name, callback_data=f"{prefix}:{item.id}")] for item in items]
    rows.extend([button] for button in extra)
    rows.append([cancel_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategories(items: Iterable, lang: str, prefix: str = "sub") -> InlineKeyboardMarkup:
    none_button = InlineKeyboardButton(t("btn_no_subcategory", lang), callback_data=f"{prefix}:0")
    return choices(items, prefix, lang, extra=[none_button])


def amount_prompt(lang: str, quick: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if quick:
        buttons = [InlineKeyboardButton(x, callback_data=f"quick:{x}") for x in QUICK_AMOUNTS]
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([cancel_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def currencies(lang: str, prefix: str = "cur") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(code, callback_data=f"{prefix}:{code}") for code in CURRENCIES],
        [cancel_button(lang)],
    ])


def split_or_finish(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t("btn_split_more", lang), callback_data="split:more")],
        [InlineKeyboardButton(t("btn_split_finish", lang), callback_data="split:finish")],
    ])


def settings(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t("btn_accounts", lang), callback_data="menu:accounts")],
        [InlineKeyboardButton(t("btn_budgets", lang), callback_data="bud:list")],
        [InlineKeyboardButton(t("btn_ai_advice", lang), callback_data="set:advice")],
        [InlineKeyboardButton(t("btn_language", lang), callback_data="set:lang")],
        [back_button(lang)],
    ])
