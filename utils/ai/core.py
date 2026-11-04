"""Provider-neutral AI layer: errors, media, the provider switch and the operation-extraction use case.

Two providers implement the same client interface: ClaudeClient (utils/ai/claude.py) and GeminiClient
(utils/ai/gemini.py). get_client() returns the one selected by AI_PROVIDER, so handlers, the assistant and the
parser never depend on a specific provider. A client offers:

- `configured`, `provider`, `key_name`, `supports_audio`, `accepts(mime)`, `media_limit(mime)`
- `generate()` / `generate_json()`: one request (text + optional image/PDF/audio in, text or JSON out)
- `analysis_step()`: one analysis-model request in a conversation, returning a provider-neutral Step;
  `user_message()` / `tool_results_message()` build the history messages in the provider's own format
  (plain JSON-compatible dicts, kept in FSM storage) and `owns_history()` recognises them.

Nothing here touches the database: the caller passes a plain-text description of the user's accounts and
categories, and utils/ai/parser.py validates whatever comes back.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from data import config

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
PDF_TYPE = "application/pdf"
# Audio formats Gemini reads; Telegram voice messages are OGG/Opus ("audio/ogg")
AUDIO_TYPES = ("audio/ogg", "audio/opus", "audio/mpeg", "audio/mp3", "audio/wav", "audio/aac", "audio/flac",
               "audio/aiff", "audio/m4a", "audio/webm")
_AUDIO_ALIASES = {"audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "audio/x-flac": "audio/flac",
                  "audio/mp4": "audio/m4a", "audio/x-m4a": "audio/m4a", "audio/x-aiff": "audio/aiff",
                  "audio/vorbis": "audio/ogg", "audio/x-opus+ogg": "audio/ogg"}
MAX_AUDIO_SECONDS = 120  # voice input is for short dictated operations; longer ones are refused politely
# Inline request limit is 20 MB in total and inline data is base64 (+1/3), so keep audio well below it
MAX_AUDIO_BYTES = 14 * 1024 * 1024
PROVIDERS = ("gemini", "claude")


def audio_mime(mime_type: Optional[str]) -> Optional[str]:
    """Normalised audio MIME type, or None if it is not an audio format we send to the model."""
    mime = (mime_type or "").split(";")[0].strip().lower()
    mime = _AUDIO_ALIASES.get(mime, mime)
    return mime if mime in AUDIO_TYPES else None


class AIError(Exception):
    """A failed AI request. `code` maps to a localized message (ai_error_<code>)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        # not_configured | timeout | quota | auth | bad_input | unavailable | bad_response | too_large | refused
        self.code = code


@dataclass
class Media:
    data: bytes
    mime_type: str  # image/*, application/pdf or (Gemini only) audio/*


@dataclass
class ToolCall:
    id: str
    name: str
    input: Any


@dataclass
class Step:
    """One analysis-model response, provider-neutral.

    stop: "tool_use" (run `calls` and send the results), "pause" (send the turn back as is to continue) or
    "end" (final answer in `text`). `message` is the assistant message to append to the history unchanged."""
    stop: str
    message: Dict[str, Any]
    text: str = ""
    calls: List[ToolCall] = field(default_factory=list)


# ---- Provider switch ----

_default_client: Any = None


def make_client(provider: Optional[str] = None):
    """A client for `provider` (default: AI_PROVIDER) built from data/config.py."""
    provider = (provider or config.AI_PROVIDER).strip().lower()
    if provider == "claude":
        from .claude import ClaudeClient
        return ClaudeClient(config.ANTHROPIC_API_KEY, config.CLAUDE_EXTRACT_MODEL, config.CLAUDE_ANALYSIS_MODEL,
                            config.CLAUDE_TIMEOUT, analysis_timeout=config.CLAUDE_ANALYSIS_TIMEOUT,
                            fallbacks=config.CLAUDE_REFUSAL_FALLBACK)
    if provider == "gemini":
        from .gemini import GeminiClient
        return GeminiClient(config.GEMINI_API_KEY, config.GEMINI_EXTRACT_MODEL, config.GEMINI_ANALYSIS_MODEL,
                            config.GEMINI_TIMEOUT, analysis_timeout=config.GEMINI_ANALYSIS_TIMEOUT)
    raise ValueError(f"Unknown AI_PROVIDER {provider!r}; use one of {', '.join(PROVIDERS)}")


