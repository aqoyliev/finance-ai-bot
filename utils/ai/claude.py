"""Anthropic Claude client (AI_PROVIDER=claude).

ClaudeClient implements the provider interface described in utils/ai/core.py: generate()/generate_json() run
one request (text + optional image/PDF in, text or JSON out) and analysis_step() runs one request of the
analysis model (the Q&A tool loop and the advice live in utils/ai/assistant.py). The extraction prompt and
schema are shared with Gemini and live in core.py; they are re-exported here for compatibility.

Claude has no audio input, so voice messages are not supported with this provider.
"""
import base64
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Shared names re-exported for older imports (utils.ai.claude.AIError, extract_operations, ...)
from .core import (EXTRACT_EFFORT, EXTRACTION_SYSTEM, INTENTS, IMAGE_TYPES, PDF_TYPE, AIError,  # noqa: F401
                   Media, Step, ToolCall, _field, _schema, build_context, extract_operations, get_client,
                   set_client)

try:  # The bot must still start (manual menus only) if the SDK is not installed
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # the API rejects images over 5 MB
MAX_MEDIA_BYTES = 15 * 1024 * 1024  # PDFs; the request limit is 32 MB and base64 adds a third
MAX_TOKENS = 4000
# Server-side refusal fallback for the analysis model: a policy decline is retried on the model Anthropic
# recommends for that category, within the same request (beta; the "default" form needs exactly this header)
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Model-internal blocks; after a fallback the ones from the declined attempt must not be echoed back
_MODEL_BLOCKS = ("thinking", "redacted_thinking", "tool_use")


def media_limit(mime_type: str) -> int:
    return MAX_IMAGE_BYTES if mime_type in IMAGE_TYPES else MAX_MEDIA_BYTES


