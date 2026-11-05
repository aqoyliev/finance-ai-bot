"""AI input without confirmation, the saved-operation card and the bot surface (/start, /help, hints to the Mini App)."""
from datetime import datetime

import pytest
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

from utils.ai import parser
from utils.db_api import finance as db
from utils.i18n import LANGUAGES, t
from utils.misc.texts import CARD_SEPARATOR, card_amount, card_time, operation_card

from test_services import USER, balance, setup_user


# ---- Saved operation card ----

async def test_expense_card_layout():
    cash, card, credit, usd = await setup_user()
    saved = await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 2_500_000)], category="Transport",
                                      subcategory="Taxi", note="taxi <home>",
                                      occurred_at=datetime(2026, 11, 4, 22, 15))
    text = operation_card(saved, "uz")
    assert text.split("\n") == [
        "💸 <b>XARAJAT</b>", CARD_SEPARATOR,
        "💰 <b>Summa:</b> 25 000 soʻm",
        "🏷 <b>Kategoriya:</b> Transport › Taxi",
        "💳 <b>To'lov:</b> Wallet",
        "🕐 <b>Vaqt:</b> 04 Noy, 22:15",
        CARD_SEPARATOR,
        "📝 taxi &lt;home&gt;",
    ]


async def test_income_and_transfer_cards_without_note():
    cash, card, credit, usd = await setup_user()
    income = await db.record_operation(USER, "income", "USD", [db.Leg(usd.id, 1_250)], category="Salary",
                                       occurred_at=datetime(2026, 1, 2, 9, 5))
    text = operation_card(income, "en")
    assert text.startswith("💰 <b>INCOME</b>") and "12.50 USD" in text and "<b>Account:</b> Dollars" in text
    assert "02 Jan, 09:05" in text and "📝" not in text and text.endswith(CARD_SEPARATOR)

    transfer = await db.record_transfer(USER, card.id, credit.id, 100_000)
    text = operation_card(transfer, "ru")
    assert text.startswith("🔁 <b>ПЕРЕВОД</b>")
    assert "<b>Откуда:</b> Card" in text and "<b>Куда:</b> Visa" in text and "1 000 сум" in text
    assert "Категория" not in text


def test_card_helpers_in_every_language():
    moment = datetime(2026, 5, 9, 7, 3)
    for lang in LANGUAGES:
        assert len(t("months_short", lang).split()) == 12
        assert card_time(moment, lang).startswith("09 ") and card_time(moment, lang).endswith(", 07:03")
        for key in ("opcard_expense", "opcard_income", "opcard_transfer"):
            assert t(key, lang).startswith(("💸", "💰", "🔁"))
    assert card_amount(123_456_789, "UZS", "en") == "1 234 567.89 UZS"
    assert card_amount(100_000_000, "UZS", "ru") == "1 000 000 сум"


# ---- Fallback category ----

async def test_fallback_category_reuses_or_creates():
    await setup_user("en")  # seeded with "Other" / "Other income"
    assert await db.fallback_category(USER, "expense", "en") == "Other"
    assert await db.fallback_category(USER, "expense", "uz") == "Other"  # any language's name is reused
    assert await db.fallback_category(USER, "income", "ru") == "Other income"


async def test_fallback_category_created_once_when_missing():
    await db.set_language(USER, "owner", "uz")
    await db.create_account(USER, "Naqd", "cash", "UZS", opening_minor=0)
    from sqlalchemy import delete
    from utils.db_api.base import session_factory
    from utils.db_api.models import Category
    async with session_factory() as session, session.begin():
        await session.execute(delete(Category).where(Category.name == "Boshqa"))
    assert await db.fallback_category(USER, "expense", "uz") == "Boshqa"
    assert await db.fallback_category(USER, "expense", "uz") == "Boshqa"
    names = [c.name for c in await db.list_categories(USER, "expense")]
    assert names.count("Boshqa") == 1


def test_input_type():
    assert parser.input_type({"input_type": "bank_sms"}) == "bank_sms"
    assert parser.input_type({"input_type": "weird"}) == "other" and parser.input_type(None) == "other"


