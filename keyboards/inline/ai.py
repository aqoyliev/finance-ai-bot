"""Inline keyboards for AI drafts (callback data prefix 'ai:')."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.i18n import t

BACK = "ai:back"  # back to the draft card


def _button(key: str, data: str, lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(t(key, lang), callback_data=data)


def back_to_draft(lang: str) -> InlineKeyboardButton:
    return _button("btn_back", BACK, lang)


def draft_card(lang: str, is_transfer: bool, can_save: bool, can_save_all: bool,
               multiple: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_save:
        rows.append([_button("btn_ai_save", "ai:save", lang)])
    if can_save_all:
        rows.append([_button("btn_ai_save_all", "ai:saveall", lang)])
    second = _button("btn_ai_to_account", "ai:edit:to", lang) if is_transfer \
        else _button("btn_ai_category", "ai:edit:cat", lang)
    rows += [
        [_button("btn_ai_amount", "ai:edit:amount", lang), second],
        [_button("btn_ai_account", "ai:edit:acc", lang), _button("btn_ai_kind", "ai:edit:kind", lang)],
        [_button("btn_ai_currency", "ai:edit:cur", lang), _button("btn_ai_date", "ai:edit:date", lang)],
    ]
    last = [_button("btn_ai_cancel", "ai:cancel", lang)]
    if multiple:
        last.insert(0, _button("btn_ai_skip", "ai:skip", lang))
    rows.append(last)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kinds(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_button("kind_expense_op", "ai:kind:expense", lang), _button("kind_income_op", "ai:kind:income", lang),
         _button("kind_transfer_op", "ai:kind:transfer", lang)],
        [back_to_draft(lang)],
    ])


def back_only(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_to_draft(lang)]])
