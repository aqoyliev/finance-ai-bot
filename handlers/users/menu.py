"""The reply keyboard under the input field: 📊 Report, 💳 Balance, ⚙️ Settings.

Registered before every other text handler (FSM steps, Ask AI, AI input), so these texts are never taken for an
amount or sent to the AI. Pressing one ends whatever flow was in progress. The texts of every language are
accepted, so a keyboard sent before a language change keeps working.
"""
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.default.menu import labels
from loader import dp

# The modules with the screens are imported inside the handlers: importing them here would register their
# FSM text handlers before these ones.


@dp.message_handler(Text(equals=labels("kb_report")), state="*")
async def report(message: types.Message, state: FSMContext, lang: str):
    from . import reports
    await state.finish()
    await reports.render_report(message, message.from_user.id, 0, lang, replace=False)


@dp.message_handler(Text(equals=labels("kb_balance")), state="*")
async def balance(message: types.Message, state: FSMContext, lang: str):
    from . import accounts
    await state.finish()
    await accounts.render_list(message, message.from_user.id, lang, edit=False)


@dp.message_handler(Text(equals=labels("kb_settings")), state="*")
async def open_settings(message: types.Message, state: FSMContext, lang: str):
    from . import settings
    await state.finish()
    await settings.render_settings(message, message.from_user.id, lang, edit=False)