# ---- AI input: save at once, ask only for the account ----

class FakeMessage:
    def __init__(self):
        self.sent = []  # (text, markup)

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.sent.append((text, reply_markup))

    async def answer(self, text, reply_markup=None, **kwargs):
        self.sent.append((text, reply_markup))

    async def delete(self):
        self.deleted = True


@pytest.fixture
def flow(monkeypatch):
    from handlers.users import ai_input

    alerts = []

    async def fake_alerts(user_id, lang, *saved):
        alerts.append(saved)

    monkeypatch.setattr(ai_input, "send_alerts", fake_alerts)
    state = FSMContext(MemoryStorage(), chat=USER, user=USER)
    return ai_input, state, alerts


async def test_resolved_account_is_saved_at_once_with_fallback_category(flow):
    ai_input, state, alerts = flow
    cash, card, credit, usd = await setup_user()
    msg = FakeMessage()
    drafts = [parser.Draft(kind="expense", amount_minor=1_800_000, currency="UZS", account_id=cash.id, note="cafe")]
    await ai_input.process(ai_input.Replier(msg, edit_first=True), state, "en", USER, drafts)
    [(text, markup)] = msg.sent
    assert text.startswith("💸 <b>EXPENSE</b>") and "<b>Category:</b> Other" in text
    assert markup is None and not getattr(msg, "deleted", False)  # no reply keyboard: the status message is edited
    assert await balance(cash.id) == 100_000 - 1_800_000
    assert len(alerts) == 1 and await state.get_state() is None
    [view] = await db.recent_operations(USER)
    assert view.tx.source == "ai" and view.tx.category == "Other"


async def test_missing_account_asked_once_for_all_and_applied(flow, webapp_on):
    ai_input, state, alerts = flow
    cash, card, credit, usd = await setup_user()
    msg = FakeMessage()
    drafts = [
        parser.Draft(kind="expense", amount_minor=2_500_000, currency="UZS", category="Transport", subcategory="Taxi"),
        parser.Draft(kind="expense", amount_minor=1_000_000, category="Health"),
        parser.Draft(kind="expense", amount_minor=500_000, currency="UZS", category="Health", account_id=card.id),
        parser.Draft(kind="expense", category="Health", account_id=card.id),  # no amount
    ]
    await ai_input.process(ai_input.Replier(msg, edit_first=True), state, "en", USER, drafts)
    texts = [text for text, _ in msg.sent]
    assert texts[0].startswith("💸") and "5 000 UZS" in texts[0]  # the complete one is saved at once
    assert "could not find an amount" in texts[1]
    question, markup = msg.sent[2]
    assert question.startswith("💳 Which payment method?") and "25 000 UZS — Transport › Taxi" in question
    assert t("ai_new_card_hint", "en") in question
    buttons = [b.callback_data for row in markup.inline_keyboard[:-1] for b in row]
    assert buttons == [f"ai:acc:{a.id}" for a in await db.list_accounts(USER)]
    last = markup.inline_keyboard[-1][0]  # last: add a card in the Mini App
    assert last.callback_data is None and last.web_app.url == "https://finance.example.com/#/new"
    assert await state.get_state() == "AIDraft:account"

    answer = FakeMessage()
    await ai_input.apply_account(ai_input.Replier(answer, edit_first=True), state, "en", USER, cash)
    assert [text.split("\n")[0] for text, _ in answer.sent] == ["💸 <b>EXPENSE</b>", "💸 <b>EXPENSE</b>"]
    assert "<b>Paid with:</b> Wallet" in answer.sent[0][0]
    assert await balance(cash.id) == 100_000 - 3_500_000
    assert await state.get_state() is None and len(alerts) == 2


