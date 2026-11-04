"""AI input: receipt photos, PDFs, voice messages, bank SMS and free text -> operations saved right away.

There is no confirmation step. Every recognized operation with an amount is saved at once:
- the account must be resolved confidently (a valid account id, card digits, "naqd" / "karta"); otherwise
  the bot asks only "which payment method?" with one button per account, and the answer is applied to every
  operation of the message that still lacks one (they wait in FSM data under PENDING_KEY, state AIDraft.account);
- an expense or income without a category goes to the "Other" category (created if needed);
- an operation without an amount is not saved; the user gets a short "no amount understood" reply.
The same SMS / photo / file sent again is not saved twice (source_ref); the same amount on the same account a few
minutes apart is saved with a warning. Budget and credit limit alerts follow the save confirmations.

The extraction model also classifies free text: a question about the user's finances is handed to Ask AI
(handlers/users/ask_ai.py) instead. Photos and files always go to extraction. Manual flows are unaffected:
their FSM states are handled by their own handlers, and this module only reacts when no state (or
AIDraft.account) is set. It is registered after the reply-keyboard handlers and before handlers/users/echo.

Voice messages and audio files need audio input, which only the Gemini provider has: the audio is transcribed
and extracted in one call. With AI_PROVIDER=claude they get a localized hint.
"""
import logging
import re
from html import escape
from typing import List, Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from loader import bot, dp
from states.finance import AIDraft
from utils.ai import core as ai
from utils.ai import parser
from utils.ai.parser import Draft
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.texts import card_amount, operation_card, over_limit_warning
from utils.notify_alerts import send_alerts

from . import ask_ai
from .ai_common import error_text, typing  # noqa: F401  (typing is used here and patched in checks)

log = logging.getLogger(__name__)

INPUT_STATES = [None, AIDraft.account]  # states in which a new input starts an analysis
PENDING_KEY = "ai_pending"  # operations waiting for the payment method


async def download_file(file_id: str) -> bytes:
    """Telegram file -> bytes (replaced in end-to-end checks)."""
    return (await bot.download_file_by_id(file_id)).getvalue()


class Replier:
    """Sends the replies of one input: the first one replaces the 'Analyzing...' status, the rest are new."""

    def __init__(self, message: types.Message, edit_first: bool):
        self.message = message
        self.edit_next = edit_first

    async def __call__(self, text: str, markup: Optional[InlineKeyboardMarkup] = None) -> None:
        if self.edit_next:
            self.edit_next = False
            await self.message.edit_text(text, reply_markup=markup)
        else:
            await self.message.answer(text, reply_markup=markup)


# ---- Input: analysis ----

async def analyze(message: types.Message, state: FSMContext, lang: str, text: Optional[str] = None,
                  media: Optional[ai.Media] = None, source_ref: Optional[str] = None):
    client = ai.get_client()
    if not client.configured:
        await message.answer(error_text("not_configured", lang))
        return
    status = await message.answer(t("ai_analyzing", lang))
    user_id = message.from_user.id
    now = db.now()
    try:
        ctx = await parser.load_context(user_id)
        accounts, categories = ctx.as_prompt_data()
        context = ai.build_context(accounts, categories, now.strftime("%Y-%m-%d %H:%M (%A)"),
                                   conversation=await ask_ai.has_conversation(state))
        async with typing(message.chat.id):
            raw = await ai.extract_operations(context, text, [media] if media else [], client=client)
    except ai.AIError as err:
        log.info("AI input failed: %s", err)
        await status.edit_text(error_text(err.code, lang))
        return

    if text and not media:
        if parser.intent(raw) == "question":
            await ask_ai.answer(message, state, lang, text, status=status)
            return
        if parser.input_type(raw) != "bank_sms":
            source_ref = None  # typed text may honestly repeat ("coffee 18000" every day); an SMS may not
    drafts = parser.parse_response(raw, ctx, now, source_ref)
    if not drafts:
        await status.edit_text(t("ai_nothing_found", lang))
        return
    await state.finish()
    await process(Replier(status, edit_first=True), state, lang, user_id, drafts)


