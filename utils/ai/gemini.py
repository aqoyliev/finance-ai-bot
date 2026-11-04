"""Google Gemini client (AI_PROVIDER=gemini, Google AI Studio key) on the official google-genai SDK.

GeminiClient implements the provider interface described in utils/ai/core.py with generateContent:
- generate()/generate_json(): text + optional image/PDF/audio in, text or JSON out (structured output with a
  JSON Schema); a voice message is transcribed and extracted in the same call.
- analysis_step(): one request of the analysis model with manual function calling (automatic function calling
  is off; the tool loop lives in utils/ai/assistant.py).

The shared schemas are written for Claude's structured outputs (nullable values as anyOf [X, null]); they are
converted to type arrays (["string", "null"]), the form the Gemini docs give for nullable values (nullable
enums keep anyOf, which the docs also list).
History messages are plain dicts in the SDK's own field names ({"role": "user" | "model", "parts": [...]}), so
they survive FSM storage; model turns are stored whole (thought signatures included, base64) and sent back
unchanged, as Gemini 3 requires for function calling.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .core import MAX_AUDIO_BYTES, PDF_TYPE, AIError, Media, Step, ToolCall, audio_mime

try:  # The bot must still start (manual menus only) if the SDK is not installed
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = genai_errors = genai_types = None

_HTTP_LIBS = []  # the SDK may run on httpx or httpx2; network errors of both are mapped
for _name in ("httpx", "httpx2"):
    try:
        _HTTP_LIBS.append(__import__(_name))
    except ImportError:  # pragma: no cover
        pass

log = logging.getLogger(__name__)

IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif")
MAX_MEDIA_BYTES = 14 * 1024 * 1024  # images and PDFs; the inline request limit is 20 MB including base64
TIMEOUT_MARGIN = 5  # seconds on top of the SDK timeout for the outer asyncio guard
MAX_TOKENS = 4000  # extraction: small JSON answers (thinking tokens count towards it)
EFFORTS = ("minimal", "low", "medium", "high")  # effort names map 1:1 onto Gemini thinking levels
# Finish reasons that mean the model declined (safety filters) rather than failed
REFUSAL_REASONS = ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION", "IMAGE_SAFETY",
                   "IMAGE_PROHIBITED_CONTENT")
BAD_CALL_REASONS = ("MALFORMED_FUNCTION_CALL", "UNEXPECTED_TOOL_CALL", "TOO_MANY_TOOL_CALLS")


def json_schema(schema: Any) -> Any:
    """Shared JSON Schema -> the form the Gemini docs describe: anyOf [X, null] becomes X with a type array,
    and the Claude-only `strict` flag is dropped."""
    if isinstance(schema, list):
        return [json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    options = schema.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options:
        other = next(option for option in options if option != {"type": "null"})
        # Enums stay anyOf [enum, null] (a type array would also need null inside the enum)
        if isinstance(other.get("type"), str) and "enum" not in other:
            merged = {**json_schema(other), "type": [other["type"], "null"]}
            if "description" in schema:
                merged["description"] = schema["description"]
            return merged
    return {key: json_schema(value) for key, value in schema.items() if key != "strict"}


def function_declarations(tools: Sequence[dict]) -> List[Any]:
    """Our tool definitions (name, description, input_schema) as Gemini function declarations."""
    return [genai_types.FunctionDeclaration(name=tool["name"], description=tool["description"],
                                            parameters_json_schema=json_schema(tool["input_schema"]))
            for tool in tools]


def _value(enum: Any) -> Optional[str]:
    if enum is None:
        return None
    return str(getattr(enum, "value", enum))


def _integral(value: Any) -> Any:
    """Whole floats from function-call arguments back to int (the tools validate integers strictly)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _content_dict(content: Any) -> Dict[str, Any]:
    """A model Content as a JSON-compatible dict (bytes such as thought signatures become base64)."""
    dump = getattr(content, "model_dump", None)
    if dump is not None:
        data = dump(mode="json", exclude_none=True)
    else:  # plain objects (tests)
        data = {"role": getattr(content, "role", None), "parts": [
            {key: value for key, value in vars(part).items() if value is not None}
            for part in getattr(content, "parts", None) or []]}
    data["role"] = "model"
    data.setdefault("parts", [])
    return data


def _to_content(message: Dict[str, Any]) -> Any:
    """A stored history dict -> types.Content; JSON-mode validation decodes the base64 thought signatures."""
    return genai_types.Content.model_validate_json(json.dumps(message))


def _parts(response: Any) -> Tuple[Any, List[Any]]:
    """(candidate, parts) after checking the prompt feedback and the finish reason."""
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise AIError("refused", _value(feedback.block_reason) or "")
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise AIError("bad_response", "no candidates")
    candidate = candidates[0]
    reason = _value(getattr(candidate, "finish_reason", None))
    if reason in REFUSAL_REASONS:
        raise AIError("refused", reason)
    if reason == "MAX_TOKENS":
        raise AIError("bad_response", "max_tokens")
    if reason in BAD_CALL_REASONS:
        raise AIError("bad_response", reason)
    content = getattr(candidate, "content", None)
    return candidate, list(getattr(content, "parts", None) or [])