async def test_same_input_is_not_saved_twice_but_similar_is_warned(flow):
    ai_input, state, alerts = flow
    cash, card, credit, usd = await setup_user()
    sms = dict(kind="expense", amount_minor=2_500_000, currency="UZS", category="Transport", account_id=card.id)
    first = FakeMessage()
    await ai_input.process(ai_input.Replier(first, edit_first=True), state, "en", USER,
                           [parser.Draft(**sms, source_ref="sms-1")])
    again = FakeMessage()
    await ai_input.process(ai_input.Replier(again, edit_first=True), state, "en", USER,
                           [parser.Draft(**sms, source_ref="sms-1")])
    assert "already saved" in again.sent[0][0]
    typed = FakeMessage()
    await ai_input.process(ai_input.Replier(typed, edit_first=True), state, "en", USER, [parser.Draft(**sms)])
    assert typed.sent[0][0].startswith("💸") and "a few minutes ago" in typed.sent[0][0]
    assert len(await db.recent_operations(USER)) == 2


async def test_typed_account_name_answers_the_question(flow, monkeypatch):
    ai_input, state, alerts = flow
    cash, card, credit, usd = await setup_user()
    await ai_input.process(ai_input.Replier(FakeMessage(), edit_first=True), state, "en", USER,
                           [parser.Draft(kind="expense", amount_minor=100_000, currency="UZS", category="Health")])

    class Typed(FakeMessage):
        text = "wallet"
        from_user = type("U", (), {"id": USER})()

    message = Typed()
    assert await ai_input.typed_account(message, state, "en") is True
    assert message.sent[0][0].startswith("💸") and await balance(cash.id) == 0
    message.text = "taxi 25000"  # a new operation is not taken for an account name
    assert await ai_input.typed_account(message, state, "en") is False


# ---- Bot surface: /start and /help only, the rest is in the Mini App ----

@pytest.fixture
def webapp_on(monkeypatch):
    from data import config

    monkeypatch.setattr(config, "WEBAPP_URL", "https://finance.example.com")
    monkeypatch.setattr(config, "WEBAPP_ENABLED", True)


def test_only_start_and_help_commands():
    from utils.set_bot_commands import COMMANDS

    assert COMMANDS == ("start", "help")
    for name in COMMANDS:
        assert all(t(f"cmd_{name}", lang) for lang in LANGUAGES)


async def test_set_commands_deletes_stale_ones_for_every_language():
    from types import SimpleNamespace

    from utils.set_bot_commands import set_default_commands

    calls = []

    class FakeBot:
        async def delete_my_commands(self, scope=None, language_code=None):
            calls.append(("delete", language_code))

        async def set_my_commands(self, commands, scope=None, language_code=None):
            calls.append(("set", language_code, [c.command for c in commands]))

    await set_default_commands(SimpleNamespace(bot=FakeBot()))
    codes = [None] + list(LANGUAGES)
    assert [c for c in calls if c[0] == "delete"] == [("delete", code) for code in codes]
    assert [c for c in calls if c[0] == "set"] == [("set", code, ["start", "help"]) for code in codes]
    assert calls.index(("delete", "en")) < calls.index(("set", None, ["start", "help"]))


def test_handler_order_and_removed_modules():
    import importlib

    from loader import dp
    import handlers  # noqa: F401  (registers everything in order)

    for gone in ("menu", "settings", "finance", "transfer", "accounts", "reports", "budgets", "operations", "advice"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"handlers.users.{gone}")
    names = [h.handler.__module__ + "." + h.handler.__name__ for h in dp.message_handlers.handlers]
    legacy = names.index("handlers.users.legacy.moved_to_app")
    assert legacy < names.index("handlers.users.ai_input.text_input") < names.index("handlers.users.echo.bot_fallback")
    callbacks = [h.handler.__module__ + "." + h.handler.__name__ for h in dp.callback_query_handlers.handlers]
    assert callbacks[-1] == "handlers.users.echo.stale_button"
    assert "handlers.users.ai_input.choose_account" in callbacks