async def process(reply: Replier, state: FSMContext, lang: str, user_id: int, drafts: List[Draft]) -> None:
    """Save what can be saved, report what cannot and ask for the account of the rest."""
    for draft in drafts:
        if draft.notes:
            log.info("AI draft notes: %s", draft.notes)
    no_amount = [d for d in drafts if not d.amount_minor]
    drafts = [d for d in drafts if d.amount_minor]
    no_target = [d for d in drafts if d.kind == "transfer" and not d.to_account_id]
    drafts = [d for d in drafts if not (d.kind == "transfer" and not d.to_account_id)]
    for draft in drafts:
        if draft.kind != "transfer" and not draft.category:
            draft.category, draft.subcategory = await db.fallback_category(user_id, draft.kind, lang), None

    ready = [d for d in drafts if d.account_id]
    pending = [d for d in drafts if not d.account_id]
    saved = await save_drafts(reply, lang, user_id, ready)
    if no_amount:
        await reply(t("ai_no_amount", lang))
    if no_target:
        await reply(t("ai_no_target", lang))
    if pending:
        await ask_account(reply, state, lang, user_id, pending)
    if saved:
        await send_alerts(user_id, lang, *saved)


async def save_drafts(reply: Replier, lang: str, user_id: int, drafts: List[Draft]) -> List[db.SavedOperation]:
    """Save complete drafts one by one, each confirmed with its own card."""
    saved_ops = []
    for draft in drafts:
        duplicate = await parser.duplicate_of(user_id, draft, db.now())
        if duplicate == "source":
            await reply(t("ai_already_saved", lang))
            continue
        try:
            saved = await parser.save_draft(user_id, draft)
        except db.FinanceError:
            await reply(t("ai_save_failed", lang))
            continue
        parts = [operation_card(saved, lang)] + over_limit_warning(saved.over_limit, lang)
        if duplicate == "similar":
            parts.append(t("ai_duplicate", lang))
        await reply("\n\n".join(parts))
        saved_ops.append(saved)
    return saved_ops


# ---- Missing account: "which payment method?" ----

def pending_line(draft: Draft, lang: str) -> str:
    amount = card_amount(draft.amount_minor, draft.currency, lang) if draft.currency else \
        f"{draft.amount_minor / 100:,.0f}".replace(",", " ")
    label = draft.category or ""
    if draft.subcategory:
        label = f"{label} › {draft.subcategory}"
    return f"• {amount}" + (f" — {label}" if label else "")


async def ask_account(reply: Replier, state: FSMContext, lang: str, user_id: int, drafts: List[Draft]) -> None:
    currencies = {d.currency for d in drafts}
    only = currencies.pop() if len(currencies) == 1 else None
    accounts = await db.list_accounts(user_id, only) if only else await db.list_accounts(user_id)
    if not accounts:
        await reply(t("no_accounts_in_currency", lang, currency=only or "UZS / USD"))
        return
    await state.update_data({PENDING_KEY: [d.to_dict() for d in drafts]})
    await state.set_state(AIDraft.account)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(f"{a.name} ({a.currency})", callback_data=f"ai:acc:{a.id}")] for a in accounts])
    lines = [t("ai_ask_account", lang)] + [escape(pending_line(d, lang), quote=False) for d in drafts]
    await reply("\n".join(lines), markup)


async def apply_account(reply: Replier, state: FSMContext, lang: str, user_id: int, account) -> None:
    """Give the chosen account to every waiting operation and save them."""
    drafts = [Draft.from_dict(d) for d in (await state.get_data()).get(PENDING_KEY) or []]
    await state.finish()
    if not drafts:
        await reply(t("session_lost", lang))
        return
    usable, failed = [], 0
    for draft in drafts:
        if draft.currency and draft.currency != account.currency:
            failed += 1
            continue
        draft.account_id, draft.currency = account.id, account.currency
        usable.append(draft)
    saved = await save_drafts(reply, lang, user_id, usable)
    if failed:
        await reply(t("ai_save_failed", lang))
    if saved:
        await send_alerts(user_id, lang, *saved)


@dp.callback_query_handler(Text(startswith="ai:acc:"), state="*")
async def choose_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    account = await db.get_account(call.from_user.id, int(call.data.split(":")[2]))
    if account is None or await state.get_state() != AIDraft.account.state:
        await state.finish()
        await call.message.edit_text(t("session_lost", lang))
        return
    await apply_account(Replier(call.message, edit_first=True), state, lang, call.from_user.id, account)


