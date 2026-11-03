from typing import Iterable, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import t

from .finance import back_button


def history(items: Iterable[Tuple[int, str]], lang: str) -> InlineKeyboardMarkup:
    """items: (transaction id, button label)."""
    rows = [[InlineKeyboardButton(label, callback_data=f"opv:{tx_id}")] for tx_id, label in items]
    rows.append([back_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def operation_actions(tx_id: int, is_transfer: bool, lang: str) -> InlineKeyboardMarkup:
    def button(key: str, prefix: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(t(key, lang), callback_data=f"{prefix}:{tx_id}")

    rows = [[button("btn_edit_amount", "opa")]]
    if not is_transfer:
        rows.append([button("btn_edit_category", "opc")])
        rows.append([button("btn_edit_account", "opk")])
    rows.append([button("btn_delete", "opd")])
    rows.append([back_button(lang, "menu:history")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete(tx_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t("btn_yes_delete", lang), callback_data=f"opdy:{tx_id}")],
        [back_button(lang, f"opv:{tx_id}")],
    ])
