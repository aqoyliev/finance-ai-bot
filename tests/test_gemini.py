"""Gemini provider: provider switch, request building, response parsing, the function-calling loop, voice
input and error mapping.

The google-genai SDK client is always faked (responses are real SDK types); no network calls are made.
"""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors
from google.genai import types as T

from data import config
from utils.ai import assistant, claude, core, gemini, tools

from test_assistant import seed
from test_services import USER, setup_user


# ---- Helpers ----

def reply(*parts, finish="STOP", blocked=None):
    feedback = T.GenerateContentResponsePromptFeedback(block_reason=blocked) if blocked else None
    candidates = [] if blocked else [T.Candidate(content=T.Content(role="model", parts=list(parts)),
                                                 finish_reason=finish)]
    return T.GenerateContentResponse(candidates=candidates, prompt_feedback=feedback)


def text(value, thought=False):
    return T.Part(text=value, thought=thought or None)


def call(name, args=None, id_="c1", signature=None):
    return T.Part(function_call=T.FunctionCall(id=id_, name=name, args=args or {}), thought_signature=signature)


class FakeModels:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def fake_client(*results):
    models = FakeModels(*results)
    sdk = SimpleNamespace(aio=SimpleNamespace(models=models))
    return gemini.GeminiClient("", "flash-lite-x", "flash-x", client=sdk), models


def api_error(code, message="boom", status="X"):
    return genai_errors.APIError(code, {"error": {"code": code, "message": message, "status": status}})


@pytest.fixture
def restore_client():
    yield
    core.set_client(None)


# ---- Provider switch ----

def test_provider_selection(monkeypatch, restore_client):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g-key")
    assert config.AI_PROVIDER in core.PROVIDERS
    client = core.make_client("gemini")
    assert isinstance(client, gemini.GeminiClient) and client.configured
    assert (client.extract_model, client.analysis_model) == (config.GEMINI_EXTRACT_MODEL, config.GEMINI_ANALYSIS_MODEL)
    assert client.supports_audio and client.key_name == "GEMINI_API_KEY"
    other = core.make_client("Claude")
    assert isinstance(other, claude.ClaudeClient) and not other.supports_audio
    assert other.extract_model == config.CLAUDE_EXTRACT_MODEL
    with pytest.raises(ValueError):
        core.make_client("openai")

    for provider, kind in (("gemini", gemini.GeminiClient), ("claude", claude.ClaudeClient)):
        monkeypatch.setattr(config, "AI_PROVIDER", provider)
        core.set_client(None)
        assert isinstance(core.get_client(), kind) and core.get_client() is core.get_client()
    # the old import path shares the same switch
    assert claude.get_client is core.get_client and claude.set_client is core.set_client
    fake, _ = fake_client()
    claude.set_client(fake)
    assert core.get_client() is fake


def test_default_models_and_provider():
    assert config.GEMINI_EXTRACT_MODEL == "gemini-3.5-flash-lite"
    assert config.GEMINI_ANALYSIS_MODEL == "gemini-3.8-flash"


async def test_not_configured_without_key():
    client = gemini.GeminiClient("", "m")
    assert client.configured is False
    with pytest.raises(core.AIError) as err:
        await core.extract_operations("CTX", "hi", client=client)
    assert err.value.code == "not_configured"
    with pytest.raises(core.AIError) as err:
        await assistant.ask(USER, "q", "en", client=client)
    assert err.value.code == "not_configured"


# ---- Request building ----

def test_json_schema_conversion():
    schema = gemini.json_schema(core._schema())
    props = schema["properties"]["operations"]["items"]["properties"]
    assert props["category"]["type"] == ["string", "null"] and "anyOf" not in props["category"]
    assert props["account_id"]["type"] == ["integer", "null"]
    assert props["currency"]["anyOf"][0]["enum"] == ["UZS", "USD"]  # nullable enums keep anyOf
    assert props["kind"] == {**core._schema()["properties"]["operations"]["items"]["properties"]["kind"]}
    declarations = gemini.function_declarations(tools.TOOLS)
    assert [d.name for d in declarations] == list(tools.TOOL_NAMES)
    search = next(d for d in declarations if d.name == "search_transactions").parameters_json_schema
    assert search["properties"]["date_from"]["type"] == ["string", "null"]
    assert "strict" not in json.dumps(search) and search["additionalProperties"] is False