class ClaudeClient:
    provider = "claude"
    key_name = "ANTHROPIC_API_KEY"
    supports_audio = False
    document_types = IMAGE_TYPES + (PDF_TYPE,)  # no HEIC

    def __init__(self, api_key: str, extract_model: str, analysis_model: str = "", timeout: float = 60,
                 max_retries: int = 1, client: Any = None, analysis_timeout: float = 180,
                 fallbacks: bool = True):
        self.api_key = api_key
        self.extract_model = extract_model
        self.analysis_model = analysis_model or extract_model  # Q&A and advice
        self.timeout = timeout
        self.analysis_timeout = analysis_timeout  # per analysis request (thinking takes longer)
        self.fallbacks = fallbacks  # server-side refusal fallback on analysis requests
        self.max_retries = max_retries
        self._client = client  # injected in tests; otherwise created lazily

    @property
    def configured(self) -> bool:
        return self._client is not None or (bool(self.api_key) and anthropic is not None)

    def accepts(self, mime_type: str) -> bool:
        return mime_type in self.document_types

    @staticmethod
    def media_limit(mime_type: str) -> int:
        return media_limit(mime_type)

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

    def build_analysis_request(self, messages: List[dict], *, system: str, effort: str, max_tokens: int,
                               tools: Optional[List[dict]] = None, cache: bool = False) -> Dict[str, Any]:
        """Keyword arguments for one analysis-model request.

        No temperature/top_p/top_k and no `thinking` field (thinking is always on for the analysis model;
        `disabled` and `budget_tokens` are rejected): `effort` is the depth/cost control. Tools are offered with
        tool_choice auto (forcing a tool is rejected). With cache=True the system prompt (rendered after the
        tools, so both are covered) gets an explicit breakpoint, and top-level automatic caching follows the
        growing conversation inside a tool loop."""
        system_block: Dict[str, Any] = {"type": "text", "text": system}
        if cache:
            system_block["cache_control"] = {"type": "ephemeral"}
        request: Dict[str, Any] = {
            "model": self.analysis_model,
            "max_tokens": max_tokens,
            "system": [system_block],
            "messages": messages,
            "output_config": {"effort": effort},
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = {"type": "auto"}
        if cache:
            request["cache_control"] = {"type": "ephemeral"}
        if self.fallbacks:
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = "default"
        return request

    async def create_analysis(self, request: Dict[str, Any]) -> Any:
        """Send a request built by build_analysis_request; SDK errors become AIError. The caller checks
        stop_reason (refusal, max_tokens, tool_use, pause_turn) before reading content."""
        client = self._sdk()
        endpoint = client.beta.messages if "betas" in request else client.messages
        try:
            return await endpoint.create(**request, timeout=float(self.analysis_timeout))
        except Exception as err:  # SDK / network errors -> one of our codes
            raise self._map_error(err) from err

    # ---- Conversation interface (see utils/ai/core.py) ----

    @staticmethod
    def user_message(text: str) -> Dict[str, Any]:
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    @staticmethod
    def owns_history(message: Any) -> bool:
        return isinstance(message, dict) and "content" in message

    async def analysis_step(self, messages: List[dict], *, system: str, effort: str, max_tokens: int,
                            tools: Optional[List[dict]] = None, cache: bool = False) -> Step:
        """One analysis request; refusal and truncation raise AIError (stop_reason is checked first)."""
        request = self.build_analysis_request(messages, system=system, effort=effort, max_tokens=max_tokens,
                                              tools=tools, cache=cache)
        response = await self.create_analysis(request)
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            raise AIError("refused")
        if stop_reason == "max_tokens":
            raise AIError("bad_response", "max_tokens")
        message = {"role": "assistant", "content": assistant_content(response.content)}
        if stop_reason == "pause_turn":  # server-side pause: send the turn back as is to continue
            return Step("pause", message)
        calls = [ToolCall(block.id, block.name, block.input) for block in response.content or []
                 if getattr(block, "type", None) == "tool_use"]
        return Step("tool_use" if stop_reason == "tool_use" and calls else "end", message,
                    response_text(response), calls)

    @staticmethod
    def tool_results_message(results: Sequence[Tuple[ToolCall, str, bool]],
                             note: Optional[str] = None) -> Dict[str, Any]:
        """All tool_result blocks of a turn in one user message, then the optional note as a text block."""
        content: List[Dict[str, Any]] = []
        for call, output, is_error in results:
            block = {"type": "tool_result", "tool_use_id": call.id, "content": output}
            if is_error:
                block["is_error"] = True
            content.append(block)
        if note:
            content.append({"type": "text", "text": note})
        return {"role": "user", "content": content}

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


def response_text(response: Any) -> str:
    """The answer: text blocks only (thinking, tool_use and fallback markers are skipped)."""
    return "".join(block.text for block in (getattr(response, "content", None) or [])
                   if getattr(block, "type", None) == "text" and getattr(block, "text", None))


def _block_param(block: Any) -> Optional[Dict[str, Any]]:
    kind = getattr(block, "type", None)
    if kind == "text":
        return {"type": "text", "text": block.text}
    if kind == "thinking":
        return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
    if kind == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    if kind == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if kind == "fallback" or kind is None:
        return None
    dump = getattr(block, "model_dump", None)  # any other block type: pass it through as the API sent it
    return dump(mode="json", exclude_none=True) if dump else None


def assistant_content(content: Sequence[Any]) -> List[Dict[str, Any]]:
    """Assistant content as request params, to append to the history unchanged (thinking blocks included).

    After a server-side fallback, model-internal blocks (thinking, tool_use) that precede the last `fallback`
    marker belong to the declined attempt and are omitted, as the API requires; the marker itself is dropped."""
    content = list(content or [])
    cut = max((i for i, block in enumerate(content) if getattr(block, "type", None) == "fallback"), default=-1)
    params = []
    for index, block in enumerate(content):
        if index < cut and getattr(block, "type", None) in _MODEL_BLOCKS:
            continue
        param = _block_param(block)
        if param is not None:
            params.append(param)
    return params
