"""Automatic AI advice: weekly every Monday at 09:00 and monthly on the first day of a new financial period
at 09:00 (Asia/Tashkent, the bot's local time).

aiogram 2 has no scheduler, and two daily checks do not justify a dependency: a single asyncio task (started
in app.on_startup) wakes up every TICK_SECONDS and asks `due()` what to send. It is restart-safe because what
was handled is stored on the User row (advice_weekly_sent = that Monday, advice_monthly_sent = that period
start): a restart never sends twice, and if the bot was down at 09:00 the advice goes out on the first tick
after start on the same day (a day missed completely is skipped, not sent late). A window with no income or
expense is marked as handled without calling the AI. A failed AI call is retried after RETRY_AFTER, at most
MAX_ATTEMPTS times per day (the counter is in memory). Turning a kind off only stops future sends.

Every advice comes with the matching receipt card (utils/cards.py) as a photo; the advice text is its caption when
it fits Telegram's caption limit, otherwise the photo carries the title and the text follows as a message. Without
a card (the card and the fallback chart both failed) the advice is sent as text only, as before.
"""
import asyncio
import contextlib
import io
import logging
from datetime import date, datetime, time, timedelta
from html import escape
from typing import Dict, List, Optional, Tuple

from aiogram import types
from aiogram.utils.exceptions import TelegramAPIError

from keyboards.inline import ai as ai_kb
from loader import bot
from utils import cards
from utils.ai import assistant
from utils.ai import core as ai
from utils.db_api import finance as db
from utils.i18n import t

log = logging.getLogger(__name__)

SEND_AT = time(9, 0)
TICK_SECONDS = 60
RETRY_AFTER = timedelta(minutes=20)
MAX_ATTEMPTS = 3
MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024  # Telegram's limit for a photo caption
HTML = types.ParseMode.HTML  # the bot default does not apply to photo captions


def due(user, now: datetime) -> List[Tuple[str, date]]:
    """[(kind, day)] to send to `user` at local time `now`; monthly first when both fall on the same day."""
    if now.time() < SEND_AT:
        return []
    today = now.date()
    result = []
    if user.advice_monthly and db.period_start(user.salary_day, today) == today \
            and user.advice_monthly_sent != today:
        result.append(("monthly", today))
    if user.advice_weekly and today.weekday() == 0 and user.advice_weekly_sent != today:
        result.append(("weekly", today))
    return result


def advice_header(result: assistant.Advice, kind: str, lang: str) -> str:
    return t(f"advice_title_{kind}", lang, start=result.start.strftime("%d.%m"),
             end=result.last_day.strftime("%d.%m.%Y"))


def advice_message(result: assistant.Advice, kind: str, lang: str) -> str:
    """Localized header plus the (escaped) advice text, within Telegram's message limit."""
    header = advice_header(result, kind, lang)
    body = escape(result.text, quote=False)
    room = MESSAGE_LIMIT - len(header) - 2
    if len(body) > room:
        body = body[:room - 1].rstrip() + "…"
    return f"{header}\n\n{body}"


async def send_advice(chat_id: int, text: str, header: str, card: Optional[bytes], markup) -> None:
    """The advice with its card: the text as the photo caption if it fits, else the photo titled `header` followed
    by the text with the keyboard. Without a card, or if Telegram rejects the photo, text only."""
    if card is not None:
        photo = types.InputFile(io.BytesIO(card), filename="advice.png")
        try:
            if len(text) <= CAPTION_LIMIT:
                await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode=HTML)
                return
            await bot.send_photo(chat_id, photo, caption=header, parse_mode=HTML)
        except TelegramAPIError as err:
            log.warning("Advice card was not sent to %s: %s", chat_id, err)
    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=HTML)


class AdviceScheduler:
    def __init__(self):
        self._failures: Dict[Tuple[int, str, date], Tuple[int, datetime]] = {}
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    async def deliver(self, user, kind: str, day: date) -> bool:
        """Generate and send one advice; marks it handled. Returns False if the window was empty."""
        result = await assistant.advice(user.id, kind, user.language, today=day)
        if result is not None:
            card = await cards.advice_card(user.id, kind, user.language, today=day)
            await send_advice(user.id, advice_message(result, kind, user.language),
                              advice_header(result, kind, user.language), card,
                              ai_kb.after_advice(user.language, settings=True))
        await db.mark_advice_sent(user.id, kind, day)
        return result is not None

    async def tick(self, now: Optional[datetime] = None) -> List[Tuple[int, str]]:
        """One check of every user. Returns [(user_id, kind)] actually sent."""
        now = now or db.now()
        sent = []
        if not ai.get_client().configured:
            return sent
        async with self._lock:
            for user in await db.list_users():
                for kind, day in due(user, now):
                    key = (user.id, kind, day)
                    attempts, retry_at = self._failures.get(key, (0, now))
                    if attempts >= MAX_ATTEMPTS or now < retry_at:
                        continue
                    try:
                        if await self.deliver(user, kind, day):
                            sent.append((user.id, kind))
                        self._failures.pop(key, None)
                    except (ai.AIError, TelegramAPIError) as err:
                        log.warning("%s advice for %s failed (attempt %d): %s", kind, user.id, attempts + 1, err)
                        self._failures[key] = (attempts + 1, now + RETRY_AFTER)
                    except Exception:  # noqa: BLE001 - one user's failure must not stop the loop
                        log.exception("%s advice for %s failed", kind, user.id)
                        self._failures[key] = (attempts + 1, now + RETRY_AFTER)
        return sent

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("Advice scheduler tick failed")
            await asyncio.sleep(TICK_SECONDS)

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


scheduler = AdviceScheduler()
