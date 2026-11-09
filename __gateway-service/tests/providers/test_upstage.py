"""Upstage AI Provider Facade & Parity Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests dynamic discovery of __دومينات مؤقته with random provider loading.
- Tests hermetic execution with mocked Next.js / SSE transport.
- Tests error mapping to canonical 12 categories without credential leakage.
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
from providers.upstage.definition import DEFINITION
from providers.upstage.adapter import HANDLERS, analyze_vision, generate_text
from providers.upstage import _core


def build_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="solar-pro4",
        request_id="req-upstage-test",
        tenant_id="tenant-upstage-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "hello"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_upstage_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "Upstage AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert set(parsed.operations) == {GatewayOperation.GENERATE_TEXT, GatewayOperation.ANALYZE_VISION}

    model_names = [m.name for m in parsed.models]
    assert "auto" in model_names
    assert "solar-pro4" in model_names
    assert "solar-docvision" in model_names
    assert "gpt-5.4-openai" in model_names

    # Check capabilities are within closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("code") is True
    assert parsed.capabilities.get("vision_input") is True
    assert parsed.capabilities.get("browser") is True
    assert parsed.capabilities.get("tool_use") is True
    assert parsed.capabilities.get("file_upload") is True
    assert parsed.capabilities.get("agent_module") is True
    assert not parsed.capabilities.get("image_generation", False)
    assert not parsed.capabilities.get("audio_input", False)
    assert not parsed.capabilities.get("audio_output", False)


def test_upstage_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


@pytest.mark.provider_env
def test_upstage_temp_domains_discovery():
    """Verify dynamic discovery and random loader of __دومينات مؤقته."""
    root = _core.discover_temp_domains_root()
    assert root is not None
    assert root.is_dir()
    assert (root / "providers").is_dir()

    provider, prov_key = _core.get_random_temp_email_provider()
    assert provider is not None
    assert hasattr(provider, "create_email")
    assert prov_key in _core.WORKING_MAIL_PROVIDERS


@pytest.mark.asyncio
async def test_upstage_credential_mode_protection():
    """Passing caller user_key credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="secret-key")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_upstage_payload_validation():
    """Malformed payload triggers BAD_REQUEST."""
    # Empty messages
    ctx_empty = build_context(payload={"messages": []})
    res_empty = await generate_text(ctx_empty)
    assert not res_empty.succeeded
    assert res_empty.error.category is ErrorCategory.BAD_REQUEST

    # Unsupported field 'files'
    ctx_files = build_context(payload={"messages": [{"role": "user", "content": "hi"}], "files": ["doc.txt"]})
    res_files = await generate_text(ctx_files)
    assert not res_files.succeeded
    assert res_files.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_upstage_generate_text_mocked_success(monkeypatch):
    """Hermetic execution testing SSE streaming with mock transport."""
    # 1. Mock session to avoid network registration
    monkeypatch.setattr(_core, "get_active_session", lambda: "mock-session-cookie-123")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # Create chat
        if "/api/chats" in url:
            return httpx.Response(
                201,
                json={"chat": {"id": "mock-chat-999"}},
            )
        # Stream chat
        if "/api/chat/pi" in url:
            # Send Next.js Vercel stream lines
            content = (
                b'0:"\xd8\xa3\xd9\x87\xd9\x84\xd8\xa7\xd9\x8b "\n'
                b'0:"\xd8\xa8\xd9\x83\x20\xd9\x85\xd9\x86\x20Upstage"\n'
            )
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=content,
            )
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(mock_transport)

    try:
        ctx = build_context(model="solar-pro4")
        res = await generate_text(ctx)
        assert res.succeeded
        assert "أهلاً بك من Upstage" in res.output["text"]
        assert res.usage is not None
        assert res.usage.output_tokens > 0
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_upstage_auth_expired_mapping(monkeypatch):
    """Auth rejection is cleanly mapped to AUTH_EXPIRED without leakage."""
    monkeypatch.setattr(_core, "get_active_session", lambda: "invalid-cookie")
    monkeypatch.setattr(_core, "refresh", lambda auto_rotate=True: (_ for _ in ()).throw(_core.UpstreamFailure("auth_expired", "expired")))

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized"})

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(mock_transport)

    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.AUTH_EXPIRED
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_upstage_analyze_vision_non_vision_model():
    """Non-vision model (solar-pro4) rejected with UNSUPPORTED_CAPABILITY (Anti-Explosion)."""
    ctx = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        model="solar-pro4",
        payload={
            "image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=",
            "instruction": "describe this image",
        },
    )
    res = await analyze_vision(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.UNSUPPORTED_CAPABILITY
    assert "does not support vision/image inputs" in res.error.message


@pytest.mark.asyncio
async def test_upstage_analyze_vision_payload_validation():
    """Missing or invalid image/instruction triggers BAD_REQUEST."""
    # Missing image_b64
    ctx1 = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        model="solar-docvision",
        payload={"instruction": "describe"},
    )
    res1 = await analyze_vision(ctx1)
    assert not res1.succeeded
    assert res1.error.category is ErrorCategory.BAD_REQUEST

    # Missing instruction
    ctx2 = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        model="solar-docvision",
        payload={"image_b64": "some_b64"},
    )
    res2 = await analyze_vision(ctx2)
    assert not res2.succeeded
    assert res2.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_upstage_analyze_vision_mocked_success(monkeypatch):
    """Hermetic vision analysis test with mock file upload and mock chat stream."""
    monkeypatch.setattr(_core, "get_active_session", lambda: "mock-session-cookie-123")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # Mock file upload
        if "/api/studio-chat/files" in url:
            return httpx.Response(
                200,
                json={"id": "file_mock_test_123", "object": "file", "filename": "image.png"},
            )
        # Mock chat creation
        if "/api/chats" in url:
            return httpx.Response(
                201,
                json={"chat": {"id": "mock-chat-vision-777"}},
            )
        # Mock stream
        if "/api/chat/pi" in url:
            content = (
                b'data: {"type":"chat_sources_changed","fileIds":["file_mock_test_123"]}\n'
                b'data: {"type":"delta","content":"\xd8\xa7\xd9\x84\xd8\xb5\xd9\x88\xd8\xb1\xd8\xa9\x20\xd9\x81\xd9\x8a\xd9\x87\xd8\xa7\x20\xd9\x82\xd8\xb7\xd8\xa9\x20\xd8\xa8\xd9\x8a\xd8\xb6\xd8\xa7\xd8\xa1"}\n'
                b'data: {"type":"done"}\n'
            )
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                content=content,
            )
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(mock_transport)

    try:
        ctx = build_context(
            operation=GatewayOperation.ANALYZE_VISION,
            model="solar-docvision",
            payload={
                "image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=",
                "instruction": "ماذا ترى في الصورة؟",
            },
        )
        res = await analyze_vision(ctx)
        assert res.succeeded
        assert "الصورة فيها قطة بيضاء" in res.output["text"]
        assert res.usage is not None
        assert res.usage.output_tokens > 0
    finally:
        _core.set_transport_override(None)
