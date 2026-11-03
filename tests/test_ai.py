"""AI input: validation of canned Gemini answers, duplicate guard and the client wrapper (no real API calls)."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from utils.ai import gemini, parser
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
    assert (await parser.mark_duplicate(USER, draft, now)).duplicate is False

    saved = await parser.save_draft(USER, draft)
    assert saved.transactions[0].source == "ai" and saved.transactions[0].source_ref == "sms-hash"
    assert await balance(card.id) == 500_000 - 2_500_000

    # Same amount + account within minutes
    again = parser.Draft(kind="expense", amount_minor=2_500_000, currency="UZS", category="Food",
                         account_id=card.id)
    assert (await parser.mark_duplicate(USER, again, now + timedelta(minutes=3))).duplicate is True
    # ... but not hours later, on another account or with another amount
    assert (await parser.mark_duplicate(USER, again, now + timedelta(hours=2))).duplicate is False
    other = parser.Draft(amount_minor=2_500_000, account_id=cash.id)
    assert (await parser.mark_duplicate(USER, other, now)).duplicate is False
    # The same SMS forwarded again, even much later
    resent = parser.Draft(amount_minor=1, account_id=cash.id, source_ref="sms-hash")
    assert (await parser.mark_duplicate(USER, resent, now + timedelta(days=3))).duplicate is True


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
    text = gemini.build_context(*ctx.as_prompt_data(), "2026-11-04 15:00")
    assert "| Visa | credit | UZS" in text and "Transport: Fuel, Taxi" in text


# ---- Gemini client wrapper (mocked SDK) ----

class FakeModels:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return SimpleNamespace(text=self.result)


def fake_client(result):
    models = FakeModels(result)
    return gemini.GeminiClient("", "test-model", client=SimpleNamespace(aio=SimpleNamespace(models=models))), models


async def test_extract_operations_sends_schema_and_media():
    answer = {"input_type": "receipt", "operations": [{"kind": "expense", "amount": "1000", "confidence": 1}]}
    client, models = fake_client(json.dumps(answer))
    result = await gemini.extract_operations("CTX", None, [gemini.Media(b"jpg", "image/jpeg")], client=client)
    assert result == answer
    call = models.calls[0]
    assert call["model"] == "test-model"
    assert call["config"].response_mime_type == "application/json" and call["config"].response_schema is not None
    parts = call["contents"][0].parts
    assert parts[0].inline_data.mime_type == "image/jpeg" and parts[0].inline_data.data == b"jpg"
    assert parts[1].text == "CTX"


async def test_client_errors_are_mapped():
    from google.genai import errors

    assert gemini.GeminiClient("", "m").configured is False
    with pytest.raises(gemini.AIError) as err:
        await gemini.extract_operations("CTX", "hi", client=gemini.GeminiClient("", "m"))
    assert err.value.code == "not_configured"

    for exc, code in [(errors.ClientError(429, {"error": {"message": "quota"}}), "quota"),
                      (errors.ClientError(403, {"error": {"message": "denied"}}), "auth"),
                      (errors.ServerError(503, {"error": {"message": "overloaded"}}), "unavailable"),
                      (RuntimeError("boom"), "unavailable")]:
        client, _ = fake_client(exc)
        with pytest.raises(gemini.AIError) as err:
            await gemini.extract_operations("CTX", "hi", client=client)
        assert err.value.code == code

    client, _ = fake_client("not json")
    with pytest.raises(gemini.AIError) as err:
        await gemini.extract_operations("CTX", "hi", client=client)
    assert err.value.code == "bad_response"

    client, _ = fake_client(None)
    with pytest.raises(gemini.AIError) as err:
        await gemini.extract_operations("CTX", "hi", client=client)
    assert err.value.code == "bad_response"

    client, _ = fake_client("{}")
    with pytest.raises(gemini.AIError) as err:
        await gemini.extract_operations("CTX", "x", [gemini.Media(b"0" * (gemini.MAX_MEDIA_BYTES + 1), "audio/ogg")],
                                        client=client)
    assert err.value.code == "too_large"
