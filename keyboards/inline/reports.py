from typing import Dict, Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.db_api import reports as rep
from utils.db_api.common import CURRENCIES
from utils.i18n import t

from .finance import back_button

MAX_CATEGORY_BUTTONS = 10


def report_view(report, category_ids: Dict[str, int], lang: str) -> InlineKeyboardMarkup:
    """Category buttons (drill-down), previous / next period, budgets, accounts and back to the menu."""
    names = list(dict.fromkeys(row.name for s in report.currencies for row in s.categories))
    buttons = [InlineKeyboardButton(name, callback_data=f"repc:{report.offset}:{category_ids[name]}")
               for name in names if name in category_ids][:MAX_CATEGORY_BUTTONS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

    nav = []
    if report.has_earlier:
        label = rep.shift_period(report.start, -1).strftime("%d.%m.%y")
        nav.append(InlineKeyboardButton(f"◀ {label}", callback_data=f"rep:{report.offset - 1}"))
    if report.offset < 0:
        label = report.end.strftime("%d.%m.%y")
        nav.append(InlineKeyboardButton(f"{label} ▶", callback_data=f"rep:{report.offset + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(t("btn_budgets", lang), callback_data="bud:list"),
                 InlineKeyboardButton(t("btn_accounts", lang), callback_data="menu:accounts")])
    rows.append([back_button(lang)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategory_view(offset: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(lang, f"rep:{offset}")]])


def budget_categories(categories: Iterable, labels: Dict[str, str], lang: str) -> InlineKeyboardMarkup:
    """One button per expense category: '<name> — <limit or not set>'."""
    rows = [[InlineKeyboardButton(labels[c.name], callback_data=f"bud:cat:{c.id}")] for c in categories]
    rows.append([back_button(lang, "menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def budget_actions(category_id: int, has_budget: bool, lang: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t("btn_set_budget", lang), callback_data=f"bud:set:{category_id}")]]
    if has_budget:
        rows.append([InlineKeyboardButton(t("btn_remove_budget", lang), callback_data=f"bud:del:{category_id}")])
    rows.append([back_button(lang, "bud:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def budget_currencies(category_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(code, callback_data=f"bud:cur:{category_id}:{code}") for code in CURRENCIES],
        [back_button(lang, f"bud:cat:{category_id}")],
    ])


def budget_amount_prompt(category_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[back_button(lang, f"bud:cat:{category_id}")]])
