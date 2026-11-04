"""Helpers shared by the AI handlers (AI input, Ask AI, advice)."""
import asyncio
import contextlib

from aiogram import types

from loader import bot
from utils.ai import core as ai
from utils.i18n import TEXTS, t


def error_text(code: str, lang: str, prefix: str = "ai_error_") -> str:
    """Localized message of an AIError code; `prefix` selects feature-specific wording when it exists.

    {env_key} in a message is the API key variable of the configured provider
    (GEMINI_API_KEY / ANTHROPIC_API_KEY)."""
    env_key = getattr(ai.get_client(), "key_name", "API key")
    if code == "not_configured":
        return t("ai_not_configured", lang, env_key=env_key)
    for key in (f"{prefix}{code}", f"ai_error_{code}"):
        if key in TEXTS:
            return t(key, lang, env_key=env_key)
    return t("ai_error_unavailable", lang, env_key=env_key)


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