def get_client():
    """Shared client of the configured provider (AI_PROVIDER = gemini | claude)."""
    global _default_client
    if _default_client is None:
        _default_client = make_client()
    return _default_client


def set_client(client) -> None:
    """Replace the shared client (tests, end-to-end checks); None rebuilds it from the config on next use."""
    global _default_client
    _default_client = client


# ---- Operation extraction ----

EXTRACT_EFFORT = "low"


def _field(schema: dict, description: str, nullable: bool = True) -> dict:
    """A described property; nullable ones become anyOf [schema, null] (structured outputs have no `nullable`)."""
    return {"anyOf": [schema, {"type": "null"}], "description": description} if nullable \
        else {**schema, "description": description}


INTENTS = ("operation", "question", "other")


def _schema() -> dict:
    """JSON Schema for structured outputs: a list of draft operations. Missing values are null, never guessed.

    Structured outputs need additionalProperties=false, every property listed in `required` and no
    numeric bounds, so optional values are expressed as anyOf [X, null].
    """
    string = {"type": "string"}
    properties = {
        "kind": _field({"type": "string", "enum": ["expense", "income", "transfer"]},
                       "expense = money spent, income = money received, "
                       "transfer = between two of the user's own accounts", nullable=False),
        "amount": _field(string, "Total amount as a plain decimal: digits and an optional dot for decimals, "
                                 "no spaces or thousands separators, e.g. '125000.00'", nullable=False),
        "currency": _field({"type": "string", "enum": ["UZS", "USD"]}, "Currency code"),
        "category": _field(string, "Exact name of one of the user's categories for this kind"),
        "subcategory": _field(string, "Exact name of a subcategory of the chosen category"),
        "account_id": _field({"type": "integer"}, "id of the user's account the money left (or, for income, "
                                                  "arrived to); for a transfer the source account"),
        "to_account_id": _field({"type": "integer"}, "Transfer only: id of the receiving account"),
        "card_last4": _field(string, "Last 4 digits of the card if shown (e.g. from '*1234')"),
        "account_hint": _field(string, "Account/bank/payment method as written in the input"),
        "note": _field(string, "Short merchant or description, max ~80 characters"),
        "occurred_at": _field(string, "Date/time printed on the receipt or SMS, 'YYYY-MM-DD HH:MM'; "
                                      "null if not shown"),
        "confidence": _field({"type": "number"}, "0..1, how sure you are about amount and kind", nullable=False),
    }
    operation = {"type": "object", "properties": properties, "required": list(properties),
                 "additionalProperties": False}
    return {
        "type": "object",
        "properties": {
            "input_type": {"type": "string", "enum": ["receipt", "bank_sms", "text", "other"]},
            "intent": {"type": "string", "enum": list(INTENTS),
                       "description": "operation = something to record; question = the user asks about their "
                                      "own finances or wants advice; other = anything else"},
            "operations": {"type": "array", "items": operation},
        },
        "required": ["input_type", "intent", "operations"],
        "additionalProperties": False,
    }


