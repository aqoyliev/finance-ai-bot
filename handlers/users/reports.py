"""Period report with a receipt card, subcategory drill-down and previous / next period navigation.

The image is the receipt card (utils/cards.py); if Chromium cannot render it, the matplotlib chart is drawn
instead, and without either the report is text only. A report screen is either a text message or a photo whose
caption is the text. Changing between
the two kinds means deleting the old message and sending a new one (see show_screen).
"""
import asyncio
import contextlib
import io
import logging
from typing import Dict, Optional, Tuple

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.exceptions import TelegramAPIError

from keyboards.inline import reports as kb
from loader import bot, dp
from utils import cards
from utils.charts import render_expense_chart
from utils.db_api import finance as db
from utils.i18n import t
from utils.misc.money import money_text, short_money
from utils.misc.texts import report_text, report_title, subcategory_text

log = logging.getLogger(__name__)

HTML = types.ParseMode.HTML  # the bot default does not apply to photo captions
CAPTION_LIMIT = 1024  # Telegram's limit for a photo caption
# When the text does not fit the caption it is sent as a separate message; remember which photo belongs to
# it so that navigating away removes both. (chat_id, text message id) -> photo message id; in memory only.
_linked_photos: Dict[Tuple[int, int], int] = {}
_MAX_LINKED = 100


async def make_image(user_id: int, report: db.PeriodReport, lang: str) -> Optional[bytes]:
    """The report card; the matplotlib chart if the card cannot be rendered; None for text only."""
    card = await cards.report_card(user_id, report, lang)
    return card if card is not None else await make_chart(report, lang)


async def make_chart(report: db.PeriodReport, lang: str) -> Optional[bytes]:
    """Fallback PNG of expenses by category, or None if there is nothing to draw or drawing failed."""
    series = report.chart_series()
    if series is None:
        return None
    currency, items, converted = series
    label = f"{currency} (USD → UZS)" if converted else currency
    title = t("report_chart_title", lang, currency=label, _escape=False)
    amount = money_text(sum(value for _, value in items), currency).replace(".00 ", " ")
    total = t("report_chart_total", lang, amount=amount, _escape=False)  # drawn as two lines in the donut
    try:
        # matplotlib is CPU-bound: keep it off the event loop
        return await asyncio.to_thread(render_expense_chart, items, title, total,
                                       t("report_chart_other", lang), short_money)
    except Exception:  # noqa: BLE001 - the text report is still useful without a chart
        log.exception("Could not render the expense chart")
        return None


async def show_screen(message: types.Message, text: str, markup: types.InlineKeyboardMarkup,
                      chart: Optional[bytes] = None, caption: str = "", replace: bool = True) -> None:
    """Show a report screen in place of `message` (the one an inline button was pressed on).

    Text on a text message is edited in place; anything involving a photo deletes the old message(s) and
    sends a new one. A photo carries the text as its caption when it fits, otherwise `caption` (a short
    title) and the text with the keyboard follows as a separate message. With replace=False (opened from
    the reply keyboard) nothing is edited or deleted, the screen is simply sent."""
    chat_id = message.chat.id
    if replace:
        linked = _linked_photos.pop((chat_id, message.message_id), None)
        if linked:
            with contextlib.suppress(TelegramAPIError):
                await bot.delete_message(chat_id, linked)

    if chart is None:
        if not replace:
            await bot.send_message(chat_id, text, reply_markup=markup)
        elif message.photo:
            with contextlib.suppress(TelegramAPIError):
                await message.delete()
            await bot.send_message(chat_id, text, reply_markup=markup)
        else:
            await message.edit_text(text, reply_markup=markup)
        return

    if replace:
        with contextlib.suppress(TelegramAPIError):
            await message.delete()
    photo = types.InputFile(io.BytesIO(chart), filename="report.png")
    if len(text) <= CAPTION_LIMIT:
        await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode=HTML)
        return
    photo_message = await bot.send_photo(chat_id, photo, caption=caption, parse_mode=HTML)
    text_message = await bot.send_message(chat_id, text, reply_markup=markup)
    if len(_linked_photos) >= _MAX_LINKED:
        _linked_photos.pop(next(iter(_linked_photos)))
    _linked_photos[(chat_id, text_message.message_id)] = photo_message.message_id


async def category_ids(user_id: int) -> Dict[str, int]:
    return {c.name: c.id for c in await db.list_categories(user_id, "expense")}


@dp.callback_query_handler(Text(startswith="rep:"), state="*")
async def navigate_report(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await render_report(call.message, call.from_user.id, min(int(call.data.split(":")[1]), 0), lang)


async def render_report(message: types.Message, user_id: int, offset: int, lang: str, replace: bool = True):
    """The report of a period (0 = running); replace=False sends it as new messages (reply keyboard)."""
    report = await db.build_period_report(user_id, offset)
    text = report_text(report, lang)
    if report.has_data:
        text += "\n\n" + t("report_tap_category", lang)
    markup = kb.report_view(report, await category_ids(user_id), lang)
    chart = await make_image(user_id, report, lang)
    await show_screen(message, text, markup, chart, caption=report_title(report, lang), replace=replace)


@dp.callback_query_handler(Text(startswith="repc:"), state="*")
async def show_category(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    _, offset, category_id = call.data.split(":")
    offset = min(int(offset), 0)
    category = await db.get_category(call.from_user.id, int(category_id))
    if category is None:
        await render_report(call.message, call.from_user.id, offset, lang)
        return
    report = await db.build_period_report(call.from_user.id, offset)
    by_currency = await db.expense_by_subcategory(call.from_user.id, category.name, report.start, report.end)
    await show_screen(call.message, subcategory_text(report, category.name, by_currency, lang),
                      kb.subcategory_view(offset, lang))