def test_old_reply_keyboard_texts_are_recognized_exactly():
    from handlers.users.legacy import OLD_COMMANDS, is_old_keyboard_text

    class Msg:
        def __init__(self, text):
            self.text = text

    for text in ("📊 Hisobot", "💳 Balans", "⚙️ Sozlamalar", "📊 Отчёт", "💳 Баланс", "⚙️ Настройки", "📊 Report",
                 "💳 Balance", "⚙️ Settings"):
        assert is_old_keyboard_text(Msg(text)), text
    # plain words are no longer a menu: they go to the AI like any other text
    for text in ("settings", "hisobot", "отчет", "taxi 25000", None):
        assert not is_old_keyboard_text(Msg(text))
    assert {"expense", "income", "transfer", "salaryday", "rate", "report", "balance", "settings"} == set(OLD_COMMANDS)


class Chat(FakeMessage):
    """A message that can be edited after it was sent (start text -> attach the app button)."""

    def __init__(self, fail_edit=False):
        super().__init__()
        self.fail_edit = fail_edit
        self.from_user = type("U", (), {"id": USER})()
        self.edited = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.sent.append((text, reply_markup))
        outer = self

        class Sent:
            async def edit_reply_markup(self, markup):
                if outer.fail_edit:
                    from aiogram.utils.exceptions import MessageCantBeEdited
                    raise MessageCantBeEdited("Message can't be edited")
                outer.edited.append(markup)

        return Sent()


async def test_start_removes_the_reply_keyboard_and_attaches_the_app_button(webapp_on):
    from aiogram.types import ReplyKeyboardRemove

    from handlers.users.start import send_start

    msg = Chat()
    await send_start(msg, "uz")
    [(text, markup)] = msg.sent
    assert text == t("start", "uz") and isinstance(markup, ReplyKeyboardRemove)
    [app] = msg.edited
    button = app.inline_keyboard[0][0]
    assert button.text == "📱 Ilovani ochish" and button.web_app.url == "https://finance.example.com/"

    refused = Chat(fail_edit=True)  # Telegram refused the edit: the button comes in a second message
    await send_start(refused, "en")
    assert len(refused.sent) == 2 and refused.sent[1][1].inline_keyboard[0][0].text == "📱 Open the app"


async def test_start_without_mini_app_has_no_button(monkeypatch):
    from data import config
    from handlers.users.start import send_start

    monkeypatch.setattr(config, "WEBAPP_ENABLED", False)
    msg = Chat()
    await send_start(msg, "ru")
    assert len(msg.sent) == 1 and not msg.edited


def test_start_and_help_texts_point_to_the_app():
    for lang in LANGUAGES:
        for key in ("start", "help", "moved_to_app"):
            text = t(key, lang)
            assert "📱" in text
            for gone in ("/expense", "/income", "/transfer", "/salaryday", "/rate", "/report", "/balance",
                         "/settings"):
                assert gone not in text, (key, lang, gone)
        assert len(t("help", lang)) > len(t("start", lang))


async def test_old_command_and_stale_button_get_the_hint(webapp_on):
    from handlers.users import echo, legacy

    msg = Chat()
    await legacy.moved_to_app(msg, "en")
    [(text, markup)] = msg.sent
    assert text == t("moved_to_app", "en") and markup.inline_keyboard[0][0].web_app is not None

    answered = []

    class Call:
        message = Chat()

        async def answer(self):
            answered.append(True)

    call = Call()
    await echo.stale_button(call, "uz")
    assert answered and call.message.sent[0][0] == t("moved_to_app", "uz")


def test_advice_settings_button_opens_the_app(webapp_on):
    from keyboards.inline import app as kb

    markup = kb.open_app("en", kb.SETTINGS, "btn_advice_settings")
    assert markup.inline_keyboard[0][0].web_app.url == "https://finance.example.com/#/settings"


def test_app_buttons_need_an_https_url(monkeypatch):
    from data import config
    from keyboards.inline import app as kb

    monkeypatch.setattr(config, "WEBAPP_ENABLED", False)
    assert kb.open_app("uz") is None and kb.app_button("x", kb.NEW_CARD) is None


