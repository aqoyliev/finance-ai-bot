"""Google Gemini (Google AI Studio) client, prompts and the response schema for AI input.

GeminiClient is generic (text + optional media in, text or JSON out) so later features such as
Q&A over the user's data or weekly advice can reuse it; extract_operations() is the AI-input use case.
Nothing here touches the database: the caller passes a plain-text description of the user's
accounts and categories, and utils/ai/parser.py validates whatever comes back.
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from data import config

try:  # The bot must still start (manual menus only) if the SDK is not installed
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = genai_errors = genai_types = None

log = logging.getLogger(__name__)

MAX_MEDIA_BYTES = 15 * 1024 * 1024  # inline request limit is ~20 MB; keep a margin


class AIError(Exception):
    """A failed AI request. `code` maps to a localized message (ai_error_<code>)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code  # not_configured | timeout | quota | auth | bad_input | unavailable | bad_response | too_large


@dataclass
class Media:
    data: bytes
    mime_type: str  # e.g. image/jpeg, audio/ogg, application/pdf


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60, client: Any = None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = client  # injected in tests; otherwise created lazily

    @property
    def configured(self) -> bool:
        return self._client is not None or (bool(self.api_key) and genai is not None)

    def _sdk(self):
        if not self.configured:
            raise AIError("not_configured")
        if self._client is None:
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=genai_types.HttpOptions(timeout=int(self.timeout * 1000)))  # milliseconds
        return self._client

    @staticmethod
    def build_contents(texts: Sequence[str], media: Sequence[Media] = ()) -> List[Any]:
        parts: List[Any] = []
        for item in media:
            if len(item.data) > MAX_MEDIA_BYTES:
                raise AIError("too_large")
            parts.append(genai_types.Part.from_bytes(data=item.data, mime_type=item.mime_type))
        parts.extend(genai_types.Part.from_text(text=text) for text in texts if text)
        return [genai_types.Content(role="user", parts=parts)]

    async def generate(self, texts: Sequence[str], media: Sequence[Media] = (), *, system: Optional[str] = None,
                       schema: Any = None, temperature: float = 0.1) -> str:
        """Run one generate_content call and return the response text (JSON text if `schema` is set)."""
        client = self._sdk()
        cfg = genai_types.GenerateContentConfig(
            system_instruction=system, temperature=temperature,
            response_mime_type="application/json" if schema is not None else None,
            response_schema=schema)
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=self.model, contents=self.build_contents(texts, media), config=cfg),
                timeout=self.timeout + 5)
        except asyncio.TimeoutError:
            raise AIError("timeout")
        except Exception as err:  # SDK / network errors -> one of our codes
            raise self._map_error(err) from err
        text = getattr(response, "text", None)
        if not text:
            log.warning("Gemini returned no text: %r", getattr(response, "prompt_feedback", None))
            raise AIError("bad_response", "empty")
        return text

    async def generate_json(self, texts: Sequence[str], media: Sequence[Media] = (), *, schema: Any,
                            system: Optional[str] = None) -> Any:
        text = await self.generate(texts, media, system=system, schema=schema)
        try:
            return json.loads(text)
        except ValueError:
            raise AIError("bad_response", "invalid JSON")

    @staticmethod
    def _map_error(err: Exception) -> AIError:
        if isinstance(err, AIError):
            return err
        if genai_errors is not None and isinstance(err, genai_errors.APIError):
            code = getattr(err, "code", None)
            message = str(getattr(err, "message", "") or err)
            log.warning("Gemini API error %s: %s", code, message)
            if code == 429:
                return AIError("quota", message)
            if code in (401, 403) or "API key" in message:
                return AIError("auth", message)
            if code == 400:
                return AIError("bad_input", message)
            return AIError("unavailable", message)
        name = type(err).__name__.lower()
        if "timeout" in name:
            return AIError("timeout", str(err))
        log.exception("Gemini request failed")
        return AIError("unavailable", str(err))


_default_client: Optional[GeminiClient] = None


def get_client() -> GeminiClient:
    """Shared client built from data/config.py (GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT)."""
    global _default_client
    if _default_client is None:
        _default_client = GeminiClient(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.GEMINI_TIMEOUT)
    return _default_client


def set_client(client: Optional[GeminiClient]) -> None:
    """Replace the shared client (tests, end-to-end checks)."""
    global _default_client
    _default_client = client


# ---- Operation extraction ----

