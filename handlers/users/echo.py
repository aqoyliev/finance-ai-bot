from aiogram import types

from loader import dp

from .legacy import send_hint


# Anything not handled elsewhere (stickers, unknown commands, ...): what the bot does and where the rest is
@dp.message_handler(state=None, content_types=types.ContentTypes.ANY)
async def bot_fallback(message: types.Message, lang: str):
    await send_hint(message, lang)


# A button of an old chat screen (report, settings, history, ...) that moved to the Mini App
@dp.callback_query_handler(state="*")
async def stale_button(call: types.CallbackQuery, lang: str):
    await call.answer()
    await send_hint(call.message, lang)
