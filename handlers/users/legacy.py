"""What is left of the old chat menus: a short hint that points to the Mini App.

Reports, balances, settings, history, budgets and manual entry moved to the Mini App. Users may still type an
old command (/report, /expense, ...) or press a button of the old reply keyboard (📊 Report, 💳 Balance,
⚙️ Settings, in any language) that is still shown in their chat; both get the hint with the "open the app" button
instead of being sent to the AI. Registered after start / help and before AI input. Buttons of old inline
screens are answered in echo.py (the catch-all callback handler).
"""
from aiogram import types
from aiogram.dispatcher.filters import Command

from keyboards.inline import app as kb
from loader import dp
from utils.i18n import LANGUAGES, t

OLD_COMMANDS = ("expense", "income", "transfer", "salaryday", "rate", "report", "balance", "settings")
OLD_KEYBOARD_KEYS = ("old_kb_report", "old_kb_balance", "old_kb_settings")
OLD_KEYBOARD_TEXTS = frozenset(t(key, lang, _escape=False) for key in OLD_KEYBOARD_KEYS for lang in LANGUAGES)


async def send_hint(message: types.Message, lang: str) -> None:
    await message.answer(t("moved_to_app", lang), reply_markup=kb.open_app(lang))


def is_old_keyboard_text(message: types.Message) -> bool:
    return (message.text or "").strip() in OLD_KEYBOARD_TEXTS


@dp.message_handler(Command(list(OLD_COMMANDS)), state="*")
@dp.message_handler(is_old_keyboard_text, state="*")
async def moved_to_app(message: types.Message, lang: str):
    """The FSM state is kept: an account question of AI input that waits for an answer still works."""
    await send_hint(message, lang)
