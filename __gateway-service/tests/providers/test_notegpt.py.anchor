"""NoteGPT AI Provider Facade & Parity Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests hermetic execution with mocked SSE transport.
- Tests error mapping to canonical 12 categories without leakage.
"""

from __future__ import annotations

import json
import pytest
import httpx

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
    ProviderDefinition,
)
from providers.notegpt.definition import DEFINITION
from providers.notegpt.adapter import HANDLERS, generate_text, synthesize_speech
from providers.notegpt import _core


def build_speech_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.SYNTHESIZE_SPEECH,
        model="text-to-speech",
        request_id="req-notegpt-audio-test",
        tenant_id="tenant-notegpt-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"text": "أهلاً وسهلاً بكم في مصر"} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))



def build_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="kimi-k3",
        request_id="req-notegpt-test",
        tenant_id="tenant-notegpt-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "1+1=?"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_notegpt_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "NoteGPT AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert set(parsed.operations) == {
        GatewayOperation.GENERATE_TEXT,
        GatewayOperation.SYNTHESIZE_SPEECH,
    }

    model_names = [m.name for m in parsed.models]
    assert set(model_names) == {"kimi-k3", "deepseek-v4-flash", "text-to-speech"}

    # Check capabilities in closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("code") is True
    assert parsed.capabilities.get("audio_output") is True
    assert not parsed.capabilities.get("image_generation", False)



@pytest.mark.asyncio
async def test_notegpt_unsupported_model_rejected():
    """Models other than kimi-k3 and deepseek-v4-flash (e.g. gpt-4.1-mini or glm-5.2) are rejected."""
    ctx = build_context(model="gpt-4.1-mini")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.MODEL_UNAVAILABLE


def test_notegpt_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