def test_default_account_is_only_cash():
    from utils.db_api.defaults import DEFAULT_ACCOUNTS

    for lang in LANGUAGES:
        assert len(DEFAULT_ACCOUNTS[lang]) == 1 and DEFAULT_ACCOUNTS[lang][0][1:] == ("cash", "UZS")


async def test_new_user_gets_one_cash_account():
    await db.set_language(USER + 5, "new", "uz")
    accounts = await db.list_accounts(USER + 5)
    assert [(a.name, a.currency) for a in accounts] == [("Naqd pul", "UZS")]


async def test_only_one_account_saves_without_asking(flow):
    ai_input, state, alerts = flow
    await db.set_language(USER, "owner", "uz")
    [cash] = await db.list_accounts(USER)
    msg = FakeMessage()
    await ai_input.process(ai_input.Replier(msg, edit_first=True), state, "uz", USER,
                           [parser.Draft(kind="expense", amount_minor=1_100_000, currency="UZS")])
    assert len(msg.sent) == 1 and msg.sent[0][0].startswith("💸")
    assert await state.get_state() is None and len(alerts) == 1
    assert await balance(cash.id) == -1_100_000


async def _pending(ai_input, state):
    cash, card, credit, usd = await setup_user()
    await ai_input.process(ai_input.Replier(FakeMessage(), edit_first=True), state, "en", USER,
                           [parser.Draft(kind="expense", amount_minor=100_000, currency="UZS", category="Health")])
    return cash


class Typed(FakeMessage):
    text = ""
    from_user = type("U", (), {"id": USER})()


async def test_text_that_is_not_an_account_gets_a_hint_not_nothing_found(flow):
    ai_input, state, alerts = flow
    cash = await _pending(ai_input, state)
    message = Typed()
    message.text = "I do not have such cards"
    assert await ai_input.typed_account(message, state, "en") is True
    assert message.sent[0][0] == t("ai_pick_account", "en") and await state.get_state() == "AIDraft:account"
    message.text = "x" * 60  # long text without digits
    assert await ai_input.typed_account(message, state, "en") is True
    message.text = "coffee 18000"  # a new operation: handled by the analysis
    assert await ai_input.typed_account(message, state, "en") is False
    assert await balance(cash.id) == 100_000


async def test_question_without_mini_app_has_account_buttons_only(flow, monkeypatch):
    from data import config

    monkeypatch.setattr(config, "WEBAPP_ENABLED", False)
    ai_input, state, alerts = flow
    await _pending(ai_input, state)
    message = Typed()
    await ai_input.hint_account(message, state, "en")
    [(text, markup)] = message.sent
    assert text == t("ai_pick_account", "en")
    assert all(b.callback_data.startswith("ai:acc:") for row in markup.inline_keyboard for b in row)


async def test_question_has_add_card_button_last(flow, webapp_on):
    ai_input, state, alerts = flow
    await _pending(ai_input, state)
    message = Typed()
    await ai_input.hint_account(message, state, "en")
    [(text, markup)] = message.sent
    last = markup.inline_keyboard[-1][0]
    assert last.text == t("btn_ai_new_account", "en") and last.web_app.url.endswith("#/new")


async def test_card_added_in_the_app_then_typed_receives_the_waiting_operation(flow):
    """The pending operation survives adding a card in the Mini App: typing the new card's name saves it."""
    ai_input, state, alerts = flow
    await _pending(ai_input, state)
    new = await db.create_account(USER, "Kapital", "debit", "UZS", opening_minor=500_000, card_type="uzcard",
                                  last4="4417")
    message = Typed()
    message.text = "kapital"
    assert await ai_input.typed_account(message, state, "en") is True
    assert message.sent[0][0].startswith("💸") and "Kapital" in message.sent[0][0]
    assert await balance(new.id) == 400_000 and await state.get_state() is None and len(alerts) == 1


async def test_nothing_found_reply_has_no_keyboard(flow):
    ai_input, state, alerts = flow
    msg = FakeMessage()
    await ai_input.Replier(msg, edit_first=True)(t("ai_nothing_found", "uz"))
    assert msg.sent == [(t("ai_nothing_found", "uz"), None)]
