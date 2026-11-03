"""AI input: receipt photos, bank SMS and free text -> draft operations -> confirm -> save.

Drafts live in FSM data ("ai_drafts", the current one first) while the state is AIDraft.*.
Manual flows are unaffected: their FSM states are handled by their own handlers, and this module only
reacts to plain text when no state (or AIDraft.review) is set. It is registered before handlers/users/echo.
"""
import asyncio
import contextlib
import logging
from typing import List, Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text

from keyboards.inline import ai as ai_kb
from keyboards.inline import finance as kb
from loader import bot, dp
from states.finance import AIDraft
from utils.ai import claude, parser
from utils.ai.parser import Draft
from utils.db_api import finance as db
from utils.i18n import TEXTS, t
from utils.misc.money import money_text, parse_amount
from utils.misc.texts import balance_line, over_limit_warning
from utils.notify_alerts import send_alerts

from .finance import Choice

log = logging.getLogger(__name__)

DOCUMENT_TYPES = claude.IMAGE_TYPES + (claude.PDF_TYPE,)  # what Claude can read (no HEIC)
INPUT_STATES = [None, AIDraft.review]  # states in which a new input starts an analysis


async def download_file(file_id: str) -> bytes:
    """Telegram file -> bytes (replaced in end-to-end checks)."""
    return (await bot.download_file_by_id(file_id)).getvalue()


def error_text(code: str, lang: str) -> str:
    key = "ai_not_configured" if code == "not_configured" else f"ai_error_{code}"
    return t(key if key in TEXTS else "ai_error_unavailable", lang)


@contextlib.asynccontextmanager
async def typing(chat_id: int):
    """Keep the 'typing…' chat action alive while the AI works (Telegram shows it for ~5 s)."""
    async def loop():
        while True:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id, types.ChatActions.TYPING)
            await asyncio.sleep(4)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()


# ---- Drafts in FSM data ----

async def load_drafts(state: FSMContext) -> List[Draft]:
    return [Draft.from_dict(d) for d in (await state.get_data()).get("ai_drafts") or []]


async def store_drafts(state: FSMContext, drafts: List[Draft]) -> None:
    await state.update_data(ai_drafts=[d.to_dict() for d in drafts])


async def current_draft(state: FSMContext) -> Optional[Draft]:
    drafts = await load_drafts(state)
    return drafts[0] if drafts else None


async def replace_current(state: FSMContext, draft: Draft) -> None:
    drafts = await load_drafts(state)
    drafts[0] = draft
    await store_drafts(state, drafts)


# ---- Rendering ----

def draft_text(draft: Draft, accounts: dict, position: int, total: int, lang: str) -> str:
    kind = t(f"kind_{draft.kind}_op", lang)
    amount = money_text(draft.amount_minor, draft.currency or "") if draft.amount_minor else "—"
    account = accounts.get(draft.account_id)
    date = parser.occurred_at(draft)
    lines = [t("ai_draft_title", lang, index=position, total=total, kind=kind),
             t("op_amount", lang, amount=amount.strip())]
    if draft.kind == "transfer":
        target = accounts.get(draft.to_account_id)
        lines.append(t("op_from", lang, name=account.name if account else "—"))
        lines.append(t("op_to", lang, name=target.name if target else "—"))
    else:
        lines.append(t("op_category", lang, category=draft.category or "—", subcategory=draft.subcategory or "—"))
        lines.append(t("op_account", lang, name=account.name if account else "—"))
    lines.append(t("op_date", lang, date=date.strftime("%d.%m.%Y %H:%M") if date else t("ai_date_now", lang)))
    if draft.note:
        lines.append(t("op_note", lang, note=draft.note))

    notices = [t(key, lang) for key in dict.fromkeys(draft.notes)]
    missing = parser.missing_fields(draft)
    if missing:
        fields = ", ".join(t(f"ai_field_{name}", lang) for name in missing)
        notices.append(t("ai_missing", lang, fields=fields))
    if draft.duplicate:
        notices.append(t("ai_duplicate", lang))
    if draft.confidence < parser.LOW_CONFIDENCE:
        notices.append(t("ai_low_confidence", lang))
    return "\n".join(lines + ([""] + notices if notices else []))