async def typed_account(message: types.Message, state: FSMContext, lang: str) -> bool:
    """While an account is asked for, a short typed name ("naqd", "uob") answers it. True if handled."""
    text = message.text or ""
    if await state.get_state() != AIDraft.account.state or re.search(r"\d", text) or len(text) > 40:
        return False
    ctx = await parser.load_context(message.from_user.id)
    match = parser.match_account(ctx, hint=text)
    account = await db.get_account(message.from_user.id, match.id) if match else None
    if account is None:
        return False
    await apply_account(Replier(message, edit_first=False), state, lang, message.from_user.id, account)
    return True


# ---- Input handlers ----

@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=INPUT_STATES,
                    content_types=types.ContentTypes.TEXT)
async def text_input(message: types.Message, state: FSMContext, lang: str):
    if await typed_account(message, state, lang):
        return
    # Forwarded bank SMS / notifications are plain text as well; the fingerprint catches re-sends
    await analyze(message, state, lang, text=message.text, source_ref=parser.fingerprint(message.text))


@dp.message_handler(state=INPUT_STATES, content_types=types.ContentTypes.PHOTO)
async def photo_input(message: types.Message, state: FSMContext, lang: str):
    photo = message.photo[-1]  # largest size
    await analyze_file(message, state, lang, photo.file_id, photo.file_unique_id, "image/jpeg")


@dp.message_handler(state=INPUT_STATES, content_types=types.ContentTypes.DOCUMENT)
async def document_input(message: types.Message, state: FSMContext, lang: str):
    document = message.document
    mime = (document.mime_type or "").lower()
    if ai.audio_mime(mime):  # an audio file sent as a document
        await audio_input(message, state, lang, document, mime)
        return
    if not ai.get_client().accepts(mime):
        await message.answer(t("ai_unsupported_file", lang))
        return
    await analyze_file(message, state, lang, document.file_id, document.file_unique_id, mime,
                       size=document.file_size)


@dp.message_handler(state=INPUT_STATES, content_types=[types.ContentType.VOICE, types.ContentType.AUDIO])
async def voice_input(message: types.Message, state: FSMContext, lang: str):
    audio = message.voice or message.audio
    await audio_input(message, state, lang, audio, audio.mime_type or "audio/ogg")  # voice notes are OGG/Opus


@dp.message_handler(state=INPUT_STATES, content_types=types.ContentTypes.VIDEO_NOTE)
async def video_note_input(message: types.Message, state: FSMContext, lang: str):
    await message.answer(t("ai_video_note_unsupported", lang))


async def audio_input(message: types.Message, state: FSMContext, lang: str, audio, mime: str):
    """Voice/audio -> Gemini audio input (transcribe + extract in one call), within the size/duration limits."""
    client = ai.get_client()
    if not client.configured:
        await message.answer(error_text("not_configured", lang))
        return
    if not client.supports_audio:
        await message.answer(t("ai_voice_needs_gemini", lang))
        return
    mime = ai.audio_mime(mime)
    if mime is None:
        await message.answer(t("ai_unsupported_file", lang))
        return
    duration = getattr(audio, "duration", None) or 0
    size = getattr(audio, "file_size", None) or 0
    if duration > ai.MAX_AUDIO_SECONDS or size > client.media_limit(mime):
        await message.answer(t("ai_voice_too_long", lang, minutes=ai.MAX_AUDIO_SECONDS // 60,
                               mb=ai.MAX_AUDIO_BYTES // (1024 * 1024)))
        return
    await analyze_file(message, state, lang, audio.file_id, audio.file_unique_id, mime, size=size)


async def analyze_file(message: types.Message, state: FSMContext, lang: str, file_id: str, unique_id: str,
                       mime: str, size: Optional[int] = None):
    client = ai.get_client()
    if not client.configured:
        await message.answer(error_text("not_configured", lang))
        return
    if size and size > client.media_limit(mime):
        await message.answer(error_text("too_large", lang))
        return
    try:
        data = await download_file(file_id)
    except Exception:
        log.exception("Could not download file %s", file_id)
        await message.answer(error_text("unavailable", lang))
        return
    # A caption ("taxi, uob card") is passed along as a hint
    await analyze(message, state, lang, text=message.caption, media=ai.Media(data, mime),
                  source_ref=parser.fingerprint(f"file:{unique_id}"))