def _schema():
    """Structured-output schema: a list of draft operations. Missing values are null, never guessed."""
    S, T = genai_types.Schema, genai_types.Type

    def nullable(type_, description, **kw):
        return S(type=type_, nullable=True, description=description, **kw)

    operation = S(
        type=T.OBJECT,
        properties={
            "kind": S(type=T.STRING, enum=["expense", "income", "transfer"],
                      description="expense = money spent, income = money received, "
                                  "transfer = between two of the user's own accounts"),
            "amount": S(type=T.STRING, description="Total amount as a plain decimal: digits and an optional "
                                                   "dot for decimals, no spaces or thousands separators, "
                                                   "e.g. '125000.00'"),
            "currency": nullable(T.STRING, "Currency code", enum=["UZS", "USD"]),
            "category": nullable(T.STRING, "Exact name of one of the user's categories for this kind"),
            "subcategory": nullable(T.STRING, "Exact name of a subcategory of the chosen category"),
            "account_id": nullable(T.INTEGER, "id of the user's account the money left (or, for income, "
                                              "arrived to); for a transfer the source account"),
            "to_account_id": nullable(T.INTEGER, "Transfer only: id of the receiving account"),
            "card_last4": nullable(T.STRING, "Last 4 digits of the card if shown (e.g. from '*1234')"),
            "account_hint": nullable(T.STRING, "Account/bank/payment method as written in the input"),
            "note": nullable(T.STRING, "Short merchant or description, max ~80 characters"),
            "occurred_at": nullable(T.STRING, "Date/time printed on the receipt or SMS, 'YYYY-MM-DD HH:MM'; "
                                              "null if not shown"),
            "confidence": S(type=T.NUMBER, description="0..1, how sure you are about amount and kind"),
        },
        required=["kind", "amount", "confidence"],
        property_ordering=["kind", "amount", "currency", "category", "subcategory", "account_id",
                           "to_account_id", "card_last4", "account_hint", "note", "occurred_at", "confidence"],
    )
    return S(
        type=T.OBJECT,
        properties={
            "input_type": S(type=T.STRING, enum=["receipt", "bank_sms", "text", "voice", "other"]),
            "operations": S(type=T.ARRAY, items=operation),
        },
        required=["input_type", "operations"],
    )


EXTRACTION_SYSTEM = """You turn a user's message into draft financial operations for a personal finance app \
in Uzbekistan. The input may be a receipt photo, a bank SMS / push notification (Uzcard, Humo, Visa; Uzbek, \
Russian or English), a voice message, or free text in Uzbek (Latin or Cyrillic), Russian or English.

Rules:
- Return one operation per separate payment. A receipt is ONE operation: use the TOTAL actually paid \
("Jami", "Итого", "Всего", "To'lov", "Total"), never individual lines, VAT (QQS/НДС) or change. You may \
list up to 3 main items briefly in the note.
- A free-text or voice message may contain several operations ("taksi 25000, kofe 18000") - return each.
- amount: a plain decimal string without thousands separators. Uzbek amounts are written like \
"125 000,00", "125.000" or "125,000" - all of these mean 125000. "18 ming"/"18 тысяч"/"18k" = 18000, \
"12 mln"/"12 млн"/"12m" = 12000000. "so'm", "сум", "sum", "UZS" mean UZS; "$", "dollar", "USD" mean USD.
- Bank SMS: "Pokupka"/"Oplata"/"Списание"/"To'lov"/"Xarid" = expense; "Popolnenie"/"Пополнение"/\
"Зачисление"/"Kirim"/"Tushum" = income. The balance ("Balans"/"Остаток") is NOT the amount. Card digits \
like "*1234" or "8600 **** **** 1234" give card_last4.
- Choose account_id, category and subcategory ONLY from the lists provided by the user context, using the \
exact names/ids. Match accounts by name, bank, card last 4 digits in the account name, or words like \
"naqd"/"наличные"/"cash" for a cash account. If unsure, use null - the user will choose.
- occurred_at only if a date/time is written in the input; otherwise null.
- If the input contains no financial operation or is unreadable, return an empty operations list.
- Do not invent data."""


def build_context(accounts: Sequence[dict], categories: dict, now_text: str) -> str:
    """Plain-text description of the user's data for the prompt.

    accounts: [{id, name, kind, currency}]; categories: {"expense": {name: [subs]}, "income": {name: []}}.
    """
    lines = [f"Current local date and time (Asia/Tashkent): {now_text}", "",
             "User's accounts (id | name | kind | currency):"]
    lines += [f"{a['id']} | {a['name']} | {a['kind']} | {a['currency']}" for a in accounts] or ["(none)"]
    lines += ["", "Expense categories (category: subcategories):"]
    lines += [f"- {name}: {', '.join(subs)}" for name, subs in categories.get("expense", {}).items()] or ["(none)"]
    lines += ["", "Income categories:"]
    lines += [f"- {name}" for name in categories.get("income", {})] or ["(none)"]
    return "\n".join(lines)


async def extract_operations(context: str, text: Optional[str] = None, media: Sequence[Media] = (),
                             client: Optional[GeminiClient] = None) -> dict:
    """Ask Gemini for draft operations. Returns the raw (unvalidated) JSON object."""
    client = client or get_client()
    if not client.configured:
        raise AIError("not_configured")
    texts = [context]
    if text:
        texts.append(f"User message:\n{text}")
    elif media:
        texts.append("Extract the operations from the attached file.")
    result = await client.generate_json(texts, media, schema=_schema(), system=EXTRACTION_SYSTEM)
    if not isinstance(result, dict):
        raise AIError("bad_response", "not an object")
    return result