@pytest.mark.asyncio
async def test_notegpt_credential_mode_protection():
    """Passing caller user_key credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="user-supplied-key")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_notegpt_payload_validation():
    """Malformed payload triggers BAD_REQUEST."""
    # Empty messages
    ctx_empty = build_context(payload={"messages": []})
    res_empty = await generate_text(ctx_empty)
    assert not res_empty.succeeded
    assert res_empty.error.category is ErrorCategory.BAD_REQUEST

    # Extra keys in message dict
    ctx_extra = build_context(payload={"messages": [{"role": "user", "content": "hi", "foo": "bar"}]})
    res_extra = await generate_text(ctx_extra)
    assert not res_extra.succeeded
    assert res_extra.error.category is ErrorCategory.BAD_REQUEST

    # Non-string content
    ctx_bad_content = build_context(payload={"messages": [{"role": "user", "content": 123}]})
    res_bad = await generate_text(ctx_bad_content)
    assert not res_bad.succeeded
    assert res_bad.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_notegpt_hermetic_chat_success():
    """Hermetic execution with mocked SSE stream returning start and text chunks."""
    sse_response = (
        'data: {"type": "start", "id": "test-session-123", "msg_id": "m123"}\n\n'
        'data: {"type": "text", "text": "1+1=2"}\n\n'
        'data: {"type": "credit_usage", "data": {"credits": 1}}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_response, headers={"content-type": "text/event-stream"})

    mock_transport = httpx.MockTransport(handler)
    _core._default_transport = mock_transport

    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert res.succeeded
        assert res.output["text"] == "1+1=2"
        assert res.output["finish_reason"] == "stop"
        assert res.usage.units == 1
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_error_mapping_rate_limit():
    """HTTP 429 maps to RATE_LIMITED."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    _core._default_transport = httpx.MockTransport(handler)
    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RATE_LIMITED
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_error_mapping_quota_exhausted():
    """Code 164019 in body maps to QUOTA_EXCEEDED."""
    body = json.dumps({"code": 164019, "message": "Insufficient Free Quotas"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    _core._default_transport = httpx.MockTransport(handler)
    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.QUOTA_EXCEEDED
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_error_mapping_auth_expired():
    """Code 164002 in body maps to AUTH_EXPIRED."""
    body = json.dumps({"code": 164002, "message": "Session Expired"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    _core._default_transport = httpx.MockTransport(handler)
    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.AUTH_EXPIRED
    finally:
        _core._default_transport = None


def test_notegpt_session_stickiness_and_auto_create_toggle():
    """Verify session stickiness: same session_id reuses identical account, does not recreate."""
    assert isinstance(_core.AUTO_CREATE_ACCOUNT_ON_NEW_CHAT, bool)

    test_sess_id = "test-multi-turn-session-xyz"
    _core._ACTIVE_CHAT_SESSIONS.pop(test_sess_id, None)

    # 1. First turn: new chat
    token1, acc1 = _core.select_account_token(session_id=test_sess_id, is_new_chat=True)
    assert token1 is not None
    assert test_sess_id in _core._ACTIVE_CHAT_SESSIONS

    # 2. Second turn: continuing same chat session (is_new_chat=False)
    token2, acc2 = _core.select_account_token(session_id=test_sess_id, is_new_chat=False)
    assert token2 == token1
    assert acc2 == acc1

    # Cleanup
    _core._ACTIVE_CHAT_SESSIONS.pop(test_sess_id, None)


@pytest.mark.asyncio
async def test_notegpt_adapter_session_propagation():
    """Adapter propagates session_id from payload and maintains stickiness."""
    sse_response = (
        'data: {"type": "start", "id": "test-session-123"}\n\n'
        'data: {"type": "text", "text": "session reply"}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_response, headers={"content-type": "text/event-stream"})

    _core._default_transport = httpx.MockTransport(handler)
    sess_id = "sticky-session-999"
    _core._ACTIVE_CHAT_SESSIONS.pop(sess_id, None)

    try:
        ctx1 = build_context(payload={"messages": [{"role": "user", "content": "turn 1"}], "session_id": sess_id})
        res1 = await generate_text(ctx1)
        assert res1.succeeded
        assert sess_id in _core._ACTIVE_CHAT_SESSIONS
        acc_turn1 = _core._ACTIVE_CHAT_SESSIONS[sess_id]

        ctx2 = build_context(payload={"messages": [{"role": "user", "content": "turn 2"}], "session_id": sess_id})
        res2 = await generate_text(ctx2)
        assert res2.succeeded
        assert _core._ACTIVE_CHAT_SESSIONS[sess_id] is acc_turn1
    finally:
        _core._default_transport = None
        _core._ACTIVE_CHAT_SESSIONS.pop(sess_id, None)


@pytest.mark.asyncio
async def test_notegpt_speech_credential_mode_protection():
    """Passing caller user_key credentials to synthesize_speech must fail as INVALID_CREDENTIAL."""
    ctx = build_speech_context(credential_mode=CredentialMode.USER_KEY, credential_value="user-supplied-key")
    res = await synthesize_speech(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_notegpt_speech_payload_validation():
    """Malformed speech payload triggers BAD_REQUEST."""
    # Missing text
    ctx_missing = build_speech_context(payload={})
    res_missing = await synthesize_speech(ctx_missing)
    assert not res_missing.succeeded
    assert res_missing.error.category is ErrorCategory.BAD_REQUEST

    # Non-string text
    ctx_bad_text = build_speech_context(payload={"text": 12345})
    res_bad_text = await synthesize_speech(ctx_bad_text)
    assert not res_bad_text.succeeded
    assert res_bad_text.error.category is ErrorCategory.BAD_REQUEST

    # Non-string voice
    ctx_bad_voice = build_speech_context(payload={"text": "hello", "voice": 999})
    res_bad_voice = await synthesize_speech(ctx_bad_voice)
    assert not res_bad_voice.succeeded
    assert res_bad_voice.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_notegpt_hermetic_synthesize_speech():
    """Hermetic synthesize_speech with mock transport returning CDN audio URL and base64 payload."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "api/v2/tts/generate" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "code": 100000,
                    "message": "success",
                    "data": {
                        "audio_url": "https://cdn.ng-resource.com/mock/speech.mp3",
                        "audio_b64": "bW9ja19tcDNfYXVkaW9fZGF0YQ==",
                    },
                },
            )
        return httpx.Response(404)

    _core._default_transport = httpx.MockTransport(handler)
    try:
        ctx = build_speech_context()
        res = await synthesize_speech(ctx)
        assert res.succeeded
        assert res.output["audio_format"] == "mp3"
        assert res.output["audio_b64"] == "bW9ja19tcDNfYXVkaW9fZGF0YQ=="
        assert res.output["cdn_url"] == "https://cdn.ng-resource.com/mock/speech.mp3"
        assert res.usage.units == 1
        assert res.usage.input_tokens == len("أهلاً وسهلاً بكم في مصر")
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_speech_error_mapping_rate_limit():
    """HTTP 429 on TTS maps to RATE_LIMITED."""
    _core._default_transport = httpx.MockTransport(lambda req: httpx.Response(429, text="Too Many Requests"))
    try:
        ctx = build_speech_context()
        res = await synthesize_speech(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RATE_LIMITED
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_speech_error_mapping_quota_exhausted():
    """Code 164005 on TTS maps to QUOTA_EXCEEDED."""
    body = json.dumps({"code": 164005, "message": "Insufficient Credits", "data": None})
    _core._default_transport = httpx.MockTransport(lambda req: httpx.Response(200, text=body))
    try:
        ctx = build_speech_context()
        res = await synthesize_speech(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.QUOTA_EXCEEDED
    finally:
        _core._default_transport = None


@pytest.mark.asyncio
async def test_notegpt_speech_error_mapping_auth_expired():
    """Code 164003 on TTS maps to AUTH_EXPIRED."""
    body = json.dumps({"code": 164003, "message": "login expired", "data": None})
    _core._default_transport = httpx.MockTransport(lambda req: httpx.Response(200, text=body))
    try:
        ctx = build_speech_context()
        res = await synthesize_speech(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.AUTH_EXPIRED
    finally:
        _core._default_transport = None