async def render(message: types.Message, state: FSMContext, lang: str, user_id: int, edit: bool = True):
    """Show the current draft card (edit the given message or send a new one)."""
    drafts = await load_drafts(state)
    data = await state.get_data()
    accounts = {a.id: a for a in await db.list_accounts(user_id)}
    for draft in drafts:  # an account may have been deactivated meanwhile
        if draft.account_id not in accounts:
            draft.account_id = None
        if draft.to_account_id not in accounts:
            draft.to_account_id = None
    draft = await parser.mark_duplicate(user_id, drafts[0], db.now())
    await store_drafts(state, drafts)
    await AIDraft.review.set()

    total = data.get("ai_total") or len(drafts)
    position = total - len(drafts) + 1
    complete = not parser.missing_fields(draft)
    all_complete = len(drafts) > 1 and all(not parser.missing_fields(d) for d in drafts)
    markup = ai_kb.draft_card(lang, draft.kind == "transfer", complete, all_complete, len(drafts) > 1)
    text = draft_text(draft, accounts, position, total, lang)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def lost(call: types.CallbackQuery, state: FSMContext, lang: str):
    await state.finish()
    await call.message.edit_text(t("session_lost", lang), reply_markup=kb.main_menu(lang))


# ---- Input: analysis ----

async def analyze(message: types.Message, state: FSMContext, lang: str, text: Optional[str] = None,
                  media: Optional[claude.Media] = None, source_ref: Optional[str] = None):
    client = claude.get_client()
    if not client.configured:
        await message.answer(t("ai_not_configured", lang), reply_markup=kb.main_menu(lang))
        return
    status = await message.answer(t("ai_analyzing", lang))
    user_id = message.from_user.id
    now = db.now()
    try:
        ctx = await parser.load_context(user_id)
        accounts, categories = ctx.as_prompt_data()
        context = claude.build_context(accounts, categories, now.strftime("%Y-%m-%d %H:%M (%A)"))
        async with typing(message.chat.id):
            raw = await claude.extract_operations(context, text, [media] if media else [], client=client)
    except claude.AIError as err:
        log.info("AI input failed: %s", err)
        await status.edit_text(error_text(err.code, lang), reply_markup=kb.main_menu(lang))
        return

    drafts = parser.parse_response(raw, ctx, now, source_ref)
    if not drafts:
        await status.edit_text(t("ai_nothing_found", lang), reply_markup=kb.main_menu(lang))
        return
    await state.finish()
    await state.update_data(ai_total=len(drafts))
    await store_drafts(state, drafts)
    await render(status, state, lang, user_id)


@dp.message_handler(lambda m: not (m.text or "").startswith("/"), state=INPUT_STATES,
                    content_types=types.ContentTypes.TEXT)
async def text_input(message: types.Message, state: FSMContext, lang: str):
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
    if mime not in DOCUMENT_TYPES:
        await message.answer(t("ai_unsupported_file", lang))
        return
    await analyze_file(message, state, lang, document.file_id, document.file_unique_id, mime,
                       size=document.file_size)


@dp.message_handler(state=INPUT_STATES, content_types=[types.ContentType.VOICE, types.ContentType.AUDIO,
                                                     types.ContentType.VIDEO_NOTE])
async def voice_input(message: types.Message, state: FSMContext, lang: str):
    # Claude has no audio input
    await message.answer(t("ai_voice_unsupported", lang))


async def analyze_file(message: types.Message, state: FSMContext, lang: str, file_id: str, unique_id: str,
                       mime: str, size: Optional[int] = None):
    if not claude.get_client().configured:
        await message.answer(t("ai_not_configured", lang), reply_markup=kb.main_menu(lang))
        return
    if size and size > claude.media_limit(mime):
        await message.answer(error_text("too_large", lang))
        return
    try:
        data = await download_file(file_id)
    except Exception:
        log.exception("Could not download file %s", file_id)
        await message.answer(error_text("unavailable", lang))
        return
    # A caption ("taxi, uob card") is passed along as a hint
    await analyze(message, state, lang, text=message.caption, media=claude.Media(data, mime),
                  source_ref=parser.fingerprint(f"file:{unique_id}"))


