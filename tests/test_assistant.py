"""Ask AI tools, the tool loop, advice and its scheduler, intent routing and the chart centre text.

The Anthropic SDK is always faked; no network calls are made.
"""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from utils import advice_scheduler as sched
from utils import charts
from utils.ai import assistant, claude, parser, tools
from utils.db_api import finance as db
from utils.db_api import reports as rep
from utils.misc.money import short_money
from utils.misc.texts import split_message

from test_services import USER, setup_user


# ---- Helpers ----

def block(kind, **fields):
    return SimpleNamespace(type=kind, **fields)


def text(value):
    return block("text", text=value)


def thinking(signature="sig"):
    return block("thinking", thinking="", signature=signature)


def tool_use(name, input_=None, id_="tu_1"):
    return block("tool_use", id=id_, name=name, input=input_ or {})


def response(*content, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=list(content))


class FakeMessages:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fake_client(*results, fallbacks=True):
    messages = FakeMessages(*results)
    sdk = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))
    return claude.ClaudeClient("", "haiku-x", "claude-opus-5-5", client=sdk, fallbacks=fallbacks), messages


def now():
    return db.now()


async def run(name, **arguments):
    content, is_error = await tools.run_tool(USER, name, arguments)
    return json.loads(content), is_error


async def seed():
    """Current period: UZS expenses + income, a USD expense, a transfer; previous period: one expense."""
    cash, card, credit, usd = await setup_user()
    stamp = now() - timedelta(minutes=5)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 3_000_000)], "Transport", "Taxi",
                              note="Yandex Go ride", occurred_at=stamp)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(card.id, 1_000_000)], "Health", None,
                              occurred_at=stamp - timedelta(minutes=1))
    await db.record_operation(USER, "income", "UZS", [db.Leg(card.id, 9_000_000)], "Salary", occurred_at=stamp)
    await db.record_operation(USER, "expense", "USD", [db.Leg(usd.id, 2_500)], "Transport", "Taxi",
                              occurred_at=stamp)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(credit.id, 500_000)], "Transport", "Fuel",
                              occurred_at=stamp - timedelta(minutes=2))
    await db.record_transfer(USER, card.id, credit.id, 400_000, note="repay", occurred_at=stamp)
    start = db.period_start(1, now().date())
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 2_000_000)], "Transport", "Taxi",
                              occurred_at=datetime.combine(start - timedelta(days=1), datetime.min.time()))
    return cash, card, credit, usd


# ---- Tools ----

def test_tool_definitions_are_strict():
    assert len(tools.TOOLS) == len(set(tools.TOOL_NAMES)) == 7
    for tool in tools.TOOLS:
        schema = tool["input_schema"]
        assert tool["strict"] is True and schema["additionalProperties"] is False
        assert schema["required"] == list(schema["properties"])
        assert tool["description"]
    dumped = json.dumps(tools.TOOLS)
    assert "minimum" not in dumped and "nullable" not in dumped


async def test_period_summary_excludes_transfers_and_splits_currencies():
    await seed()
    result, is_error = await run("get_period_summary", period_offset=0)
    assert not is_error
    uzs, usd = result["currencies"]
    assert (uzs["currency"], uzs["income"], uzs["expense"], uzs["balance"]) == ("UZS", 90_000, 45_000, 45_000)
    top = uzs["expenses_by_category"][0]
    assert (top["category"], top["amount"], top["share_pct"]) == ("Transport", 35_000, 78)
    assert (usd["currency"], usd["expense"]) == ("USD", 25) and "income" in usd
    assert result["period"]["is_current"] is True and "combined_in_uzs" not in result

    await db.set_usd_rate(USER, Decimal("12500"))
    result, _ = await run("get_period_summary", period_offset=0)
    assert result["combined_in_uzs"]["expense"] == 45_000 + 312_500

    previous, _ = await run("get_period_summary", period_offset=-1)
    assert previous["currencies"][0]["expense"] == 20_000 and previous["period"]["is_current"] is False


