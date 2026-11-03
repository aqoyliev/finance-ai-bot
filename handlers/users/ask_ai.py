"""Ask AI: questions about the owner's own data, answered by the analysis model with read-only tools.

Two ways in: the main-menu button (AskAI.question state: every text is a question until Menu / Cancel, so
follow-ups work) and plain free text that the extraction model classifies as a question (handled from
handlers/users/ai_input.py). The conversation lives in FSM data (HISTORY_KEY) and is cleared by /start,
Menu or Cancel (state.finish) or after an hour of silence.
"""
import logging
from html import escape
from typing import Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import ai as ai_kb
from keyboards.inline import finance as kb
from loader import dp
from states.finance import AskAI
from utils.ai import assistant, claude
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.texts import split_message

from .ai_common import error_text, typing

log = logging.getLogger(__name__)

HISTORY_KEY = "qa_turns"
UPDATED_KEY = "qa_at"


async def stored_history(state: FSMContext):
    data = await state.get_data()
    return assistant.fresh(data.get(HISTORY_KEY), data.get(UPDATED_KEY), db.now())


async def has_conversation(state: FSMContext) -> bool:
    return bool(await stored_history(state))


async def answer(message: types.Message, state: FSMContext, lang: str, question: str,
                 status: Optional[types.Message] = None) -> None:
    """Answer one question (with the stored conversation) and reply in place of `status` if given."""
    client = claude.get_client()
    markup = ai_kb.ask_answer(lang)
    if not client.configured:
        await message.answer(t("ai_not_configured", lang), reply_markup=kb.main_menu(lang))
        return
    if status is None:
        status = await message.answer(t("ask_thinking", lang))
    else:
        await status.edit_text(t("ask_thinking", lang))
    try:
        async with typing(message.chat.id):
            result = await assistant.ask(message.from_user.id, question, lang, await stored_history(state),
                                         client=client)
    except claude.AIError as err:
        log.info("Ask AI failed: %s", err)
        await status.edit_text(error_text(err.code, lang, prefix="ask_error_"), reply_markup=markup)
        return
    await state.update_data({HISTORY_KEY: result.turns, UPDATED_KEY: db.now().isoformat()})
    chunks = split_message(escape(result.text, quote=False))
    for index, chunk in enumerate(chunks):
        last = index == len(chunks) - 1
        if index == 0:
            await status.edit_text(chunk, reply_markup=markup if last else None)
        else:
            await message.answer(chunk, reply_markup=markup if last else None)


@dp.callback_query_handler(Text(equals="menu:ask"), state="*")
async def open_ask(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()  # a new conversation
    await AskAI.question.set()
    await call.message.edit_text(t("ask_intro", lang), reply_markup=ai_kb.ask_answer(lang))


@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=AskAI.question,
                    content_types=types.ContentTypes.TEXT)
async def question(message: types.Message, state: FSMContext, lang: str):
    await answer(message, state, lang, message.text)