# ---- Save / skip / cancel ----

def saved_summary(draft: Draft, saved: db.SavedOperation, lang: str) -> str:
    account_names = {a.id: a.name for a in saved.accounts}
    amount = money_text(draft.amount_minor, draft.currency)
    if draft.kind == "transfer":
        summary = f"{amount} · {account_names.get(draft.account_id)} → {account_names.get(draft.to_account_id)}"
    else:
        category = draft.category + (f" / {draft.subcategory}" if draft.subcategory else "")
        summary = f"{amount} · {category} · {account_names.get(draft.account_id)}"
    lines = [t("ai_saved", lang, summary=summary)] + [balance_line(a, lang) for a in saved.accounts]
    return "\n".join(lines + over_limit_warning(saved.over_limit, lang))


async def next_or_finish(call: types.CallbackQuery, state: FSMContext, lang: str, result: str,
                         saved: Optional[db.SavedOperation] = None):
    """Drop the current draft, then show the next one (as a new message) or finish.

    Limit alerts for a just saved operation go out before the next draft is shown."""
    drafts = (await load_drafts(state))[1:]
    if not drafts:
        await state.finish()
        await call.message.edit_text(result, reply_markup=kb.main_menu(lang))
        if saved:
            await send_alerts(call.from_user.id, lang, saved)
        return
    await store_drafts(state, drafts)
    await call.message.edit_text(result)
    if saved:
        await send_alerts(call.from_user.id, lang, saved)
    await render(call.message, state, lang, call.from_user.id, edit=False)


