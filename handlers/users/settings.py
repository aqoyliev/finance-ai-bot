from decimal import Decimal, InvalidOperation

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text

from keyboards.inline import finance as kb
from loader import dp
from utils.db_api import finance as db
from utils.i18n import t


@dp.message_handler(Command("salaryday"), state="*")
async def salaryday(message: types.Message, lang: str):
    arg = message.get_args().strip()
    if not arg.isdigit() or not 1 <= int(arg) <= 28:
        await message.answer(t("salaryday_usage", lang))
        return
    await db.set_salary_day(message.from_user.id, int(arg))
    await message.answer(t("salaryday_saved", lang, day=int(arg)))


AUTO_WORDS = {"auto", "avto", "авто"}


def rate_source(info, lang: str) -> str:
    if info.source == "cbu":
        return t("rate_source_cbu", lang, date=info.day.strftime("%d.%m.%Y"))
    return t("rate_source_manual", lang)


async def rate_status(user_id: int, lang: str) -> str:
    info = await db.get_usd_rate_info(user_id)
    if info is None:
        return t("rate_unknown", lang)
    return t("rate_current", lang, rate=f"{info.rate:f}", source=rate_source(info, lang))


@dp.message_handler(Command("rate"), state="*")
async def rate_command(message: types.Message, lang: str):
    """/rate: show the rate; /rate 1 USD 12850 UZS: set a manual override; /rate auto: use the Central Bank rate."""
    args = message.get_args().split()
    user_id = message.from_user.id
    if not args:
        await message.answer(await rate_status(user_id, lang))
        return
    if len(args) == 1 and args[0].lower() in AUTO_WORDS:
        removed = await db.clear_usd_rate(user_id)
        await message.answer(t("rate_auto" if removed else "rate_auto_none", lang))
        return
    if len(args) != 4 or args[0] != "1" or args[1].upper() != "USD" or args[3].upper() != "UZS":
        await message.answer(t("rate_usage", lang))
        return
    try:
        rate = Decimal(args[2].replace(",", "."))
        if not rate.is_finite() or rate <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.answer(t("rate_invalid", lang))
        return
    await db.set_usd_rate(user_id, rate)
    await message.answer(t("rate_saved", lang, rate=rate))


async def render_settings(message: types.Message, user_id: int, lang: str, edit: bool = True):
    """Settings: accounts, budgets, history, AI advice, language (from the reply keyboard or a Back button)."""
    user = await db.get_user(user_id)
    send = message.edit_text if edit else message.answer
    await send(t("settings", lang, salary_day=user.salary_day), reply_markup=kb.settings(lang))


@dp.callback_query_handler(Text(equals="menu:settings"), state="*")
async def show_settings(call: types.CallbackQuery, state: FSMContext, lang: str):
    await call.answer()
    await state.finish()
    await render_settings(call.message, call.from_user.id, lang)


@dp.callback_query_handler(Text(equals="set:lang"), state="*")
async def change_language(call: types.CallbackQuery, lang: str):
    await call.answer()
    await call.message.edit_text(t("choose_language", lang), reply_markup=kb.languages())