async def test_period_summary_rejects_bad_offsets():
    await setup_user()
    for value in (1, "0", True, -1000):
        result, is_error = await run("get_period_summary", period_offset=value)
        assert is_error and "period_offset" in result["error"]


async def test_category_breakdown():
    await seed()
    result, is_error = await run("get_category_breakdown", category="transport", period_offset=0)
    assert not is_error and result["category"] == "Transport"
    by_currency = {c["currency"]: c for c in result["currencies"]}
    assert by_currency["UZS"]["total"] == 35_000
    assert by_currency["UZS"]["subcategories"] == [
        {"subcategory": "Taxi", "amount": 30_000, "share_pct": 86}, {"subcategory": "Fuel", "amount": 5_000,
                                                                     "share_pct": 14}]
    assert by_currency["USD"]["total"] == 25
    result, is_error = await run("get_category_breakdown", category="Casino", period_offset=0)
    assert is_error and "Transport" in result["error"]


async def test_search_transactions_filters_and_transfers():
    cash, card, credit, usd = await seed()
    result, _ = await run("search_transactions", date_from=None, date_to=None, kind=None, category=None,
                          account=None, text=None, min_amount=None, max_amount=None, limit=None)
    assert result["count"] == 7  # the transfer is listed once (outgoing leg)
    transfer = next(t for t in result["transactions"] if t["kind"] == "transfer")
    assert transfer["account"] == "Card" and transfer["to_account"] == "Visa" and transfer["amount"] == 4_000

    result, _ = await run("search_transactions", date_from=None, date_to=None, kind="expense", category="taxi",
                          account=None, text=None, min_amount=None, max_amount=None, limit=1)
    assert result["count"] == 3 and result["listed"] == 1
    assert {(t["kind"], t["currency"]): t["amount"] for t in result["totals"]} == {
        ("expense", "UZS"): 50_000, ("expense", "USD"): 25}

    result, _ = await run("search_transactions", date_from=None, date_to=None, kind=None, category=None,
                          account="vis", text=None, min_amount=None, max_amount=None, limit=None)
    assert {t["kind"] for t in result["transactions"]} == {"expense", "transfer"}  # fuel + repayment

    today = now().date().isoformat()
    result, _ = await run("search_transactions", date_from=today, date_to=today, kind=None, category=None,
                          account=None, text="YANDEX", min_amount=10_000, max_amount=30_000, limit=None)
    assert result["count"] == 1 and result["transactions"][0]["note"] == "Yandex Go ride"

    result, is_error = await run("search_transactions", date_from="2026-13-01", date_to=None, kind=None,
                                 category=None, account=None, text=None, min_amount=None, max_amount=None,
                                 limit=None)
    assert is_error
    result, is_error = await run("search_transactions", date_from=None, date_to=None, kind=None, category=None,
                                 account="nope", text=None, min_amount=None, max_amount=None, limit=None)
    assert is_error and "Wallet" in result["error"]


async def test_accounts_budgets_rate_and_categories():
    await seed()
    await db.set_budget(USER, "Transport", "UZS", 4_000_000)
    accounts, _ = await run("get_accounts")
    visa = next(a for a in accounts["accounts"] if a["name"] == "Visa")
    assert visa["debt"] == 3_000 and visa["credit_limit"] == 10_000 and visa["limit_used_pct"] == 30
    assert visa["available_credit"] == 7_000

    budgets, _ = await run("get_budgets")
    assert budgets["budgets"] == [{"category": "Transport", "currency": "UZS", "limit": 40_000, "spent": 35_000,
                                   "used_pct": 87, "left": 5_000}]
    rate, _ = await run("get_exchange_rate")
    assert rate == {"usd_to_uzs": None}
    await db.set_usd_rate(USER, Decimal("12700"))
    assert (await run("get_exchange_rate"))[0] == {"usd_to_uzs": "12700"}
    categories, _ = await run("get_categories")
    assert "Transport" in categories["expense"] and categories["income"]


async def test_run_tool_errors_never_raise():
    await setup_user()
    assert (await tools.run_tool(USER, "drop_tables", {}))[1] is True
    assert (await tools.run_tool(USER, "get_accounts", {"extra": 1}))[1] is True
    assert (await tools.run_tool(USER, "get_accounts", "x"))[1] is True


# ---- Request shape ----

def test_analysis_request_shape():
    client, _ = fake_client()
    request = client.build_analysis_request([{"role": "user", "content": "q"}], system="S", effort="medium",
                                            max_tokens=1000, tools=tools.TOOLS, cache=True)
    assert request["model"] == "claude-opus-5-5"
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in request
    assert request["output_config"] == {"effort": "medium"}
    assert request["tool_choice"] == {"type": "auto"}
    assert all(tool["strict"] for tool in request["tools"])
    assert request["system"] == [{"type": "text", "text": "S", "cache_control": {"type": "ephemeral"}}]
    assert request["cache_control"] == {"type": "ephemeral"}
    assert request["betas"] == ["server-side-fallback-2026-07-01"] and request["fallbacks"] == "default"

    plain, _ = fake_client(fallbacks=False)
    request = plain.build_analysis_request([], system="S", effort="high", max_tokens=10)
    assert "betas" not in request and "tools" not in request and "cache_control" not in request


def test_analysis_request_is_accepted_by_the_sdk():
    """The built request goes through the real SDK (beta endpoint) with a fake transport."""
    import anthropic
    import httpx2 as httpx

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta")
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "stop_reason": "end_turn", "stop_sequence": None, "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1}})

    sdk = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = claude.ClaudeClient("test", "haiku-x", "claude-opus-5-5")
    request = client.build_analysis_request([{"role": "user", "content": [{"type": "text", "text": "q"}]}],
                                            system=assistant.QA_SYSTEM, effort="medium", max_tokens=100,
                                            tools=tools.TOOLS, cache=True)
    assert sdk.beta.messages.create(**request).stop_reason == "end_turn"
    body = seen["body"]
    assert seen["beta"] == "server-side-fallback-2026-07-01" and body["fallbacks"] == "default"
    assert body["tool_choice"] == {"type": "auto"} and body["output_config"] == {"effort": "medium"}
    assert body["tools"][0]["strict"] is True and "temperature" not in body


# ---- Tool loop ----

async def test_tool_loop_round_trip():
    await seed()
    first = response(thinking("s1"), tool_use("get_accounts", id_="a"),
                     tool_use("get_period_summary", {"period_offset": 0}, id_="b"), stop_reason="tool_use")
    final = response(thinking("s2"), text("**Visa** debt: 3 000 UZS"))
    client, messages = fake_client(first, final)
    result = await assistant.ask(USER, "how much do I owe?", "ru", client=client, today=date(2026, 11, 4))
    assert result.text == "Visa debt: 3 000 UZS"  # Markdown removed

    assert len(messages.calls) == 2
    call = messages.calls[1]
    assert call["timeout"] == client.analysis_timeout and call["model"] == "claude-opus-5-5"
    question, assistant_turn, results = call["messages"]
    assert "Answer language: Russian" in question["content"][0]["text"] and "2026-11-04" in question["content"][0]["text"]
    assert assistant_turn == {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "", "signature": "s1"},
        {"type": "tool_use", "id": "a", "name": "get_accounts", "input": {}},
        {"type": "tool_use", "id": "b", "name": "get_period_summary", "input": {"period_offset": 0}}]}
    assert results["role"] == "user" and [r["tool_use_id"] for r in results["content"]] == ["a", "b"]
    assert "Visa" in results["content"][0]["content"] and "is_error" not in results["content"][0]
    # the stored turn is the conversation as sent, plus the final answer with its thinking block
    [turn] = result.turns
    assert turn[:3] == call["messages"] and turn[3]["content"][0] == {"type": "thinking", "thinking": "",
                                                                       "signature": "s2"}

    # Follow-up: the earlier turn is replayed unchanged (append-only), then the new question
    client, messages = fake_client(response(text("Less than last month.")))
    follow = await assistant.ask(USER, "and last month?", "ru", result.turns, client=client)
    assert messages.calls[0]["messages"][:4] == turn and len(follow.turns) == 2


async def test_tool_errors_are_returned_to_the_model():
    await setup_user()
    client, messages = fake_client(
        response(tool_use("get_period_summary", {"period_offset": 3}), stop_reason="tool_use"),
        response(text("ok")))
    await assistant.ask(USER, "q", "en", client=client)
    [result] = messages.calls[1]["messages"][-1]["content"]
    assert result["is_error"] is True and "period_offset" in result["content"]


async def test_tool_loop_iteration_cap():
    await setup_user()
    loops = [response(tool_use("get_accounts", id_=f"t{i}"), stop_reason="tool_use")
             for i in range(assistant.MAX_ITERATIONS)]
    client, messages = fake_client(*loops)
    with pytest.raises(claude.AIError) as err:
        await assistant.ask(USER, "q", "en", client=client)
    assert err.value.code == "bad_response" and len(messages.calls) == assistant.MAX_ITERATIONS
    # before the last request the model is told to answer now (text after the tool results)
    last_user = messages.calls[-1]["messages"][-1]["content"]
    assert last_user[-1]["type"] == "text" and "Answer now" in last_user[-1]["text"]
    assert all(r["type"] == "tool_result" for r in last_user[:-1])


@pytest.mark.parametrize("bad, code", [
    (response(stop_reason="refusal"), "refused"),
    (response(text("partial"), stop_reason="max_tokens"), "bad_response"),
    (response(thinking(), stop_reason="end_turn"), "bad_response"),  # no text at all
])
async def test_tool_loop_stop_reasons(bad, code):
    await setup_user()
    client, _ = fake_client(bad)
    with pytest.raises(claude.AIError) as err:
        await assistant.ask(USER, "q", "en", client=client)
    assert err.value.code == code


async def test_tool_loop_maps_sdk_errors_and_not_configured():
    import anthropic
    import httpx2 as httpx

    await setup_user()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    for exc, code in [(anthropic.RateLimitError("x", response=httpx.Response(429, request=request), body=None),
                       "quota"),
                      (anthropic.BadRequestError("x", response=httpx.Response(400, request=request), body=None),
                       "bad_input"),
                      (anthropic.APITimeoutError(request=None), "timeout")]:
        client, _ = fake_client(exc)
        with pytest.raises(claude.AIError) as err:
            await assistant.ask(USER, "q", "en", client=client)
        assert err.value.code == code
    with pytest.raises(claude.AIError) as err:
        await assistant.ask(USER, "q", "en", client=claude.ClaudeClient("", "h", "o"))
    assert err.value.code == "not_configured"


async def test_pause_turn_continues_and_fallback_blocks_are_not_echoed():
    await setup_user()
    paused = response(thinking("old"), tool_use("get_accounts", id_="declined"), block("fallback"),
                      thinking("new"), text("Partial"), stop_reason="pause_turn")
    client, messages = fake_client(paused, response(text("Done")))
    result = await assistant.ask(USER, "q", "en", client=client)
    assert result.text == "Done"
    echoed = messages.calls[1]["messages"][1]["content"]
    assert echoed == [{"type": "thinking", "thinking": "", "signature": "new"}, {"type": "text", "text": "Partial"}]


def test_history_compaction_and_expiry():
    def turn(i):
        return [{"role": "user", "content": [{"type": "text", "text": f"q{i}"}]},
                {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                                  {"type": "tool_use", "id": "x", "name": "n", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "{}"}]},
                {"role": "assistant", "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                                                  {"type": "text", "text": f"a{i}"}]}]

    few = [turn(i) for i in range(assistant.MAX_TURNS - 1)]
    assert assistant.compact(few) is few
    many = [turn(i) for i in range(assistant.MAX_TURNS)]
    compacted = assistant.compact(many)
    assert len(compacted) == assistant.KEEP_TURNS
    assert compacted[-1] == [{"role": "user", "content": [{"type": "text", "text": f"q{assistant.MAX_TURNS - 1}"}]},
                             {"role": "assistant", "content": [{"type": "text",
                                                                "text": f"a{assistant.MAX_TURNS - 1}"}]}]
    assert "thinking" not in json.dumps(compacted)

    stamp = datetime(2026, 11, 4, 12, 0)
    assert assistant.fresh(few, stamp.isoformat(), stamp + timedelta(minutes=30)) is few
    assert assistant.fresh(few, stamp.isoformat(), stamp + timedelta(hours=2)) == []
    assert assistant.fresh(few, None, stamp) == [] and assistant.fresh(None, "x", stamp) == []


def test_answer_cleanup_and_split():
    assert assistant.clean_answer("## Title\n**Bold** and __x__\n- one\n* two\n\n\n\n`code`") == \
        "Title\nBold and x\n• one\n• two\n\ncode"
    parts = split_message("line &amp; more\n" * 600, limit=4000)
    assert all(len(p) <= 4000 for p in parts) and len(parts) > 1
    assert all(p.count("&") == p.count("&amp;") for p in parts)
    assert split_message("short") == ["short"]


# ---- Intent routing (extraction schema) ----

def test_intent_in_extraction_schema_and_parser():
    schema = claude._schema()
    assert "intent" in schema["required"] and schema["properties"]["intent"]["enum"] == list(claude.INTENTS)
    assert "intent" in claude.EXTRACTION_SYSTEM
    assert parser.intent({"intent": "question", "operations": []}) == "question"
    assert parser.intent({"intent": "operation"}) == "operation"
    assert parser.intent({"operations": []}) == "operation"  # older answers / missing field
    assert parser.intent({"intent": "weird"}) == "operation" and parser.intent(None) == "operation"
    context = claude.build_context([], {}, "2026-11-04 10:00", conversation=True)
    assert "follow-up" in context
    assert "follow-up" not in claude.build_context([], {}, "2026-11-04 10:00")


# ---- Advice ----

async def test_advice_data_windows_and_skip_when_empty():
    cash, card, credit, usd = await setup_user()
    monday = date(2026, 11, 2)
    assert await assistant.advice_data(USER, "weekly", monday) is None
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 900_000)], "Transport", "Taxi",
                              occurred_at=datetime(2026, 10, 30, 12))
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 100_000)], "Transport", "Taxi",
                              occurred_at=datetime(2026, 10, 22, 12))  # the week before
    await db.record_transfer(USER, card.id, credit.id, 100_000, occurred_at=datetime(2026, 10, 30, 12))
    data = await assistant.advice_data(USER, "weekly", monday)
    assert data["window"] == {"start": "2026-10-26", "last_day": "2026-11-01"}
    assert data["compared_with"] == {"start": "2026-10-19", "last_day": "2026-10-25"}
    [uzs] = data["currencies"]
    assert (uzs["expense"], uzs["previous_expense"], uzs["expense_change_pct"]) == (9_000, 1_000, 800)
    assert uzs["expenses_by_category"][0]["notable_increase"] is True
    assert data["largest_expenses"][0]["amount"] == 9_000
    visa = next(c for c in data["credit_cards"] if c["name"] == "Visa")
    assert visa["debt"] == 1_000 and visa["used_pct"] == 10  # 2 000 opening debt minus the 1 000 repayment

    await db.set_salary_day(USER, 5)
    data = await assistant.advice_data(USER, "monthly", date(2026, 11, 5))
    assert data["window"] == {"start": "2026-10-05", "last_day": "2026-11-04"}
    assert data["compared_with"] == {"start": "2026-09-05", "last_day": "2026-10-04"}


async def test_advice_request_and_text():
    await seed()
    client, messages = fake_client(response(thinking(), text("**Good** week.\n- tip one")))
    result = await assistant.advice(USER, "now", "uz", client=client)
    assert result.text == "Good week.\n• tip one"
    call = messages.calls[0]
    assert call["output_config"] == {"effort": "medium"} and "tools" not in call
    assert call["system"][0]["text"] == assistant.ADVICE_SYSTEM
    assert "Uzbek (Latin script)" in call["messages"][0]["content"][0]["text"]

    client, _ = fake_client(response(stop_reason="refusal"))
    with pytest.raises(claude.AIError) as err:
        await assistant.advice(USER, "now", "en", client=client)
    assert err.value.code == "refused"


# ---- Scheduler ----

def user_row(**kw):
    base = dict(id=USER, language="en", salary_day=5, advice_weekly=True, advice_monthly=True,
                advice_weekly_sent=None, advice_monthly_sent=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_due_weekly_monday_nine():
    monday = datetime(2026, 11, 2, 9, 0)
    assert sched.due(user_row(), monday) == [("weekly", date(2026, 11, 2))]
    assert sched.due(user_row(), monday - timedelta(minutes=1)) == []  # 08:59
    assert sched.due(user_row(), monday + timedelta(hours=14)) == [("weekly", date(2026, 11, 2))]  # catch-up
    assert sched.due(user_row(), monday + timedelta(days=1)) == []  # Tuesday: a missed Monday is skipped
    assert sched.due(user_row(advice_weekly_sent=date(2026, 11, 2)), monday) == []  # already sent
    assert sched.due(user_row(advice_weekly=False), monday) == []  # turned off


def test_due_monthly_on_period_start():
    start = datetime(2026, 11, 5, 9, 30)  # Thursday, salary day 5
    assert sched.due(user_row(), start) == [("monthly", date(2026, 11, 5))]
    assert sched.due(user_row(), start.replace(hour=8)) == []
    assert sched.due(user_row(), start + timedelta(days=1)) == []
    assert sched.due(user_row(advice_monthly_sent=date(2026, 11, 5)), start) == []
    assert sched.due(user_row(advice_monthly=False), start) == []
    # salary day on a Monday: both, monthly first
    assert sched.due(user_row(salary_day=2), datetime(2026, 11, 2, 10)) == [
        ("monthly", date(2026, 11, 2)), ("weekly", date(2026, 11, 2))]
    assert sched.due(user_row(salary_day=31), datetime(2026, 2, 28, 9)) == [("monthly", date(2026, 2, 28))]


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


@pytest.fixture
def fake_bot(monkeypatch):
    bot = FakeBot()
    monkeypatch.setattr(sched, "bot", bot)

    async def no_card(*args, **kwargs):  # the card path is covered in test_cards.py
        return None

    monkeypatch.setattr(sched.cards, "advice_card", no_card)
    yield bot
    claude.set_client(None)


async def test_scheduler_sends_weekly_once_and_survives_restart(fake_bot):
    cash, *_ = await setup_user()
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 900_000)], "Transport", "Taxi",
                              occurred_at=datetime(2026, 10, 30, 12))
    client, messages = fake_client(response(text("Spent 9 000 UZS on taxi.")))
    claude.set_client(client)
    monday = datetime(2026, 11, 2, 8, 59)

    assert await sched.AdviceScheduler().tick(monday) == []  # before 09:00
    # "restart": a new scheduler instance at 11:00 the same day still sends (bot was down at 09:00)
    first = sched.AdviceScheduler()
    assert await first.tick(monday.replace(hour=11)) == [(USER, "weekly")]
    assert len(fake_bot.sent) == 1 and "Weekly summary" in fake_bot.sent[0][1]
    assert "26.10 – 01.11.2026" in fake_bot.sent[0][1] and "Spent 9 000 UZS" in fake_bot.sent[0][1]
    assert (await db.get_user(USER)).advice_weekly_sent == date(2026, 11, 2)
    # later ticks and another restart do not send again
    assert await first.tick(monday.replace(hour=12)) == []
    assert await sched.AdviceScheduler().tick(monday.replace(hour=13)) == []
    assert len(fake_bot.sent) == 1 and len(messages.calls) == 1


async def test_scheduler_skips_empty_window_and_disabled(fake_bot):
    await setup_user()
    client, messages = fake_client(response(text("x")))
    claude.set_client(client)
    monday = datetime(2026, 11, 2, 9, 0)
    assert await sched.AdviceScheduler().tick(monday) == []
    assert messages.calls == [] and fake_bot.sent == []
    assert (await db.get_user(USER)).advice_weekly_sent == date(2026, 11, 2)  # handled, not retried

    await db.toggle_advice(USER, "weekly")
    await db.toggle_advice(USER, "monthly")
    user = await db.get_user(USER)
    assert (user.advice_weekly, user.advice_monthly) == (False, False)
    assert await sched.AdviceScheduler().tick(datetime(2026, 11, 9, 9, 0)) == []
    assert (await db.get_user(USER)).advice_weekly_sent == date(2026, 11, 2)


async def test_scheduler_monthly_and_retry_after_failure(fake_bot):
    cash, *_ = await setup_user()
    await db.set_salary_day(USER, 5)
    await db.record_operation(USER, "expense", "UZS", [db.Leg(cash.id, 900_000)], "Transport", "Taxi",
                              occurred_at=datetime(2026, 10, 20, 12))
    client, messages = fake_client(claude.AIError("unavailable"), response(text("Monthly review text")))
    claude.set_client(client)
    scheduler = sched.AdviceScheduler()
    start = datetime(2026, 11, 5, 9, 0)
    assert await scheduler.tick(start) == []  # AI failed
    assert (await db.get_user(USER)).advice_monthly_sent is None
    assert await scheduler.tick(start + timedelta(minutes=5)) == []  # waiting for the retry time
    assert len(messages.calls) == 1
    assert await scheduler.tick(start + sched.RETRY_AFTER) == [(USER, "monthly")]
    assert "Monthly review" in fake_bot.sent[0][1] and "05.10 – 04.11.2026" in fake_bot.sent[0][1]
    assert messages.calls[1]["output_config"] == {"effort": "high"}
    assert (await db.get_user(USER)).advice_monthly_sent == date(2026, 11, 5)


async def test_scheduler_does_nothing_without_api_key(fake_bot):
    await setup_user()
    claude.set_client(claude.ClaudeClient("", "h", "o"))
    assert await sched.AdviceScheduler().tick(datetime(2026, 11, 2, 9, 0)) == []
    assert (await db.get_user(USER)).advice_weekly_sent is None


def test_advice_message_escapes_and_fits():
    result = assistant.Advice("<b>x</b> & " + "y" * 5000, date(2026, 10, 26), date(2026, 11, 1))
    message = sched.advice_message(result, "weekly", "ru")
    assert message.startswith("📅 <b>Недельная сводка</b> · 26.10 – 01.11.2026")
    assert "&lt;b&gt;x&lt;/b&gt; &amp;" in message and len(message) <= sched.MESSAGE_LIMIT


# ---- Chart centre text ----

@pytest.mark.parametrize("total", ["Jami: 2 440 000 UZS", "Итого: 1 234 567 890 123 UZS", "Total: 12 345.67 USD"])
def test_donut_center_text_fits_in_the_hole(total):
    items = [("Transport", 1_200_000), ("Oziq-ovqat", 800_000), ("Uy", 440_000)]
    fig = charts.build_expense_figure(items, "Xarajatlar", total, "Boshqa", short_money)
    ax = fig.axes[0]
    [center] = [t for t in ax.texts if "\n" in t.get_text()]
    label, amount = center.get_text().split("\n")
    assert label.endswith(":") and amount and ":" not in amount
    box = center.get_window_extent(fig.canvas.get_renderer())
    assert (box.width ** 2 + box.height ** 2) ** 0.5 <= charts.hole_size(ax) * charts.HOLE_FILL
    assert charts.MIN_CENTER_FONT <= center.get_fontsize() <= charts.CENTER_FONT


def test_center_lines():
    assert charts.center_lines("Jami: 2 440 000 UZS") == "Jami:\n2 440 000 UZS"
    assert charts.center_lines("9.5M UZS") == "9.5M UZS"