def _text(parts: Sequence[Any]) -> str:
    """The answer: text parts only (thought summaries are skipped)."""
    return "".join(part.text for part in parts if getattr(part, "text", None) and not getattr(part, "thought", None))


class GeminiClient:
    provider = "gemini"
    key_name = "GEMINI_API_KEY"
    supports_audio = True
    document_types = IMAGE_TYPES + (PDF_TYPE,)

    def __init__(self, api_key: str, extract_model: str, analysis_model: str = "", timeout: float = 60,
                 client: Any = None, analysis_timeout: float = 180):
        self.api_key = api_key
        self.extract_model = extract_model  # receipts, SMS, free text, voice
        self.analysis_model = analysis_model or extract_model  # Q&A and advice
        self.timeout = timeout
        self.analysis_timeout = analysis_timeout
        self._client = client  # injected in tests; otherwise created lazily

    @property
    def configured(self) -> bool:
        return self._client is not None or (bool(self.api_key) and genai is not None)

    def accepts(self, mime_type: str) -> bool:
        return mime_type in self.document_types or audio_mime(mime_type) is not None

    @staticmethod
    def media_limit(mime_type: str) -> int:
        return MAX_AUDIO_BYTES if audio_mime(mime_type) else MAX_MEDIA_BYTES

    def _sdk(self):
        if not self.configured:
            raise AIError("not_configured")
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    # ---- Requests ----

    def build_contents(self, texts: Sequence[str], media: Sequence[Media] = ()) -> List[Any]:
        """One user Content: media parts first, then the text parts."""
        parts: List[Any] = []
        for item in media:
            mime = audio_mime(item.mime_type) or item.mime_type
            if mime not in self.document_types and not audio_mime(mime):
                raise AIError("bad_input", f"unsupported media type {item.mime_type}")
            if len(item.data) > self.media_limit(mime):
                raise AIError("too_large")
            parts.append(genai_types.Part.from_bytes(data=item.data, mime_type=mime))
        parts.extend(genai_types.Part.from_text(text=text) for text in texts if text)
        return [genai_types.Content(role="user", parts=parts)]

    @staticmethod
    def build_config(*, system: Optional[str], timeout: float, max_tokens: int, effort: Optional[str] = None,
                     schema: Optional[dict] = None, tools: Optional[Sequence[dict]] = None) -> Any:
        """GenerateContentConfig. Effort maps onto the thinking level; temperature stays at the model default
        (recommended for Gemini 3)."""
        options: Dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "http_options": genai_types.HttpOptions(timeout=int(timeout * 1000)),  # milliseconds
        }
        if system:
            options["system_instruction"] = system
        if effort in EFFORTS:
            options["thinking_config"] = genai_types.ThinkingConfig(thinking_level=effort.upper())
        if schema is not None:
            options["response_mime_type"] = "application/json"
            options["response_json_schema"] = json_schema(schema)
        if tools:
            options["tools"] = [genai_types.Tool(function_declarations=function_declarations(tools))]
            options["tool_config"] = genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(mode="AUTO"))
            options["automatic_function_calling"] = genai_types.AutomaticFunctionCallingConfig(disable=True)
        return genai_types.GenerateContentConfig(**options)

    def build_request(self, texts: Sequence[str], media: Sequence[Media] = (), *, system: Optional[str] = None,
                      schema: Optional[dict] = None, model: Optional[str] = None,
                      effort: Optional[str] = None, max_tokens: int = MAX_TOKENS) -> Dict[str, Any]:
        """Keyword arguments for models.generate_content()."""
        return {
            "model": model or self.extract_model,
            "contents": self.build_contents(texts, media),
            "config": self.build_config(system=system, timeout=self.timeout, max_tokens=max_tokens,
                                        effort=effort, schema=schema),
        }

    async def _send(self, request: Dict[str, Any], timeout: float) -> Any:
        client = self._sdk()
        try:
            # The SDK timeout covers the HTTP request; this guard also covers retries and slow streams
            return await asyncio.wait_for(client.aio.models.generate_content(**request), timeout + TIMEOUT_MARGIN)
        except Exception as err:  # SDK / network errors -> one of our codes
            raise self._map_error(err) from err

    async def generate(self, texts: Sequence[str], media: Sequence[Media] = (), *, system: Optional[str] = None,
                       schema: Optional[dict] = None, model: Optional[str] = None,
                       effort: Optional[str] = None, max_tokens: int = MAX_TOKENS) -> str:
        """Run one generate_content call and return the text (JSON text if `schema` is set)."""
        request = self.build_request(texts, media, system=system, schema=schema, model=model, effort=effort,
                                     max_tokens=max_tokens)
        response = await self._send(request, self.timeout)
        _, parts = _parts(response)
        text = _text(parts)
        if not text:
            log.warning("Gemini returned no text")
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

    def build_analysis_request(self, messages: List[dict], *, system: str, effort: str, max_tokens: int,
                               tools: Optional[List[dict]] = None, cache: bool = False) -> Dict[str, Any]:
        """Keyword arguments for one analysis-model request. `cache` is accepted for interface parity: Gemini
        caches repeated prefixes implicitly."""
        return {
            "model": self.analysis_model,
            "contents": [_to_content(message) for message in messages],
            "config": self.build_config(system=system, timeout=self.analysis_timeout, max_tokens=max_tokens,
                                        effort=effort, tools=tools),
        }

    async def create_analysis(self, request: Dict[str, Any]) -> Any:
        return await self._send(request, self.analysis_timeout)

    # ---- Conversation interface (see utils/ai/core.py) ----

    @staticmethod
    def user_message(text: str) -> Dict[str, Any]:
        return {"role": "user", "parts": [{"text": text}]}

    @staticmethod
    def owns_history(message: Any) -> bool:
        return isinstance(message, dict) and "parts" in message

    async def analysis_step(self, messages: List[dict], *, system: str, effort: str, max_tokens: int,
                            tools: Optional[List[dict]] = None, cache: bool = False) -> Step:
        request = self.build_analysis_request(messages, system=system, effort=effort, max_tokens=max_tokens,
                                              tools=tools, cache=cache)
        response = await self.create_analysis(request)
        candidate, parts = _parts(response)
        message = _content_dict(candidate.content) if getattr(candidate, "content", None) is not None \
            else {"role": "model", "parts": []}
        calls = []
        for index, part in enumerate(parts):
            call = getattr(part, "function_call", None)
            if call is None:
                continue
            args = getattr(call, "args", None)
            if isinstance(args, dict):
                args = {key: _integral(value) for key, value in args.items()}
            calls.append(ToolCall(getattr(call, "id", None) or "", call.name, args if args is not None else {}))
        if calls:
            return Step("tool_use", message, _text(parts), calls)
        if _value(getattr(candidate, "finish_reason", None)) == "CONTINUATION":
            return Step("pause", message, _text(parts))
        return Step("end", message, _text(parts))

    @staticmethod
    def tool_results_message(results: Sequence[Tuple[ToolCall, str, bool]],
                             note: Optional[str] = None) -> Dict[str, Any]:
        """All function responses of a turn in one user message (same order as the calls), then the note.

        Results go under "output", failures under "error", as the function-calling docs describe."""
        parts: List[Dict[str, Any]] = []
        for call, output, is_error in results:
            try:
                data = json.loads(output)
            except ValueError:
                data = output
            if is_error and isinstance(data, dict) and "error" in data:
                data = data["error"]
            response = {"error": data} if is_error else {"output": data}
            function_response: Dict[str, Any] = {"name": call.name, "response": response}
            if call.id:
                function_response["id"] = call.id
            parts.append({"function_response": function_response})
        if note:
            parts.append({"text": note})
        return {"role": "user", "parts": parts}

    # ---- Errors ----

    @staticmethod
    def _map_error(err: Exception) -> AIError:
        if isinstance(err, AIError):
            return err
        if isinstance(err, asyncio.TimeoutError):
            return AIError("timeout", "no answer in time")
        if genai_errors is not None and isinstance(err, genai_errors.APIError):
            status = getattr(err, "code", None)
            reason = str(getattr(err, "status", "") or "")
            message = str(getattr(err, "message", "") or err)
            if status == 429 or reason == "RESOURCE_EXHAUSTED":
                code = "quota"
            elif status in (401, 403) or reason in ("UNAUTHENTICATED", "PERMISSION_DENIED") \
                    or "API key" in message or "API_KEY" in message:
                code = "auth"  # an invalid key comes back as 400 INVALID_ARGUMENT "API key not valid"
            elif status == 413:
                code = "too_large"
            elif status in (408, 504) or reason == "DEADLINE_EXCEEDED":
                code = "timeout"
            elif status == 400:
                code = "bad_input"
            else:
                code = "unavailable"  # 404 unknown model, 5xx, 503 overloaded, ...
            log.warning("Gemini API error %s (%s): %s", status, code, message)
            return AIError(code, message)
        for lib in _HTTP_LIBS:
            if isinstance(err, lib.TimeoutException):
                return AIError("timeout", str(err))
            if isinstance(err, lib.HTTPError):
                log.warning("Gemini connection error: %s", err)
                return AIError("unavailable", str(err))
        if "timeout" in type(err).__name__.lower():
            return AIError("timeout", str(err))
        log.exception("Gemini request failed")
        return AIError("unavailable", str(err))