def test_extraction_request_shape():
    client, _ = fake_client()
    media = [core.Media(b"jpg", "image/jpeg"), core.Media(b"%PDF", "application/pdf"),
             core.Media(b"OggS", "audio/ogg; codecs=opus")]
    request = client.build_request(["CTX", "Q"], media, system="S", schema=core._schema(), effort="low")
    assert request["model"] == "flash-lite-x"
    [content] = request["contents"]
    assert content.role == "user"
    assert [p.inline_data.mime_type for p in content.parts[:3]] == ["image/jpeg", "application/pdf", "audio/ogg"]
    assert [p.text for p in content.parts[3:]] == ["CTX", "Q"]
    cfg = request["config"]
    assert cfg.system_instruction == "S" and cfg.max_output_tokens == gemini.MAX_TOKENS
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema["type"] == "object"
    assert cfg.thinking_config.thinking_level == T.ThinkingLevel.LOW
    assert cfg.http_options.timeout == client.timeout * 1000 and cfg.temperature is None and cfg.tools is None

    plain = client.build_request(["hi"], model="other", max_tokens=10)
    assert plain["model"] == "other" and plain["config"].response_mime_type is None
    assert plain["config"].thinking_config is None


def test_media_checks():
    client, _ = fake_client()
    with pytest.raises(core.AIError) as err:
        client.build_contents(["x"], [core.Media(b"gif", "image/gif")])  # Gemini reads no GIF
    assert err.value.code == "bad_input"
    with pytest.raises(core.AIError) as err:
        client.build_contents(["x"], [core.Media(b"0" * (gemini.MAX_MEDIA_BYTES + 1), "application/pdf")])
    assert err.value.code == "too_large"
    with pytest.raises(core.AIError) as err:
        client.build_contents(["x"], [core.Media(b"0" * (core.MAX_AUDIO_BYTES + 1), "audio/mpeg")])
    assert err.value.code == "too_large"
    assert client.accepts("image/heic") and client.accepts("audio/x-m4a") and not client.accepts("image/gif")
    assert core.audio_mime("audio/x-wav") == "audio/wav" and core.audio_mime("video/mp4") is None
    assert client.media_limit("audio/ogg") == core.MAX_AUDIO_BYTES


def test_analysis_request_shape():
    client, _ = fake_client()
    history = [client.user_message("q"), {"role": "model", "parts": [
        {"function_call": {"id": "a", "name": "get_accounts", "args": {}}, "thought_signature": "AP9zaWc="}]}]
    request = client.build_analysis_request(history, system="S", effort="medium", max_tokens=1000,
                                            tools=tools.TOOLS, cache=True)
    assert request["model"] == "flash-x"
    cfg = request["config"]
    assert cfg.thinking_config.thinking_level == T.ThinkingLevel.MEDIUM and cfg.max_output_tokens == 1000
    assert len(cfg.tools[0].function_declarations) == 7
    assert cfg.tool_config.function_calling_config.mode == T.FunctionCallingConfigMode.AUTO
    assert cfg.automatic_function_calling.disable is True
    assert cfg.http_options.timeout == client.analysis_timeout * 1000
    # stored base64 signatures are decoded back to the original bytes
    assert request["contents"][1].parts[0].thought_signature == b"\x00\xffsig"


# ---- Extraction responses ----

async def test_extract_operations_parses_json_and_skips_thoughts():
    answer = {"input_type": "text", "intent": "operation", "operations": [{"kind": "expense", "amount": "25000"}]}
    client, models = fake_client(reply(text("thinking...", thought=True), text(json.dumps(answer))))
    result = await core.extract_operations("CTX", None, [core.Media(b"OggS", "audio/ogg")], client=client)
    assert result == answer
    call_ = models.calls[0]
    assert call_["model"] == "flash-lite-x" and call_["config"].system_instruction == core.EXTRACTION_SYSTEM
    texts = [p.text for p in call_["contents"][0].parts if p.text]
    assert texts[0] == "CTX" and "voice message" in texts[1]


