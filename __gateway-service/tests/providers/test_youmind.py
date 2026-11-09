"""YouMind AI Provider Facade & Parity Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests dynamic discovery of __دومينات مؤقته.
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
from providers.youmind.definition import DEFINITION
from providers.youmind.adapter import HANDLERS, generate_text
from providers.youmind import _core


def build_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="claude-fable-5-1",
        request_id="req-youmind-test",
        tenant_id="tenant-youmind-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "hello"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_youmind_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "YouMind AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert parsed.operations == [GatewayOperation.GENERATE_TEXT]

    model_names = [m.name for m in parsed.models]
    assert "claude-fable-5-1" in model_names
    assert "gpt-6-astra" in model_names
    assert "deepseek-flash" in model_names
    assert "gemini-3.8-flash" in model_names
    assert "kimi-k3" in model_names
    assert "auto" in model_names

    # Check capabilities are in closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("code") is True
    assert not parsed.capabilities.get("image_generation", False)


def test_youmind_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


@pytest.mark.provider_env
def test_youmind_temp_domains_discovery():
    """Verify dynamic discovery of __دومينات مؤقته directory."""
    root = _core.discover_temp_domains_root()
    assert root is not None
    assert root.is_dir()
    assert (root / "providers").is_dir()

    provider = _core.get_temp_email_provider()
    assert provider is not None
    assert hasattr(provider, "create_email")


@pytest.mark.asyncio
async def test_youmind_credential_mode_protection():
    """Passing caller user_key credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="secret-key")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_youmind_payload_validation():
    """Malformed payload triggers BAD_REQUEST."""
    # Empty messages
    ctx_empty = build_context(payload={"messages": []})
    res_empty = await generate_text(ctx_empty)
    assert not res_empty.succeeded
    assert res_empty.error.category is ErrorCategory.BAD_REQUEST

    # Unsupported extra field
    ctx_files = build_context(payload={"messages": [{"role": "user", "content": "hi"}], "files": []})
    res_files = await generate_text(ctx_files)
    assert not res_files.succeeded
    assert res_files.error.category is ErrorCategory.BAD_REQUEST

    # Invalid role
    ctx_role = build_context(payload={"messages": [{"role": "admin", "content": "hi"}]})
    res_role = await generate_text(ctx_role)
    assert not res_role.succeeded
    assert res_role.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_youmind_generate_text_mocked_success():
    """Hermetic success test via mocked SSE streaming transport."""
    sse_body = (
        'data: {"mode":"insert","dataType":"CompletionBlock","data":{"id":"blk1","type":"content"}}\n\n'
        'data: {"mode":"append_string","targetId":"blk1","data":"Hello from YouMind!"}\n\n'
        'data: {"mode":"replace","targetType":"Message","data":"success"}\n\n'
        'data: [DONE]\n\n'
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(transport)

    try:
        ctx = build_context(payload={"messages": [{"role": "user", "content": "hello"}]})
        res = await generate_text(ctx)
        assert res.succeeded is True
        assert res.output["text"] == "Hello from YouMind!"
        assert res.output["finish_reason"] == "stop"
        assert res.usage.units == 1
        assert res.error is None
    finally:
        _core.set_transport_override(None)


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_youmind_upstream_rate_limited():
    """HTTP 429 response mapped to ErrorCategory.RATE_LIMITED."""
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limited")

    transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(transport)

    try:
        ctx = build_context()
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.RATE_LIMITED
        assert res.error.retryable is True
        assert res.error.provider_code == "429"
    finally:
        _core.set_transport_override(None)


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_youmind_upstream_permission_denied():
    """PermissionDenied event inside SSE mapped to MODEL_UNAVAILABLE."""
    sse_body = (
        'data: {"event":"error","data":{"name":"PermissionDenied","message":"Subscription does not allow this model"}}\n\n'
        'data: [DONE]\n\n'
    )

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body.encode("utf-8"))

    transport = httpx.MockTransport(mock_handler)
    _core.set_transport_override(transport)

    try:
        ctx = build_context(model="claude-4-6-opus")
        res = await generate_text(ctx)
        assert not res.succeeded
        assert res.error.category is ErrorCategory.MODEL_UNAVAILABLE
        assert res.error.provider_code == "403"
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_youmind_no_credential_leakage():
    """Ensure error messages never leak tokens or emails."""
    ctx = build_context(payload={"messages": []})
    res = await generate_text(ctx)
    msg = res.error.message.lower()
    assert "token" not in msg
    assert "@" not in msg
    assert "cookie" not in msg
