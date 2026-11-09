"""IvyCraft AI Provider Facade & Parity Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation for all 3 operations.
- Tests dynamic discovery of __دومينات مؤقته.
- Tests hermetic execution with mocked transport (generate_text, generate_image, synthesize_speech).
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
from providers.ivycraft.definition import DEFINITION
from providers.ivycraft.adapter import HANDLERS, generate_text, generate_image, synthesize_speech
from providers.ivycraft import _core


def build_text_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="gpt-5.6-terra",
        request_id="req-ivycraft-test",
        tenant_id="tenant-ivycraft-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "hello"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def build_image_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_IMAGE,
        model="gpt-image-2.5-sunburst",
        request_id="req-ivycraft-img-test",
        tenant_id="tenant-ivycraft-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"prompt": "A modern futuristic city"} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def build_speech_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.SYNTHESIZE_SPEECH,
        model="text-to-speech",
        request_id="req-ivycraft-audio-test",
        tenant_id="tenant-ivycraft-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"text": "Welcome to IvyCraft AI podcast"} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_ivycraft_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "IvyCraft AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert set(parsed.operations) == {
        GatewayOperation.GENERATE_TEXT,
        GatewayOperation.GENERATE_IMAGE,
        GatewayOperation.SYNTHESIZE_SPEECH,
    }

    model_names = [m.name for m in parsed.models]
    assert "gpt-5.6-terra" in model_names
    assert "gpt-image-2.5-sunburst" in model_names
    assert "text-to-speech" in model_names

    # Check capabilities are within closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("code") is True
    assert parsed.capabilities.get("image_generation") is True
    assert parsed.capabilities.get("audio_output") is True
    assert parsed.capabilities.get("audio_input") is True
    assert parsed.capabilities.get("file_upload") is True


def test_ivycraft_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


def test_ivycraft_temp_domains_discovery():
    """Verify dynamic discovery of __دومينات مؤقته directory."""
    root = _core.discover_temp_domains_root()
    assert root is not None
    assert root.is_dir()
    assert (root / "providers").is_dir()

    provider = _core.get_temp_email_provider()
    assert provider is not None
    assert hasattr(provider, "create_email")


@pytest.mark.asyncio
async def test_ivycraft_credential_mode_protection():
    """Passing caller user_key credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_text_context(credential_mode=CredentialMode.USER_KEY, credential_value="secret-key")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_ivycraft_payload_validation():
    """Malformed payloads trigger BAD_REQUEST for all operations."""
    # 1. Empty messages
    ctx_empty = build_text_context(payload={"messages": []})
    res_empty = await generate_text(ctx_empty)
    assert not res_empty.succeeded
    assert res_empty.error.category is ErrorCategory.BAD_REQUEST

    # 2. Unsupported 'files' key in text payload
    ctx_files = build_text_context(payload={"messages": [{"role": "user", "content": "hi"}], "files": []})
    res_files = await generate_text(ctx_files)
    assert not res_files.succeeded
    assert res_files.error.category is ErrorCategory.BAD_REQUEST

    # 3. Invalid image prompt
    ctx_img_bad = build_image_context(payload={"prompt": ""})
    res_img = await generate_image(ctx_img_bad)
    assert not res_img.succeeded
    assert res_img.error.category is ErrorCategory.BAD_REQUEST

    # 4. Invalid speech text
    ctx_sp_bad = build_speech_context(payload={"text": ""})
    res_sp = await synthesize_speech(ctx_sp_bad)
    assert not res_sp.succeeded
    assert res_sp.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_ivycraft_hermetic_generate_text():
    """Hermetic generate_text with mocked SSE stream transport."""
    mock_body = 'data: {"type": "content", "content": "Hello from IvyCraft GPT-5.6-Terra!"}\ndata: [DONE]\n'
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, text=mock_body, headers={"content-type": "text/event-stream"})
    )
    _core.set_transport_override(transport)

    try:
        ctx = build_text_context()
        res = await generate_text(ctx)
        assert res.succeeded
        assert "Hello from IvyCraft GPT-5.6-Terra" in res.output["text"]
        assert res.output["finish_reason"] == "stop"
        assert res.usage is not None
        assert res.usage.units == 1
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_ivycraft_hermetic_generate_image():
    """Hermetic generate_image with mock transport."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"code": 200, "data": {"images": [{"b64": "mock_b64_image_data", "format": "png"}]}},
        )
    )
    _core.set_transport_override(transport)

    try:
        ctx = build_image_context()
        res = await generate_image(ctx)
        assert res.succeeded
        assert len(res.output["images"]) == 1
        assert res.output["images"][0]["format"] == "png"
        assert res.usage.units == 1
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_ivycraft_hermetic_synthesize_speech():
    """Hermetic synthesize_speech with mock transport."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"code": 200, "data": {"audio_b64": "mock_audio_b64_wav", "audio_format": "wav"}},
        )
    )
    _core.set_transport_override(transport)

    try:
        ctx = build_speech_context()
        res = await synthesize_speech(ctx)
        assert res.succeeded
        assert res.output["audio_format"] == "wav"
        assert res.usage.units == 1
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_ivycraft_error_mapping():
    """Test mapping of upstream HTTP status codes to canonical categories."""
    # 401 -> AUTH_EXPIRED
    transport_401 = httpx.MockTransport(lambda req: httpx.Response(401, text="Unauthorized"))
    _core.set_transport_override(transport_401)
    try:
        res = await generate_text(build_text_context())
        assert not res.succeeded
        assert res.error.category is ErrorCategory.AUTH_EXPIRED
    finally:
        _core.set_transport_override(None)

    # 429 -> RATE_LIMITED with retry_after_ms
    transport_429 = httpx.MockTransport(lambda req: httpx.Response(429, text="Too Many Requests"))
    _core.set_transport_override(transport_429)
    try:
        res = await generate_text(build_text_context())
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RATE_LIMITED
        assert res.error.retry_after_ms is not None
    finally:
        _core.set_transport_override(None)

    # 501 / Insufficient credits -> QUOTA_EXCEEDED
    transport_quota = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"code": 501, "msg": "1001:Insufficient credits for this operation."},
            headers={"content-type": "application/json"},
        )
    )
    _core.set_transport_override(transport_quota)
    try:
        res = await generate_text(build_text_context())
        assert not res.succeeded
        assert res.error.category is ErrorCategory.QUOTA_EXCEEDED
    finally:
        _core.set_transport_override(None)

    # 500 -> RETRYABLE_SERVER_ERROR
    transport_500 = httpx.MockTransport(lambda req: httpx.Response(500, text="Internal Server Error"))
    _core.set_transport_override(transport_500)
    try:
        res = await generate_text(build_text_context())
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RETRYABLE_SERVER_ERROR
    finally:
        _core.set_transport_override(None)