@pytest.mark.parametrize("bad, code", [
    (reply(text("{}"), finish="SAFETY"), "refused"),
    (reply(blocked="PROHIBITED_CONTENT"), "refused"),
    (reply(text('{"input'), finish="MAX_TOKENS"), "bad_response"),
    (reply(text("not json")), "bad_response"),
    (reply(text("[1]")), "bad_response"),
    (reply(text("only a thought", thought=True)), "bad_response"),
    (T.GenerateContentResponse(candidates=[]), "bad_response"),
])
async def test_extraction_response_problems(bad, code):
    client, _ = fake_client(bad)
    with pytest.raises(core.AIError) as err:
        await core.extract_operations("CTX", "hi", client=client)
    assert err.value.code == code


# ---- Error mapping ----

@pytest.mark.parametrize("exc, code", [
    (api_error(429, "quota", "RESOURCE_EXHAUSTED"), "quota"),
    (api_error(401, "no", "UNAUTHENTICATED"), "auth"),
    (api_error(403, "no", "PERMISSION_DENIED"), "auth"),
    (api_error(400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"), "auth"),
    (api_error(400, "bad schema", "INVALID_ARGUMENT"), "bad_input"),
    (api_error(413, "too big"), "too_large"),
    (api_error(504, "slow", "DEADLINE_EXCEEDED"), "timeout"),
    (api_error(404, "model not found", "NOT_FOUND"), "unavailable"),
    (api_error(503, "overloaded", "UNAVAILABLE"), "unavailable"),
    (asyncio.TimeoutError(), "timeout"),
    (RuntimeError("weird"), "unavailable"),
])
async def test_client_errors_are_mapped(exc, code):
    client, _ = fake_client(exc)
    with pytest.raises(core.AIError) as err:
        await core.extract_operations("CTX", "hi", client=client)
    assert err.value.code == code


async def test_network_errors_are_mapped():
    import httpx

    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    for exc, code in [(httpx.ReadTimeout("t", request=request), "timeout"),
                      (httpx.ConnectError("c", request=request), "unavailable")]:
        client, _ = fake_client(exc)
        with pytest.raises(core.AIError) as err:
            await client.generate(["x"])
        assert err.value.code == code


async def test_slow_sdk_call_times_out(monkeypatch):
    class Slow:
        async def generate_content(self, **kwargs):
            await asyncio.sleep(5)

    monkeypatch.setattr(gemini, "TIMEOUT_MARGIN", 0)
    client = gemini.GeminiClient("", "m", client=SimpleNamespace(aio=SimpleNamespace(models=Slow())), timeout=0.05)
    with pytest.raises(core.AIError) as err:
        await client.generate(["x"])
    assert err.value.code == "timeout"


# ---- Function-calling loop ----

async def test_tool_loop_round_trip_and_history():
    await seed()
    first = reply(text("plan", thought=True), call("get_accounts", id_="a", signature=b"sig-1"),
                  call("get_period_summary", {"period_offset": 0.0}, id_="b"))
    final = reply(text("**Visa** debt: 3 000 UZS"))
    client, models = fake_client(first, final)
    result = await assistant.ask(USER, "how much do I owe?", "ru", client=client, today=date(2026, 11, 4))
    assert result.text == "Visa debt: 3 000 UZS"
    assert len(models.calls) == 2 and models.calls[1]["model"] == "flash-x"
    question, model_turn, results = models.calls[1]["contents"]
    assert question.role == "user" and "Answer language: Russian" in question.parts[0].text
    # the model turn goes back whole: thought summary, both calls, the signature bytes
    assert model_turn.role == "model" and model_turn.parts[0].thought is True
    assert model_turn.parts[1].thought_signature == b"sig-1"
    assert [p.function_call.name for p in model_turn.parts[1:]] == ["get_accounts", "get_period_summary"]
    assert results.role == "user"
    responses = [p.function_response for p in results.parts]
    assert [(r.id, r.name) for r in responses] == [("a", "get_accounts"), ("b", "get_period_summary")]
    assert "accounts" in responses[0].response["output"]  # the float 0.0 offset was accepted as 0
    assert "currencies" in responses[1].response["output"]

    # The stored turns survive JSON (FSM storage) and are replayed unchanged
    stored = json.loads(json.dumps(result.turns))
    [turn] = stored
    assert turn[1]["parts"][1]["thought_signature"] and turn[-1]["role"] == "model"
    client, models = fake_client(reply(text("Less than last month.")))
    follow = await assistant.ask(USER, "and last month?", "ru", stored, client=client)
    replayed = models.calls[0]["contents"]
    assert len(replayed) == 5 and replayed[1].parts[1].thought_signature == b"sig-1"
    assert len(follow.turns) == 2 and follow.text == "Less than last month."


async def test_tool_errors_go_back_as_error_responses():
    await setup_user()
    client, models = fake_client(reply(call("get_period_summary", {"period_offset": 3})), reply(text("ok")))
    await assistant.ask(USER, "q", "en", client=client)
    [part] = models.calls[1]["contents"][-1].parts
    assert "period_offset" in part.function_response.response["error"]


async def test_tool_loop_iteration_cap():
    await setup_user()
    loops = [reply(call("get_accounts", id_=f"t{i}")) for i in range(assistant.MAX_ITERATIONS)]
    client, models = fake_client(*loops)
    with pytest.raises(core.AIError) as err:
        await assistant.ask(USER, "q", "en", client=client)
    assert err.value.code == "bad_response" and len(models.calls) == assistant.MAX_ITERATIONS
    last = models.calls[-1]["contents"][-1].parts
    assert last[0].function_response is not None and "Answer now" in last[-1].text


@pytest.mark.parametrize("bad, code", [
    (reply(text("x"), finish="SAFETY"), "refused"),
    (reply(text("partial"), finish="MAX_TOKENS"), "bad_response"),
    (reply(text("only thinking", thought=True)), "bad_response"),
    (reply(finish="MALFORMED_FUNCTION_CALL"), "bad_response"),
    (api_error(429, "quota"), "quota"),
])
async def test_tool_loop_failures(bad, code):
    await setup_user()
    client, _ = fake_client(bad)
    with pytest.raises(core.AIError) as err:
        await assistant.ask(USER, "q", "en", client=client)
    assert err.value.code == code


async def test_history_of_the_other_provider_is_dropped():
    await setup_user()
    claude_turn = [[{"role": "user", "content": [{"type": "text", "text": "old"}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "old answer"}]}]]
    client, models = fake_client(reply(text("fresh")))
    result = await assistant.ask(USER, "q", "en", claude_turn, client=client)
    assert len(models.calls[0]["contents"]) == 1 and len(result.turns) == 1


def test_gemini_history_compaction():
    def turn(i):
        return [{"role": "user", "parts": [{"text": f"q{i}"}]},
                {"role": "model", "parts": [{"function_call": {"name": "n", "args": {}}, "thought_signature": "c2ln"}]},
                {"role": "user", "parts": [{"function_response": {"name": "n", "response": {"output": {}}}}]},
                {"role": "model", "parts": [{"text": "hmm", "thought": True}, {"text": f"a{i}"}]}]

    turns = [turn(i) for i in range(assistant.MAX_TURNS)]
    kept = assistant.compact(turns)
    assert kept == [[{"role": "user", "parts": [{"text": f"q{i}"}]}, {"role": "model", "parts": [{"text": f"a{i}"}]}]
                    for i in range(assistant.MAX_TURNS - assistant.KEEP_TURNS, assistant.MAX_TURNS)]


# ---- Advice ----

async def test_advice_with_gemini():
    await seed()
    client, models = fake_client(reply(text("thinking", thought=True), text("**Good** week.\n- tip one")))
    result = await assistant.advice(USER, "now", "uz", client=client)
    assert result.text == "Good week.\n• tip one"
    cfg = models.calls[0]["config"]
    assert cfg.system_instruction == assistant.ADVICE_SYSTEM and cfg.tools is None
    assert cfg.thinking_config.thinking_level == T.ThinkingLevel.MEDIUM
    assert "Uzbek (Latin script)" in models.calls[0]["contents"][0].parts[0].text

    client, _ = fake_client(reply(text("x"), finish="SAFETY"))
    with pytest.raises(core.AIError) as err:
        await assistant.advice(USER, "now", "en", client=client)
    assert err.value.code == "refused"


# ---- Voice handler ----

class FakeMessage:
    def __init__(self, voice=None, audio=None, document=None, caption=None):
        self.voice, self.audio, self.document, self.caption = voice, audio, document, caption
        self.from_user = SimpleNamespace(id=USER)
        self.chat = SimpleNamespace(id=USER)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def voice(duration=5, size=20_000, mime="audio/ogg"):
    return SimpleNamespace(file_id="v1", file_unique_id="uv1", duration=duration, file_size=size, mime_type=mime)


@pytest.fixture
def handler(monkeypatch, restore_client):
    from handlers.users import ai_input

    seen = {"downloads": [], "analyze": []}

    async def fake_download(file_id):
        seen["downloads"].append(file_id)
        return b"OggS-voice"

    async def fake_analyze(message, state, lang, text=None, media=None, source_ref=None):
        seen["analyze"].append((text, media, source_ref))

    monkeypatch.setattr(ai_input, "download_file", fake_download)
    monkeypatch.setattr(ai_input, "analyze", fake_analyze)
    return ai_input, seen


async def test_voice_goes_to_gemini_audio_input(handler):
    ai_input, seen = handler
    core.set_client(fake_client()[0])
    message = FakeMessage(voice=voice(), caption="uob")
    await ai_input.voice_input(message, None, "en")
    assert message.answers == [] and seen["downloads"] == ["v1"]
    [(caption, media, source_ref)] = seen["analyze"]
    assert caption == "uob" and media.mime_type == "audio/ogg" and media.data == b"OggS-voice" and source_ref

    # an audio file and an audio document take the same path
    await ai_input.voice_input(FakeMessage(audio=voice(mime="audio/mpeg")), None, "en")
    document = SimpleNamespace(file_id="d1", file_unique_id="ud1", file_size=1000, mime_type="audio/x-m4a")
    await ai_input.document_input(FakeMessage(document=document), None, "en")
    assert [m.mime_type for _, m, _ in seen["analyze"][1:]] == ["audio/mpeg", "audio/m4a"]


@pytest.mark.parametrize("audio", [voice(duration=core.MAX_AUDIO_SECONDS + 1),
                                   voice(size=core.MAX_AUDIO_BYTES + 1)])
async def test_voice_limits(handler, audio):
    ai_input, seen = handler
    core.set_client(fake_client()[0])
    message = FakeMessage(voice=audio)
    await ai_input.voice_input(message, None, "en")
    [reply_] = message.answers
    assert "too long" in reply_ and "2 minutes" in reply_ and "14 MB" in reply_
    assert seen["downloads"] == [] and seen["analyze"] == []


@pytest.mark.parametrize("lang, phrase", [("en", "need Google Gemini"), ("ru", "Google Gemini"),
                                          ("uz", "Google Gemini")])
async def test_voice_with_claude_provider(handler, lang, phrase):
    ai_input, seen = handler
    core.set_client(claude.ClaudeClient("", "h", "o", client=SimpleNamespace()))
    message = FakeMessage(voice=voice())
    await ai_input.voice_input(message, None, lang)
    assert phrase in message.answers[0] and "AI_PROVIDER=gemini" in message.answers[0]
    assert seen["downloads"] == [] and seen["analyze"] == []


async def test_voice_not_configured_names_the_key(handler):
    ai_input, seen = handler
    core.set_client(gemini.GeminiClient("", "m"))
    message = FakeMessage(voice=voice())
    await ai_input.voice_input(message, None, "en")
    assert "not configured" in message.answers[0] and "GEMINI_API_KEY" in message.answers[0]
    assert seen["downloads"] == []