@dp.callback_query_handler(Text(equals="ai:save"), state=AIDraft.states)
async def save(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    if draft is None:
        await lost(call, state, lang)
        return
    if parser.missing_fields(draft):
        await render(call.message, state, lang, call.from_user.id)
        return
    try:
        saved = await parser.save_draft(call.from_user.id, draft)
    except db.FinanceError:
        draft.account_id = draft.to_account_id = None
        await replace_current(state, draft)
        await call.message.answer(t("ai_save_failed", lang))
        await render(call.message, state, lang, call.from_user.id, edit=False)
        return
    await next_or_finish(call, state, lang, saved_summary(draft, saved, lang), saved)


@dp.callback_query_handler(Text(equals="ai:saveall"), state=AIDraft.states)
async def save_all(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    drafts = await load_drafts(state)
    if not drafts:
        await lost(call, state, lang)
        return
    results, remaining, saved_ops = [], [], []
    for draft in drafts:
        try:
            if parser.missing_fields(draft):
                raise db.InvalidValue()
            saved = await parser.save_draft(call.from_user.id, draft)
        except db.FinanceError:
            remaining.append(draft)
            continue
        saved_ops.append(saved)
        results.append(saved_summary(draft, saved, lang))
    if not remaining:
        await state.finish()
        await call.message.edit_text("\n\n".join(results), reply_markup=kb.main_menu(lang))
        await send_alerts(call.from_user.id, lang, *saved_ops)
        return
    await state.update_data(ai_total=len(remaining))
    await store_drafts(state, remaining)
    await call.message.edit_text("\n\n".join(results + [t("ai_save_failed", lang)]))
    await send_alerts(call.from_user.id, lang, *saved_ops)
    await render(call.message, state, lang, call.from_user.id, edit=False)


@dp.callback_query_handler(Text(equals="ai:skip"), state=AIDraft.states)
async def skip(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if await current_draft(state) is None:
        await lost(call, state, lang)
        return
    await next_or_finish(call, state, lang, t("ai_skipped", lang))


@dp.callback_query_handler(Text(equals="ai:cancel"), state="*")
async def cancel(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await call.message.edit_text(t("cancelled", lang), reply_markup=kb.main_menu(lang))


@dp.callback_query_handler(Text(equals=ai_kb.BACK), state=AIDraft.states)
async def back(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if await current_draft(state) is None:
        await lost(call, state, lang)
        return
    await render(call.message, state, lang, call.from_user.id)


# ---- Edit: amount and date (typed) ----

@dp.callback_query_handler(Text(equals="ai:edit:amount"), state=AIDraft.states)
async def ask_amount(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if await current_draft(state) is None:
        await lost(call, state, lang)
        return
    await AIDraft.amount.set()
    await call.message.edit_text(t("ask_new_amount", lang), reply_markup=ai_kb.back_only(lang))


@dp.message_handler(state=AIDraft.amount)
async def typed_amount(message: types.Message, state: FSMContext, lang: str):
    amount = parse_amount(message.text or "")
    draft = await current_draft(state)
    if draft is None:
        await state.finish()
        await message.answer(t("session_lost", lang), reply_markup=kb.main_menu(lang))
        return
    if amount is None:
        await message.answer(t("bad_amount", lang))
        return
    draft.amount_minor = amount
    draft.notes = [n for n in draft.notes if n != "ai_note_amount"]
    await replace_current(state, draft)
    await render(message, state, lang, message.from_user.id, edit=False)


@dp.callback_query_handler(Text(equals="ai:edit:date"), state=AIDraft.states)
async def ask_date(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    if await current_draft(state) is None:
        await lost(call, state, lang)
        return
    await AIDraft.date.set()
    await call.message.edit_text(t("ai_ask_date", lang), reply_markup=ai_kb.back_only(lang))


@dp.message_handler(state=AIDraft.date)
async def typed_date(message: types.Message, state: FSMContext, lang: str):
    draft = await current_draft(state)
    if draft is None:
        await state.finish()
        await message.answer(t("session_lost", lang), reply_markup=kb.main_menu(lang))
        return
    parsed = parser.parse_datetime(message.text, db.now())
    if parsed is None:
        await message.answer(t("ai_bad_date", lang))
        return
    draft.occurred_at = parsed.isoformat()
    await replace_current(state, draft)
    await render(message, state, lang, message.from_user.id, edit=False)


# ---- Edit: choices ----

@dp.callback_query_handler(Text(equals="ai:edit:kind"), state=AIDraft.states)
async def ask_kind(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await call.message.edit_text(t("ai_ask_kind", lang), reply_markup=ai_kb.kinds(lang))


@dp.callback_query_handler(Text(startswith="ai:kind:"), state=AIDraft.states)
async def set_kind(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    kind = call.data.split(":")[2]
    if draft is None or kind not in parser.KINDS:
        await lost(call, state, lang)
        return
    if kind != draft.kind:
        ctx = await parser.load_context(call.from_user.id)
        draft.kind = kind
        draft.category, draft.subcategory = parser.match_category(ctx, kind, draft.category, draft.subcategory)
        if kind != "transfer":
            draft.to_account_id = None
        await replace_current(state, draft)
    await render(call.message, state, lang, call.from_user.id)


@dp.callback_query_handler(Text(equals="ai:edit:cur"), state=AIDraft.states)
async def ask_currency(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await call.message.edit_text(t("ask_currency", lang), reply_markup=kb.currencies(lang, prefix="ai:cur"))


@dp.callback_query_handler(Text(startswith="ai:cur:"), state=AIDraft.states)
async def set_currency(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    currency = call.data.split(":")[2]
    if draft is None or currency not in db.CURRENCIES:
        await lost(call, state, lang)
        return
    if currency != draft.currency:
        draft.currency = currency
        accounts = {a.id: a for a in await db.list_accounts(call.from_user.id, currency)}
        if draft.account_id not in accounts:
            draft.account_id = None
        if draft.to_account_id not in accounts:
            draft.to_account_id = None
        draft.notes = [n for n in draft.notes if n not in ("ai_note_currency", "ai_note_account_currency")]
        await replace_current(state, draft)
    await render(call.message, state, lang, call.from_user.id)


async def show_accounts(call: types.CallbackQuery, state: FSMContext, lang: str, target: bool):
    draft = await current_draft(state)
    if draft is None:
        await lost(call, state, lang)
        return
    accounts = await db.list_accounts(call.from_user.id, draft.currency)
    if target:
        accounts = [a for a in accounts if a.id != draft.account_id]
    if not accounts:
        await call.message.edit_text(t("no_accounts_in_currency", lang, currency=draft.currency or "—"),
                                     reply_markup=ai_kb.back_only(lang))
        return
    labels = [Choice(a.id, f"{a.name} ({a.currency})") for a in accounts]
    key = "ai_ask_to_account" if target else "ask_new_account"
    await call.message.edit_text(
        t(key, lang, currency=draft.currency or "UZS / USD"),
        reply_markup=kb.choices(labels, "ai:to" if target else "ai:acc", lang, extra=[ai_kb.back_to_draft(lang)]))


@dp.callback_query_handler(Text(equals="ai:edit:acc"), state=AIDraft.states)
async def ask_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await show_accounts(call, state, lang, target=False)


@dp.callback_query_handler(Text(equals="ai:edit:to"), state=AIDraft.states)
async def ask_target(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await show_accounts(call, state, lang, target=True)


@dp.callback_query_handler(Text(startswith=["ai:acc:", "ai:to:"]), state=AIDraft.states)
async def set_account(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    _, field, account_id = call.data.split(":")
    account = await db.get_account(call.from_user.id, int(account_id))
    if draft is None or account is None:
        await lost(call, state, lang)
        return
    if draft.currency and account.currency != draft.currency:
        await render(call.message, state, lang, call.from_user.id)
        return
    draft.currency = account.currency
    if field == "acc":
        draft.account_id = account.id
        if draft.to_account_id == account.id:
            draft.to_account_id = None
    else:
        draft.to_account_id = account.id if account.id != draft.account_id else None
    draft.notes = [n for n in draft.notes if n != "ai_note_account_currency"]
    await replace_current(state, draft)
    await render(call.message, state, lang, call.from_user.id)


@dp.callback_query_handler(Text(equals="ai:edit:cat"), state=AIDraft.states)
async def ask_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    if draft is None or draft.kind == "transfer":
        await lost(call, state, lang)
        return
    categories = await db.list_categories(call.from_user.id, draft.kind)
    await call.message.edit_text(t("ask_new_category", lang),
                                 reply_markup=kb.choices(categories, "ai:cat", lang,
                                                         extra=[ai_kb.back_to_draft(lang)]))


@dp.callback_query_handler(Text(startswith="ai:cat:"), state=AIDraft.states)
async def set_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    category = await db.get_category(call.from_user.id, int(call.data.split(":")[2]))
    if draft is None or category is None or category.kind != draft.kind:
        await lost(call, state, lang)
        return
    draft.category, draft.subcategory = category.name, None
    await replace_current(state, draft)
    if draft.kind == "expense":
        await state.update_data(ai_category_id=category.id)
        subcategories = await db.list_subcategories(category.id)
        await call.message.edit_text(t("ask_subcategory", lang),
                                     reply_markup=kb.subcategories(subcategories, lang, prefix="ai:sub"))
        return
    await render(call.message, state, lang, call.from_user.id)


@dp.callback_query_handler(Text(startswith="ai:sub:"), state=AIDraft.states)
async def set_subcategory(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    draft = await current_draft(state)
    if draft is None:
        await lost(call, state, lang)
        return
    subcategory_id = int(call.data.split(":")[2])
    subcategory = await db.get_subcategory(call.from_user.id, subcategory_id) if subcategory_id else None
    if subcategory is not None and subcategory.category_id != (await state.get_data()).get("ai_category_id"):
        subcategory = None
    draft.subcategory = subcategory.name if subcategory else None
    await replace_current(state, draft)
    await render(call.message, state, lang, call.from_user.id)
