"""Anthropic Claude client, prompts and the response schema for AI input.

ClaudeClient is generic (text + optional image/PDF in, text or JSON out, model chosen per call) so later
features such as Q&A over the user's data or weekly advice can reuse it; extract_operations() is the
AI-input use case. Nothing here touches the database: the caller passes a plain-text description of the
user's accounts and categories, and utils/ai/parser.py validates whatever comes back.

Claude has no audio input, so voice messages are not supported.
"""
import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from data import config

try:  # The bot must still start (manual menus only) if the SDK is not installed
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

log = logging.getLogger(__name__)

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
PDF_TYPE = "application/pdf"
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # the API rejects images over 5 MB
MAX_MEDIA_BYTES = 15 * 1024 * 1024  # PDFs; the request limit is 32 MB and base64 adds a third
MAX_TOKENS = 4000
EXTRACT_EFFORT = "low"


def media_limit(mime_type: str) -> int:
    return MAX_IMAGE_BYTES if mime_type in IMAGE_TYPES else MAX_MEDIA_BYTES


class AIError(Exception):
    """A failed AI request. `code` maps to a localized message (ai_error_<code>)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        # not_configured | timeout | quota | auth | bad_input | unavailable | bad_response | too_large | refused
        self.code = code


@dataclass
class Media:
    data: bytes
    mime_type: str  # image/jpeg | image/png | image/gif | image/webp | application/pdf


class ClaudeClient:
    def __init__(self, api_key: str, extract_model: str, analysis_model: str = "", timeout: float = 60,
                 max_retries: int = 1, client: Any = None):
        self.api_key = api_key
        self.extract_model = extract_model
        self.analysis_model = analysis_model or extract_model  # Phase 3 (Q&A, advice): pass model=analysis_model
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client  # injected in tests; otherwise created lazily

    @property
    def configured(self) -> bool:
        return self._client is not None or (bool(self.api_key) and anthropic is not None)

    def _sdk(self):
        if not self.configured:
            raise AIError("not_configured")
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=float(self.timeout),
                                                    max_retries=self.max_retries)
        return self._client

    @staticmethod
    def build_content(texts: Sequence[str], media: Sequence[Media] = ()) -> List[Dict[str, Any]]:
        """Content blocks: media first, then the text blocks."""
        blocks: List[Dict[str, Any]] = []
        for item in media:
            if item.mime_type in IMAGE_TYPES:
                block_type = "image"
            elif item.mime_type == PDF_TYPE:
                block_type = "document"
            else:
                raise AIError("bad_input", f"unsupported media type {item.mime_type}")
            if len(item.data) > media_limit(item.mime_type):
                raise AIError("too_large")
            blocks.append({"type": block_type, "source": {
                "type": "base64", "media_type": item.mime_type,
                "data": base64.standard_b64encode(item.data).decode("ascii")}})
        blocks.extend({"type": "text", "text": text} for text in texts if text)
        return blocks

    def build_request(self, texts: Sequence[str], media: Sequence[Media] = (), *, system: Optional[str] = None,
                      schema: Optional[dict] = None, model: Optional[str] = None,
                      effort: Optional[str] = None, max_tokens: int = MAX_TOKENS) -> Dict[str, Any]:
        """Keyword arguments for messages.create(). No temperature/top_p/top_k: the API rejects them."""
        request: Dict[str, Any] = {
            "model": model or self.extract_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": self.build_content(texts, media)}],
        }
        if system:
            request["system"] = system
        output_config: Dict[str, Any] = {}
        if effort:
            output_config["effort"] = effort
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        if output_config:
            request["output_config"] = output_config
        return request

    async def generate(self, texts: Sequence[str], media: Sequence[Media] = (), *, system: Optional[str] = None,
                       schema: Optional[dict] = None, model: Optional[str] = None,
                       effort: Optional[str] = None, max_tokens: int = MAX_TOKENS) -> str:
        """Run one messages.create call and return the text (JSON text if `schema` is set)."""
        client = self._sdk()
        request = self.build_request(texts, media, system=system, schema=schema, model=model, effort=effort,
                                     max_tokens=max_tokens)
        try:
            response = await client.messages.create(**request)
        except Exception as err:  # SDK / network errors -> one of our codes
            raise self._map_error(err) from err
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise AIError("refused")
        if stop_reason == "max_tokens":
            raise AIError("bad_response", "max_tokens")
        # Skip thinking blocks: only text blocks carry the answer
        text = "".join(block.text for block in (getattr(response, "content", None) or [])
                       if getattr(block, "type", None) == "text" and getattr(block, "text", None))
        if not text:
            log.warning("Claude returned no text (stop_reason=%r)", stop_reason)
            raise AIError("bad_response", "empty")
        return text

    async def generate_json(self, texts: Sequence[str], media: Sequence[Media] = (), *, schema: dict,
                            system: Optional[str] = None, model: Optional[str] = None,
                            effort: Optional[str] = None, max_tokens: int = MAX_TOKENS) -> Any:
        text = await self.generate(texts, media, system=system, schema=schema, model=model, effort=effort,
                                   max_tokens=max_tokens)
        try:
            return json.loads(text)
        except ValueError:
            raise AIError("bad_response", "invalid JSON")

    @staticmethod
    def _map_error(err: Exception) -> AIError:
        if isinstance(err, AIError):
            return err
        if anthropic is not None:
            # Most specific first (APITimeoutError is an APIConnectionError; status errors are APIStatusError)
            if isinstance(err, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
                code = "auth"
            elif isinstance(err, anthropic.RateLimitError):
                code = "quota"
            elif isinstance(err, anthropic.RequestTooLargeError):
                code = "too_large"
            elif isinstance(err, anthropic.BadRequestError):
                code = "bad_input"
            elif isinstance(err, anthropic.APITimeoutError):
                code = "timeout"
            elif isinstance(err, (anthropic.APIConnectionError, anthropic.APIStatusError)):
                code = "unavailable"  # connection, 5xx, 529 overloaded, 404 unknown model, ...
            else:
                code = ""
            if code:
                log.warning("Claude API error (%s): %s", code, err)
                return AIError(code, str(err))
        log.exception("Claude request failed")
        return AIError("unavailable", str(err))


_default_client: Optional[ClaudeClient] = None


def get_client() -> ClaudeClient:
    """Shared client built from data/config.py (ANTHROPIC_API_KEY, CLAUDE_*_MODEL, CLAUDE_TIMEOUT)."""
    global _default_client
    if _default_client is None:
        _default_client = ClaudeClient(config.ANTHROPIC_API_KEY, config.CLAUDE_EXTRACT_MODEL,
                                       config.CLAUDE_ANALYSIS_MODEL, config.CLAUDE_TIMEOUT)
    return _default_client


def set_client(client: Optional[ClaudeClient]) -> None:
    """Replace the shared client (tests, end-to-end checks)."""
    global _default_client
    _default_client = client


# ---- Operation extraction ----

def _field(schema: dict, description: str, nullable: bool = True) -> dict:
    """A described property; nullable ones become anyOf [schema, null] (structured outputs have no `nullable`)."""
    return {"anyOf": [schema, {"type": "null"}], "description": description} if nullable \
        else {**schema, "description": description}


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
            "operations": {"type": "array", "items": operation},
        },
        "required": ["input_type", "operations"],
        "additionalProperties": False,
    }


EXTRACTION_SYSTEM = """You turn a user's message into draft financial operations for a personal finance app \
in Uzbekistan. The input may be a receipt photo or PDF, a bank SMS / push notification (Uzcard, Humo, Visa; \
Uzbek, Russian or English), or free text in Uzbek (Latin or Cyrillic), Russian or English.

Rules:
- Return one operation per separate payment. A receipt is ONE operation: use the TOTAL actually paid \
("Jami", "Итого", "Всего", "To'lov", "Total"), never individual lines, VAT (QQS/НДС) or change. You may \
list up to 3 main items briefly in the note.
- A free-text message may contain several operations ("taksi 25000, kofe 18000") - return each.
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
                             client: Optional[ClaudeClient] = None) -> dict:
    """Ask Claude (the extraction model) for draft operations. Returns the raw (unvalidated) JSON object."""
    client = client or get_client()
    if not client.configured:
        raise AIError("not_configured")
    texts = [context]
    if text:
        texts.append(f"User message:\n{text}")
    elif media:
        texts.append("Extract the operations from the attached file.")
    result = await client.generate_json(texts, media, schema=_schema(), system=EXTRACTION_SYSTEM,
                                        model=client.extract_model, effort=EXTRACT_EFFORT)
    if not isinstance(result, dict):
        raise AIError("bad_response", "not an object")
    return result
