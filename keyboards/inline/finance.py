from typing import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.db_api.finance import CURRENCIES

QUICK_AMOUNTS = ("5000", "10000", "20000", "50000", "100000")

CANCEL_BUTTON = InlineKeyboardButton("Cancel", callback_data="cancel")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("➖ EXPENSE", callback_data="menu:expense"),
         InlineKeyboardButton("➕ INCOME", callback_data="menu:income")],
        [InlineKeyboardButton("💳 MY ACCOUNTS", callback_data="menu:accounts"),
         InlineKeyboardButton("📊 REPORT", callback_data="menu:report")],
        [InlineKeyboardButton("🧾 HISTORY", callback_data="menu:history"),
         InlineKeyboardButton("⚙️ SETTINGS", callback_data="menu:settings")],
    ])


def choices(items: Iterable, prefix: str, extra: Iterable[InlineKeyboardButton] = ()) -> InlineKeyboardMarkup:
    """One button per item (objects with .id and .name); callback data is '<prefix>:<id>'."""
    rows = [[InlineKeyboardButton(item.name, callback_data=f"{prefix}:{item.id}")] for item in items]
    rows.extend([button] for button in extra)
    rows.append([CANCEL_BUTTON])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subcategories(items: Iterable) -> InlineKeyboardMarkup:
    return choices(items, "sub", extra=[InlineKeyboardButton("No subcategory", callback_data="sub:0")])


def amount_prompt() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(x, callback_data=f"quick:{x}") for x in QUICK_AMOUNTS]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([CANCEL_BUTTON])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def currencies() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(code, callback_data=f"cur:{code}") for code in CURRENCIES],
        [CANCEL_BUTTON],
    ])


def split_or_finish() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Yes, add another part", callback_data="split:more")],
        [InlineKeyboardButton("No, finish", callback_data="split:finish")],
    ])
