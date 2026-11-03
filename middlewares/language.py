from aiogram import types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware

from keyboards.inline.finance import languages
from utils.db_api import finance as db
from utils.i18n import guess_language, t


def is_start_command(message: types.Message) -> bool:
    return (message.text or "").split("@")[0].split(" ")[0] == "/start"


class LanguageMiddleware(BaseMiddleware):
    """Puts the user's language into handler data as `lang`.

    Until a language is chosen only /start and the language buttons are processed;
    everything else gets the language picker.
    """

    async def on_pre_process_message(self, message: types.Message, data: dict):
        if not await self._resolve(message.from_user, data) and not is_start_command(message):
            await message.answer(t("choose_language", data["lang"]), reply_markup=languages())
            raise CancelHandler()

    async def on_pre_process_callback_query(self, call: types.CallbackQuery, data: dict):
        if not await self._resolve(call.from_user, data) and not (call.data or "").startswith("lang:"):
            await call.answer()
            await call.message.answer(t("choose_language", data["lang"]), reply_markup=languages())
            raise CancelHandler()

    @staticmethod
    async def _resolve(user: types.User, data: dict) -> bool:
        """Set data['lang']; return False if the user has not chosen a language yet."""
        lang = await db.get_language(user.id)
        data["lang"] = lang or guess_language(user.language_code)
        return lang is not None
