from typing import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.db_api.common import ACCOUNT_KINDS
from utils.i18n import t

from .finance import back_button, cancel_button


def account_list(accounts: Iterable, lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"{a.name} ({a.currency})", callback_data=f"acs:view:{a.id}")]
            for a in accounts]
    rows.append([InlineKeyboardButton(t("btn_add_account", lang), callback_data="acs:add")])
    rows.append([back_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_actions(account, lang: str) -> InlineKeyboardMarkup:
    def button(key: str, action: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(t(key, lang), callback_data=f"acs:{action}:{account.id}")

    rows = [[button("btn_rename", "ren")]]
    if account.kind == "credit":
        rows.append([button("btn_edit_opening_debt", "open")])
        rows.append([button("btn_edit_limit", "lim")])
    else:
        rows.append([button("btn_edit_opening", "open")])
    rows.append([button("btn_deactivate", "off")])
    rows.append([back_button(lang, "menu:accounts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_deactivate(account_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(t("btn_yes_deactivate", lang), callback_data=f"acs:offok:{account_id}")],
        [back_button(lang, f"acs:view:{account_id}")],
    ])


def account_kinds(lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t(f"kind_{kind}", lang), callback_data=f"nakind:{kind}")]
            for kind in ACCOUNT_KINDS]
    rows.append([cancel_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
