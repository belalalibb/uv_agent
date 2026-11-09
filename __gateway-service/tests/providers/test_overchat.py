"""Overchat AI Provider Facade & Parity Tests.

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
from providers.overchat.definition import DEFINITION
from providers.overchat.adapter import HANDLERS, generate_text, analyze_vision, transcribe_audio
from providers.overchat import _core


def build_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="gpt-6-luna",
        request_id="req-overchat-test",
        tenant_id="tenant-overchat-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "1+1=?"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_overchat_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities & operations."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "Overchat AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert parsed.operations == [
        GatewayOperation.GENERATE_TEXT,
        GatewayOperation.ANALYZE_VISION,
        GatewayOperation.TRANSCRIBE_AUDIO,
    ]
    assert set(HANDLERS.keys()) == set(parsed.operations)

    model_names = [m.name for m in parsed.models]
    expected_models = {
        "gpt-6-luna",
        "gpt-5.6-luna",
        "gemini-3.8-flash",
        "claude-4.5-haiku",
        "deepseek-v3.2",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1-nano",
    }
    assert set(model_names) == expected_models

    # Check capabilities in closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("code") is True
    assert parsed.capabilities.get("vision_input") is True
    assert parsed.capabilities.get("audio_input") is True
    assert parsed.capabilities.get("file_upload") is True
    assert not parsed.capabilities.get("image_generation", False)


@pytest.mark.asyncio
async def test_overchat_unsupported_model_rejected():
    """Requesting an undeclared model fails with MODEL_UNAVAILABLE."""
    ctx = build_context(model="unsupported-model-x")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.MODEL_UNAVAILABLE


@pytest.mark.asyncio
async def test_overchat_invalid_credential_mode():
    """Passing user credential or non-platform mode fails with INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="secret")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_overchat_payload_validation_empty_messages():
    """Empty or missing messages must fail with BAD_REQUEST."""
    ctx = build_context(payload={"messages": []})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_overchat_payload_validation_forbidden_fields():
    """Messages with extra keys fail with BAD_REQUEST."""
    ctx = build_context(payload={"messages": [{"role": "user", "content": "hi", "extra": 123}]})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_overchat_hermetic_chat_success():
    """Hermetic execution via MockTransport returns FacadeResult with valid Usage."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/v1/auth/me" in url_str:
            return httpx.Response(200, json={"id": "mock-user-123", "role": None})
        if "/v1/chat/" in url_str:
            return httpx.Response(201, json={"status": "ok"})
        if "/v2/chat/responses" in url_str:
            sse_content = (
                b"data: {\"event\":\"response.output_text.delta\",\"data\":{\"delta\":\"2\"}}\n\n"
                b"data: [DONE]\n\n"
            )
            return httpx.Response(201, content=sse_content)
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_default_transport(mock_transport)

    try:
        ctx = build_context(model="gpt-6-luna", payload={"messages": [{"role": "user", "content": "What is 1+1?"}]})
        res = await generate_text(ctx)
        assert res.succeeded
        assert res.output["text"] == "2"
        assert res.output["finish_reason"] == "stop"
        assert res.usage.input_tokens > 0
        assert res.usage.output_tokens > 0
    finally:
        _core.set_default_transport(None)


@pytest.mark.asyncio
async def test_overchat_hermetic_fallback_on_model_failure():
    """Hermetic execution falls back to gpt-5.6-luna if gpt-6-luna returns error."""
    tried_models = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/v1/auth/me" in url_str:
            return httpx.Response(200, json={"id": "mock-user-123"})
        if "/v1/chat/" in url_str:
            return httpx.Response(201, json={"status": "ok"})
        if "/v2/chat/responses" in url_str:
            req_body = json.loads(request.content)
            m = req_body.get("model")
            tried_models.append(m)
            if m == "gpt-6-luna":
                return httpx.Response(500, json={"error": "model temporarily busy"})
            if m == "gpt-5.6-luna":
                sse_content = b"data: {\"event\":\"response.output_text.delta\",\"data\":{\"delta\":\"fallback success\"}}\n\ndata: [DONE]\n\n"
                return httpx.Response(201, content=sse_content)
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_default_transport(mock_transport)

    try:
        ctx = build_context(model="gpt-6-luna", payload={"messages": [{"role": "user", "content": "test fallback"}]})
        res = await generate_text(ctx)
        assert res.succeeded
        assert res.output["text"] == "fallback success"
        assert "gpt-6-luna" in tried_models
        assert "gpt-5.6-luna" in tried_models
    finally:
        _core.set_default_transport(None)


@pytest.mark.asyncio
async def test_overchat_error_mapping_rate_limit():
    """HTTP 429 maps to ErrorCategory.RATE_LIMITED."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "/v1/auth/me" in str(request.url):
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_default_transport(mock_transport)

    try:
        ctx = build_context(model="gpt-6-luna")
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RATE_LIMITED
    finally:
        _core.set_default_transport(None)


