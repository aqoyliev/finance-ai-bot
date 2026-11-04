"""AI input: validation of canned Claude answers, duplicate guard and the client wrapper (no real API calls)."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from utils.ai import claude, parser
from utils.ai.parser import AccountRef, UserContext
from utils.db_api import finance as db

from test_services import USER, balance, setup_user

NOW = datetime(2026, 11, 4, 15, 0)

CTX = UserContext(
    accounts=[
        AccountRef(1, "Naqd pul", "cash", "UZS"),
        AccountRef(2, "UOB 4417", "debit", "UZS"),
        AccountRef(3, "Hamkorbank", "debit", "UZS"),
        AccountRef(4, "Cash (USD)", "cash", "USD"),
        AccountRef(5, "Kredit karta 9012", "credit", "UZS"),
    ],
    categories={
        "expense": {"Transport": ["Taksi", "Yoqilg'i"], "Mayda xarajatlar": ["Qahva", "Gazaklar"],
                    "Uy-ro'zg'or": ["Uy uchun oziq-ovqat", "Go'sht"]},
        "income": {"Maosh": [], "Qo'shimcha daromad": []},
    },
)


def parse(*operations, source_ref=None):
    return parser.parse_response({"input_type": "text", "operations": list(operations)}, CTX, NOW, source_ref)


# ---- Amounts ----

@pytest.mark.parametrize("value, expected", [
    ("125000.00", 12_500_000),
    ("125 000,00", 12_500_000),
    ("125.000", 12_500_000),
    ("125,000", 12_500_000),
    ("1 250 000", 125_000_000),
    ("1,250.50", 125_050),
    ("1.250,50", 125_050),
    ("18,50", 1_850),
    ("18k", 1_800_000),
    ("12m", 1_200_000_000),
    ("25 000 so'm", 2_500_000),
    ("12 mln so'm", 1_200_000_000),
    ("UZS 25 000", 2_500_000),
    ("abc12def3", None),
    (25000, 2_500_000),
    (12.5, 1_250),
    ("0", None), ("-500", None), ("abc", None), ("", None), (None, None), (True, None), ("1e30", None),
])
def test_normalize_amount(value, expected):
    assert parser.normalize_amount(value) == expected


# ---- Canned model answers ----

def test_receipt_total_with_date():
    [draft] = parser.parse_response({"input_type": "receipt", "operations": [{
        "kind": "expense", "amount": "187 450,00", "currency": "UZS", "category": "uy-ro'zg'or",
        "subcategory": "Uy uchun oziq-ovqat", "account_id": None, "card_last4": None,
        "account_hint": None, "note": "Korzinka: non, sut, go'sht", "occurred_at": "2026-11-03 19:42",
        "confidence": 0.93}]}, CTX, NOW, "ref")
    assert draft.amount_minor == 18_745_000 and draft.currency == "UZS"
    assert (draft.category, draft.subcategory) == ("Uy-ro'zg'or", "Uy uchun oziq-ovqat")
    assert draft.occurred_at == "2026-11-03T19:42:00"
    assert draft.account_id is None and parser.missing_fields(draft) == ["account"]
    assert draft.source_ref == "ref"


def test_uzbek_sms_matches_card_last4():
    [draft] = parse({"kind": "expense", "amount": "45000.00", "currency": "UZS", "category": "Transport",
                     "subcategory": "Taksi", "account_id": None, "card_last4": "*4417",
                     "note": "YANDEX GO", "occurred_at": "04.11.2026 14:31", "confidence": 0.9})
    assert draft.account_id == 2 and draft.card_last4 == "4417"
    assert draft.occurred_at == "2026-11-04T14:31:00"
    assert parser.missing_fields(draft) == []


def test_sms_income_to_credit_card_by_last4():
    [draft] = parse({"kind": "income", "amount": "1000000", "currency": "UZS", "category": "Maosh",
                     "card_last4": "8600 **** **** 9012", "confidence": 0.8})
    assert draft.kind == "income" and draft.account_id == 5 and draft.category == "Maosh"
    assert draft.subcategory is None


def test_russian_free_text_cash_hint():
    [draft] = parse({"kind": "expense", "amount": "18000", "currency": "UZS", "category": "Mayda xarajatlar",
                     "subcategory": "qahva", "account_hint": "naqd pul", "note": "кофе", "confidence": 0.85})
    assert draft.account_id == 1 and draft.subcategory == "Qahva"
    assert draft.occurred_at is None  # saved as "now"


def test_multi_item_text():
    drafts = parse(
        {"kind": "expense", "amount": "25000", "currency": "UZS", "category": "Transport", "subcategory": "Taksi",
         "account_id": 2, "confidence": 0.9},
        {"kind": "expense", "amount": "18000", "currency": "UZS", "category": "Mayda xarajatlar",
         "subcategory": "Qahva", "account_id": 1, "confidence": 0.9},
        source_ref="same-message")
    assert [d.amount_minor for d in drafts] == [2_500_000, 1_800_000]
    assert [d.account_id for d in drafts] == [2, 1]
    assert all(d.source_ref is None for d in drafts)  # one message, several operations: no fingerprint


def test_salary_by_account_id_and_transfer():
    income, transfer = parse(
        {"kind": "income", "amount": "12000000", "currency": "UZS", "category": "Maosh", "account_id": 3,
         "confidence": 0.95},
        {"kind": "transfer", "amount": "500000", "currency": "UZS", "account_id": 3, "to_account_id": 5,
         "category": "Transport", "confidence": 0.9})
    assert income.account_id == 3 and parser.missing_fields(income) == []
    assert (transfer.account_id, transfer.to_account_id, transfer.category) == (3, 5, None)
    assert parser.missing_fields(transfer) == []


def test_garbage_and_invalid_amount():
    assert parser.parse_response("nonsense", CTX, NOW) == []
    assert parser.parse_response({"operations": "x"}, CTX, NOW) == []
    assert parse({"kind": "expense", "amount": "abc", "confidence": 0.1}) == []  # nothing useful at all
    [draft] = parse({"kind": "weird", "amount": "-100", "category": "Transport", "account_id": 999,
                     "occurred_at": "1999-01-01 10:00", "confidence": 7})
    assert draft.kind == "expense" and draft.amount_minor is None and "ai_note_amount" in draft.notes
    assert draft.account_id is None  # foreign / unknown account id
    assert draft.occurred_at is None  # implausible date dropped
    assert draft.confidence == 1.0
    assert set(parser.missing_fields(draft)) == {"amount", "currency", "account"}


def test_wrong_currency_for_account():
    [draft] = parse({"kind": "expense", "amount": "20", "currency": "USD", "category": "Transport",
                     "account_id": 2, "confidence": 0.9})
    assert draft.currency == "USD" and draft.account_id is None
    assert "ai_note_account_currency" in draft.notes

    [draft] = parse({"kind": "expense", "amount": "20", "currency": "EUR", "account_id": 4, "confidence": 0.9})
    assert draft.currency == "USD" and draft.account_id == 4  # unsupported currency -> taken from the account
    assert "ai_note_currency" in draft.notes


def test_unknown_category():
    [draft] = parse({"kind": "expense", "amount": "50000", "currency": "UZS", "category": "Restaurants",
                     "subcategory": "Sushi", "account_id": 1, "confidence": 0.9})
    assert draft.category is None and draft.subcategory is None
    assert parser.missing_fields(draft) == ["category"]

    # Unknown category but a known subcategory: its parent is used
    [draft] = parse({"kind": "expense", "amount": "50000", "currency": "UZS", "category": "Taxi rides",
                     "subcategory": "Taksi", "account_id": 1, "confidence": 0.9})
    assert (draft.category, draft.subcategory) == ("Transport", "Taksi")

    # Income must not take an expense category
    [draft] = parse({"kind": "income", "amount": "50000", "currency": "UZS", "category": "Transport",
                     "account_id": 1, "confidence": 0.9})
    assert draft.category is None


def test_draft_roundtrip_and_fingerprint():
    [draft] = parse({"kind": "expense", "amount": "1000", "currency": "UZS", "account_id": 1, "confidence": 1})
    assert parser.Draft.from_dict(json.loads(json.dumps(draft.to_dict()))) == draft
    assert parser.fingerprint("Pokupka:  10 000 UZS\nKarta *4417") == parser.fingerprint("pokupka: 10 000 uzs karta *4417")


# ---- Duplicate guard and saving (database) ----

async def test_duplicate_guard_and_save_as_ai():
    cash, card, credit, usd = await setup_user()
    now = db.now()
    draft = parser.Draft(kind="expense", amount_minor=2_500_000, currency="UZS", category="Food",
                         account_id=card.id, confidence=0.9, source_ref="sms-hash")
    assert await parser.duplicate_of(USER, draft, now) is None

    saved = await parser.save_draft(USER, draft)
    assert saved.transactions[0].source == "ai" and saved.transactions[0].source_ref == "sms-hash"
    assert await balance(card.id) == 500_000 - 2_500_000

    # Same amount + account within minutes
    again = parser.Draft(kind="expense", amount_minor=2_500_000, currency="UZS", category="Food",
                         account_id=card.id)
    assert await parser.duplicate_of(USER, again, now + timedelta(minutes=3)) == "similar"
    # ... but not hours later, on another account or with another amount
    assert await parser.duplicate_of(USER, again, now + timedelta(hours=2)) is None
    other = parser.Draft(amount_minor=2_500_000, account_id=cash.id)
    assert await parser.duplicate_of(USER, other, now) is None
    # The same SMS forwarded again, even much later: never saved twice
    resent = parser.Draft(amount_minor=1, account_id=cash.id, source_ref="sms-hash")
    assert await parser.duplicate_of(USER, resent, now + timedelta(days=3)) == "source"
    # A repeat of the same input wins over a merely similar one
    same = parser.Draft(amount_minor=2_500_000, account_id=card.id, source_ref="sms-hash")
    assert await parser.duplicate_of(USER, same, now) == "source"


async def test_save_transfer_draft_and_incomplete_rejected():
    cash, card, credit, usd = await setup_user()
    draft = parser.Draft(kind="transfer", amount_minor=200_000, currency="UZS", account_id=card.id,
                         to_account_id=credit.id, occurred_at="2026-11-01T10:00:00")
    saved = await parser.save_draft(USER, draft)
    assert {tx.source for tx in saved.transactions} == {"ai"}
    assert saved.transactions[0].occurred_at == datetime(2026, 11, 1, 10, 0)
    assert await balance(credit.id) == 0

    with pytest.raises(db.InvalidValue):
        await parser.save_draft(USER, parser.Draft(kind="expense", amount_minor=100, currency="UZS"))
    with pytest.raises(db.CurrencyMismatch):
        await parser.save_draft(USER, parser.Draft(kind="expense", amount_minor=100, currency="UZS",
                                                   category="Food", account_id=usd.id))


async def test_load_context_from_db():
    await setup_user()
    ctx = await parser.load_context(USER)
    assert any(a.name == "Visa" and a.kind == "credit" for a in ctx.accounts)
    assert "Transport" in ctx.categories["expense"] and "Taxi" in ctx.categories["expense"]["Transport"]
    assert "Salary" in ctx.categories["income"]
    text = claude.build_context(*ctx.as_prompt_data(), "2026-11-04 15:00")
    assert "| Visa | credit | UZS" in text and "Transport: Fuel, Taxi" in text


# ---- Claude client wrapper (mocked SDK) ----

class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def reply(text, stop_reason="end_turn", blocks=None):
    content = blocks if blocks is not None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def fake_client(result):
    messages = FakeMessages(result)
    client = claude.ClaudeClient("", "haiku-x", "opus-x", client=SimpleNamespace(messages=messages))
    return client, messages


def status_error(cls, status):
    import httpx2 as httpx
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


async def test_extract_operations_request_shape():
    answer = {"input_type": "receipt", "operations": [{"kind": "expense", "amount": "1000", "confidence": 1}]}
    client, messages = fake_client(reply(json.dumps(answer)))
    media = [claude.Media(b"jpg", "image/jpeg"), claude.Media(b"%PDF", "application/pdf")]
    result = await claude.extract_operations("CTX", None, media, client=client)
    assert result == answer
    call = messages.calls[0]
    assert call["model"] == "haiku-x" and call["max_tokens"] == 4000
    assert call["system"] == claude.EXTRACTION_SYSTEM
    for banned in ("temperature", "top_p", "top_k", "thinking", "output_format"):
        assert banned not in call
    config = call["output_config"]
    assert config["effort"] == "low"
    assert config["format"]["type"] == "json_schema" and config["format"]["schema"]["additionalProperties"] is False
    [message] = call["messages"]
    assert message["role"] == "user"
    image, document, context, instruction = message["content"]  # media first, then text
    assert image == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "anBn"}}
    assert document["type"] == "document" and document["source"]["media_type"] == "application/pdf"
    assert context == {"type": "text", "text": "CTX"}
    assert instruction["text"] == "Extract the operations from the attached file."


async def test_per_call_model_and_text_only_request():
    client, messages = fake_client(reply("hello"))
    assert await client.generate(["q"], model=client.analysis_model) == "hello"
    call = messages.calls[0]
    assert call["model"] == "opus-x" and "output_config" not in call and "system" not in call


def test_schema_is_structured_output_compatible():
    schema = claude._schema()
    operation = schema["properties"]["operations"]["items"]
    assert operation["additionalProperties"] is False
    assert operation["required"] == list(operation["properties"])
    assert "voice" not in schema["properties"]["input_type"]["enum"]
    assert {"type": "null"} in operation["properties"]["account_id"]["anyOf"]
    text = json.dumps(schema)
    assert "nullable" not in text and "minimum" not in text and "maximum" not in text


def test_request_is_accepted_by_the_sdk_types():
    """Send the built request through the real SDK with a fake transport (no network)."""
    import anthropic
    import httpx2 as httpx

    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": "haiku-x", "stop_reason": "end_turn",
            "stop_sequence": None, "content": [{"type": "text", "text": "{}"}],
            "usage": {"input_tokens": 1, "output_tokens": 1}})

    sdk = anthropic.Anthropic(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    client = claude.ClaudeClient("test", "haiku-x")
    request = client.build_request(["CTX"], [claude.Media(b"jpg", "image/jpeg")], system="S",
                                   schema=claude._schema(), effort="low")
    response = sdk.messages.create(**request)
    assert response.stop_reason == "end_turn"
    assert seen["body"]["output_config"]["effort"] == "low"
    assert seen["body"]["messages"][0]["content"][0]["type"] == "image"


async def test_not_configured_and_oversized_media():
    assert claude.ClaudeClient("", "m").configured is False
    with pytest.raises(claude.AIError) as err:
        await claude.extract_operations("CTX", "hi", client=claude.ClaudeClient("", "m"))
    assert err.value.code == "not_configured"

    client, _ = fake_client(reply("{}"))
    too_big = [claude.Media(b"0" * (claude.MAX_IMAGE_BYTES + 1), "image/png")]
    with pytest.raises(claude.AIError) as err:
        await claude.extract_operations("CTX", "x", too_big, client=client)
    assert err.value.code == "too_large"
    with pytest.raises(claude.AIError) as err:  # audio / HEIC are not supported by Claude
        await claude.extract_operations("CTX", "x", [claude.Media(b"0", "audio/ogg")], client=client)
    assert err.value.code == "bad_input"
    assert claude.media_limit("application/pdf") == claude.MAX_MEDIA_BYTES


async def test_response_problems_are_mapped():
    cases = [(reply("", stop_reason="refusal"), "refused"),
             (reply('{"operations": ', stop_reason="max_tokens"), "bad_response"),
             (reply("not json"), "bad_response"),
             (reply("", blocks=[]), "bad_response")]
    for response, code in cases:
        client, _ = fake_client(response)
        with pytest.raises(claude.AIError) as err:
            await claude.extract_operations("CTX", "hi", client=client)
        assert err.value.code == code, code

    # thinking blocks are skipped, only text counts
    blocks = [SimpleNamespace(type="thinking", thinking="hmm"), SimpleNamespace(type="text", text='{"a": 1}')]
    client, _ = fake_client(reply("", blocks=blocks))
    assert await client.generate_json(["x"], schema={}) == {"a": 1}


async def test_client_errors_are_mapped():
    import anthropic

    cases = [(status_error(anthropic.AuthenticationError, 401), "auth"),
             (status_error(anthropic.PermissionDeniedError, 403), "auth"),
             (status_error(anthropic.RateLimitError, 429), "quota"),
             (status_error(anthropic.BadRequestError, 400), "bad_input"),
             (status_error(anthropic.RequestTooLargeError, 413), "too_large"),
             (status_error(anthropic.InternalServerError, 500), "unavailable"),
             (status_error(anthropic.OverloadedError, 529), "unavailable"),
             (status_error(anthropic.NotFoundError, 404), "unavailable"),
             (anthropic.APITimeoutError(request=None), "timeout"),
             (anthropic.APIConnectionError(message="down", request=None), "unavailable"),
             (RuntimeError("boom"), "unavailable")]
    for exc, code in cases:
        client, _ = fake_client(exc)
        with pytest.raises(claude.AIError) as err:
            await claude.extract_operations("CTX", "hi", client=client)
        assert err.value.code == code, (type(exc).__name__, code)
