"""Ask AI: questions about the owner's own data, answered by the analysis model with read-only tools.

Plain free text that the extraction model classifies as a question is handed here from
handlers/users/ai_input.py. The conversation lives in FSM data (HISTORY_KEY), so follow-up questions work; the
extraction model is told about it so short follow-ups ("and last month?") are classified as questions too. It is
cleared by /start, the reply-keyboard buttons, a newly recorded operation (state.finish) or after an hour of
silence.
"""
import logging
from html import escape
from typing import Optional

from aiogram import types
from aiogram.dispatcher import FSMContext

from utils.ai import assistant
from utils.ai import core as ai
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
    client = ai.get_client()
    if not client.configured:
        await message.answer(error_text("not_configured", lang))
        return
    if status is None:
        status = await message.answer(t("ask_thinking", lang))
    else:
        await status.edit_text(t("ask_thinking", lang))
    try:
        async with typing(message.chat.id):
            result = await assistant.ask(message.from_user.id, question, lang, await stored_history(state),
                                         client=client)
    except ai.AIError as err:
        log.info("Ask AI failed: %s", err)
        await status.edit_text(error_text(err.code, lang, prefix="ask_error_"))
        return
    await state.update_data({HISTORY_KEY: result.turns, UPDATED_KEY: db.now().isoformat()})
    chunks = split_message(escape(result.text, quote=False))
    await status.edit_text(chunks[0])
    for chunk in chunks[1:]:
        await message.answer(chunk)