@pytest.mark.asyncio
async def test_overchat_hermetic_analyze_vision_success():
    """Hermetic execution of analyze_vision uploads image to S3 and streams response."""
    import base64

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/v1/auth/me" in url_str:
            return httpx.Response(200, json={"id": "mock-user-123"})
        if "/v1/chat/upload" in url_str:
            return httpx.Response(200, json={"link": "https://s3.amazonaws.com/test-bucket/sample.png"})
        if "/v1/chat/" in url_str:
            return httpx.Response(201, json={"status": "ok"})
        if "/v2/chat/responses" in url_str:
            sse_content = (
                b"data: {\"event\":\"response.output_text.delta\",\"data\":{\"delta\":\"The image contains text: HELLO\"}}\n\n"
                b"data: [DONE]\n\n"
            )
            return httpx.Response(201, content=sse_content)
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_default_transport(mock_transport)

    try:
        sample_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfakeimage").decode("ascii")
        ctx = build_context(
            operation=GatewayOperation.ANALYZE_VISION,
            model="gpt-6-luna",
            payload={
                "image_b64": sample_b64,
                "image_format": "png",
                "instruction": "Read text in this image",
            },
        )
        res = await analyze_vision(ctx)
        assert res.succeeded
        assert "HELLO" in res.output["text"]
        assert res.usage.units == 1
    finally:
        _core.set_default_transport(None)


@pytest.mark.asyncio
async def test_overchat_analyze_vision_bad_payload():
    """Missing or invalid image_b64 fails with BAD_REQUEST."""
    ctx = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        payload={"instruction": "Read this"},
    )
    res = await analyze_vision(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_overchat_hermetic_transcribe_audio_success():
    """Hermetic execution of transcribe_audio uploads audio to /v1/transcript."""
    import base64

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "/v1/auth/me" in url_str:
            return httpx.Response(200, json={"id": "mock-user-123"})
        if "/v1/transcript" in url_str:
            return httpx.Response(200, json={"text": "مرحبا بك في اختبار الصوت", "language": "ar"})
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_default_transport(mock_transport)

    try:
        sample_audio = base64.b64encode(b"OggSfakeaudiobytes").decode("ascii")
        ctx = build_context(
            operation=GatewayOperation.TRANSCRIBE_AUDIO,
            payload={
                "audio_b64": sample_audio,
                "audio_format": "ogg",
            },
        )
        res = await transcribe_audio(ctx)
        assert res.succeeded
        assert res.output["text"] == "مرحبا بك في اختبار الصوت"
        assert res.output["language"] == "ar"
        assert res.usage.units == 1
    finally:
        _core.set_default_transport(None)


@pytest.mark.asyncio
async def test_overchat_transcribe_audio_bad_payload():
    """Missing audio_b64 fails with BAD_REQUEST."""
    ctx = build_context(
        operation=GatewayOperation.TRANSCRIBE_AUDIO,
        payload={"audio_format": "mp3"},
    )
    res = await transcribe_audio(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST

