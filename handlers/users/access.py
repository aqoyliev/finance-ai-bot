"""Access management in the chat (the rest is on the Mini App's Users screen):

- "✅ Grant access" under the "somebody wants in" message (callback acc:grant:<user_id>);
- the contact picker: the Mini App asks the bot (POST /api/users/pick) to send a one-time reply keyboard with a
  request_users button; the shared contact comes back as `users_shared` (Bot API 7), which aiogram 2.25 does not
  know, so it is read from the raw message (the older `user_shared` is accepted too);
- "❌ Cancel" under that keyboard removes it.

Only owners and superadmins may do any of this. Registered after start / help and before legacy / AI input,
so a shared contact or the cancel text never reaches the AI.
"""
import contextlib
from typing import List, Optional

from aiogram import types
from aiogram.dispatcher.filters import Text
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.exceptions import TelegramAPIError

from loader import dp
from utils import access_notify
from utils.access_notify import GRANT_PREFIX, PICK_REQUEST_ID
from utils.db_api import access
from utils.i18n import LANGUAGES, t

CANCEL_TEXTS = frozenset(t("picker_cancel", lang, _escape=False) for lang in LANGUAGES)


async def is_manager(user_id: int) -> bool:
    return await access.role_of(user_id) in access.MANAGER_ROLES


def shared_users(message: types.Message) -> Optional[List[dict]]:
    """Users of a request_users / request_user answer to our picker: [{user_id, first_name, last_name,
    username}] (names only with users_shared), or None when the message is no such answer."""
    raw = message.to_python()
    if isinstance(raw.get("users_shared"), dict):
        data = raw["users_shared"]
        users = data.get("users")
        if not isinstance(users, list):  # early Bot API 7.0: only the ids
            users = [{"user_id": uid} for uid in data.get("user_ids") or []]
    elif isinstance(raw.get("user_shared"), dict):
        data = raw["user_shared"]
        users = [{"user_id": data.get("user_id")}]
    else:
        return None
    if data.get("request_id") != PICK_REQUEST_ID:
        return None
    return [u for u in users if isinstance(u, dict) and isinstance(u.get("user_id"), int)
            and not isinstance(u.get("user_id"), bool)]


def has_shared_users(message: types.Message) -> bool:
    return shared_users(message) is not None


async def is_picker_cancel(message: types.Message) -> bool:
    return (message.text or "").strip() in CANCEL_TEXTS and await is_manager(message.from_user.id)


def grant_name(grant) -> str:
    return grant.display_name or (f"@{grant.username}" if grant.username else str(grant.user_id))


@dp.callback_query_handler(Text(startswith=GRANT_PREFIX), state="*")
async def grant_button(call: types.CallbackQuery, lang: str):
    if not await is_manager(call.from_user.id):
        await call.answer(t("grant_not_manager", lang, _escape=False), show_alert=True)
        return
    try:
        user_id = int(call.data[len(GRANT_PREFIX):])
    except ValueError:
        await call.answer()
        return
    try:
        grant = await access.grant_by_id(user_id, call.from_user.id)
    except access.AlreadyGranted:
        await call.answer(t("grant_already", lang, _escape=False), show_alert=True)
        with contextlib.suppress(TelegramAPIError):
            await call.message.edit_reply_markup(None)
        return
    await call.answer()
    with contextlib.suppress(TelegramAPIError):
        await call.message.edit_text(t("grant_done", lang, name=grant_name(grant)))
    await access_notify.notify_granted(call.bot, user_id)


@dp.message_handler(has_shared_users, content_types=types.ContentTypes.ANY, state="*")
async def contact_shared(message: types.Message, lang: str):
    if not await is_manager(message.from_user.id):
        await message.answer(t("grant_not_manager", lang), reply_markup=ReplyKeyboardRemove())
        return
    for shared in shared_users(message):
        name = access.full_name(shared.get("first_name"), shared.get("last_name"))
        try:
            grant = await access.grant_by_id(shared["user_id"], message.from_user.id,
                                             username=shared.get("username"), display_name=name)
        except access.AlreadyGranted:
            await message.answer(t("grant_already", lang), reply_markup=ReplyKeyboardRemove())
            continue
        await message.answer(t("grant_done", lang, name=grant_name(grant)), reply_markup=ReplyKeyboardRemove())
        await access_notify.notify_granted(message.bot, shared["user_id"])


@dp.message_handler(is_picker_cancel, state="*")
async def picker_cancel(message: types.Message, lang: str):
    await message.answer(t("picker_cancelled", lang), reply_markup=ReplyKeyboardRemove())