EXTRACTION_SYSTEM = """You turn a user's message into draft financial operations for a personal finance app \
in Uzbekistan. The input may be a receipt photo or PDF, a bank SMS / push notification (Uzcard, Humo, Visa; \
Uzbek, Russian or English), a voice message, or free text in Uzbek (Latin or Cyrillic), Russian or English.

Rules:
- Return one operation per separate payment. A receipt is ONE operation: use the TOTAL actually paid \
("Jami", "Итого", "Всего", "To'lov", "Total"), never individual lines, VAT (QQS/НДС) or change. You may \
list up to 3 main items briefly in the note.
- A free-text or voice message may contain several operations ("taksi 25000, kofe 18000") - return each.
- A voice message: listen to what the user says (it may mix Uzbek, Russian and English) and treat it like \
free text (input_type "text"); spoken numbers ("yigirma besh ming", "двадцать пять тысяч") are amounts.
- amount: a plain decimal string without thousands separators. Uzbek amounts are written like \
"125 000,00", "125.000" or "125,000" - all of these mean 125000. "18 ming"/"18 тысяч"/"18k" = 18000, \
"12 mln"/"12 млн"/"12m" = 12000000. "so'm", "сум", "sum", "UZS" mean UZS; "$", "dollar", "USD" mean USD.
Keep the amount in the currency it is written in: never convert between currencies and never state an \
exchange rate (you do not know today's rate).
- Bank SMS: "Pokupka"/"Oplata"/"Списание"/"To'lov"/"Xarid" = expense; "Popolnenie"/"Пополнение"/\
"Зачисление"/"Kirim"/"Tushum" = income. The balance ("Balans"/"Остаток") is NOT the amount. Card digits \
like "*1234" or "8600 **** **** 1234" give card_last4.
- Choose account_id, category and subcategory ONLY from the lists provided by the user context, using the \
exact names/ids. Match accounts by name, bank, card last 4 digits (the account's last4, or digits \
in its name), or words like \
"naqd"/"наличные"/"cash" for a cash account. If unsure, use null - the user will choose.
- occurred_at only if a date/time is written in the input; otherwise null.
- If the input contains no financial operation or is unreadable, return an empty operations list.
- Do not invent data.

intent:
- "operation": the message records money spent, received or moved (every receipt and bank SMS is one).
- "question": the user asks about their own finances, spending, balances, budgets or wants advice \
("taksiga qancha ketdi?", "сколько я потратил в этом месяце?", "how can I save more?", "and last month?"). \
Return an empty operations list for a question.
- "other": greetings, chit-chat, unreadable input."""


def build_context(accounts: Sequence[dict], categories: dict, now_text: str, conversation: bool = False) -> str:
    """Plain-text description of the user's data for the prompt.

    accounts: [{id, name, kind, currency, last4}]; categories: {"expense": {name: [subs]}, "income": {name: []}}.
    conversation: the user has just been asking the assistant questions, so short follow-ups are questions.
    """
    lines = [f"Current local date and time (Asia/Tashkent): {now_text}"]
    if conversation:
        lines.append("The user is in a conversation with the finance assistant: a short follow-up without an "
                     "amount (e.g. 'and last month?', 'a taksi?') has intent=question.")
    lines += ["", "User's accounts (id | name | kind | currency | card last4):"]
    lines += [f"{a['id']} | {a['name']} | {a['kind']} | {a['currency']} | {a.get('last4') or '-'}"
              for a in accounts] or ["(none)"]
    lines += ["", "Expense categories (category: subcategories):"]
    lines += [f"- {name}: {', '.join(subs)}" for name, subs in categories.get("expense", {}).items()] or ["(none)"]
    lines += ["", "Income categories:"]
    lines += [f"- {name}" for name in categories.get("income", {})] or ["(none)"]
    return "\n".join(lines)


async def extract_operations(context: str, text: Optional[str] = None, media: Sequence[Media] = (),
                             client: Any = None) -> dict:
    """Ask the extraction model for draft operations. Returns the raw (unvalidated) JSON object.

    A voice message is transcribed and extracted in the same call (Gemini audio input)."""
    client = client or get_client()
    if not client.configured:
        raise AIError("not_configured")
    texts = [context]
    if text:
        texts.append(f"User message:\n{text}")
    if any(audio_mime(item.mime_type) for item in media):
        texts.append("The attached audio is the user's voice message: extract the operations from what they say.")
    elif media and not text:
        texts.append("Extract the operations from the attached file.")
    result = await client.generate_json(texts, media, schema=_schema(), system=EXTRACTION_SYSTEM,
                                        model=client.extract_model, effort=EXTRACT_EFFORT)
    if not isinstance(result, dict):
        raise AIError("bad_response", "not an object")
    return result
