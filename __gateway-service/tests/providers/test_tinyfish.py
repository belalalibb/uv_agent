"""TinyFish AI Provider Facade & Parity Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests hermetic execution with mocked transport.
- Tests error mapping to canonical 12 categories without leakage.
- Tests dynamic discovery of __دومينات مؤقته.
"""

from __future__ import annotations

import base64
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
from providers.tinyfish.definition import DEFINITION
from providers.tinyfish.adapter import HANDLERS, generate_text, analyze_vision
from providers.tinyfish import _core


def build_context(payload=None, **overrides) -> ProviderContext:
    data = dict(
        operation=GatewayOperation.GENERATE_TEXT,
        model="mako",
        request_id="req-tinyfish-test",
        tenant_id="tenant-tinyfish-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "Hello"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_tinyfish_definition_contract():
    """DEFINITION parses as valid ProviderDefinition matching closed capabilities."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "TinyFish AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert set(parsed.operations) == {GatewayOperation.GENERATE_TEXT, GatewayOperation.ANALYZE_VISION}

    model_names = [m.name for m in parsed.models]
    assert "mako" in model_names
    assert "eva" in model_names
    assert "browser-agent" in model_names
    assert "stealth-agent" in model_names
    assert "tetra-engine" in model_names
    assert "web-fetch" in model_names
    assert "web-search" in model_names
    assert "web-monitor" in model_names
    assert len(model_names) == 8

    # Check capabilities in closed set
    assert parsed.capabilities.get("chat") is True
    assert parsed.capabilities.get("reasoning") is True
    assert parsed.capabilities.get("browser") is True
    assert parsed.capabilities.get("vision_input") is True
    assert parsed.capabilities.get("tool_use") is True
    assert not parsed.capabilities.get("image_generation", False)


def test_tinyfish_adapter_handlers_parity():
    """Handlers declared match operations exactly."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(HANDLERS.keys()) == set(parsed.operations)


@pytest.mark.asyncio
async def test_tinyfish_invalid_credential_mode():
    """Rejects caller-supplied key when mode is PLATFORM."""
    ctx = build_context(credential_value="stray_key")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category == ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_tinyfish_input_validation():
    """Rejects invalid message schemas as BAD_REQUEST."""
    # Empty messages
    ctx = build_context(payload={"messages": []})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category == ErrorCategory.BAD_REQUEST

    # Forbidden role
    ctx = build_context(payload={"messages": [{"role": "admin", "content": "hi"}]})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category == ErrorCategory.BAD_REQUEST

    # Extra keys in message
    ctx = build_context(payload={"messages": [{"role": "user", "content": "hi", "extra": 123}]})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category == ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_tinyfish_hermetic_text_generation():
    """Hermetic execution of generate_text with MockTransport."""
    mock_response = {
        "run_id": "run-test-123",
        "status": "COMPLETED",
        "started_at": "2026-09-26T00:00:00Z",
        "finished_at": "2026-09-26T00:00:02Z",
        "num_of_steps": 1,
        "result": {"result": "The answer is 42"},
        "error": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(handler)
    _core.set_transport_override(transport)

    try:
        ctx = build_context(payload={"messages": [{"role": "user", "content": "What is the meaning of life?"}]})
        res = await generate_text(ctx)
        assert res.succeeded
        assert res.output["text"] == "The answer is 42"
        assert res.output["finish_reason"] == "stop"
        assert res.usage.units == 1
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_tinyfish_hermetic_vision_analysis():
    """Hermetic execution of analyze_vision with MockTransport."""
    mock_response = {
        "run_id": "run-vision-123",
        "status": "COMPLETED",
        "result": {"result": "A high-resolution image of a green leaf."},
        "error": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(handler)
    _core.set_transport_override(transport)

    try:
        raw_bytes = b"fake-png-bytes"
        b64_str = base64.b64encode(raw_bytes).decode("ascii")

        ctx = ProviderContext(
            operation=GatewayOperation.ANALYZE_VISION,
            model="mako",
            request_id="req-vision-test",
            tenant_id="tenant-vision-test",
            credential_mode=CredentialMode.PLATFORM,
            timeout_ms=15000,
            payload={
                "image_b64": b64_str,
                "image_format": "png",
                "instruction": "Describe this image",
            },
        )
        res = await analyze_vision(ctx)
        assert res.succeeded
        assert "green leaf" in res.output["text"]
    finally:
        _core.set_transport_override(None)


@pytest.mark.asyncio
async def test_tinyfish_error_mapping():
    """Maps upstream error status codes safely without credential leakage."""
    # 401 -> AUTH_EXPIRED
    _core.save_accounts_pool([{"api_key": "sk-tinyfish-testkey123456", "status": "active"}])

    def handler_401(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "Unauthorized key"})

    _core.set_transport_override(httpx.MockTransport(handler_401))
    try:
        res = await generate_text(build_context())
        assert not res.succeeded
        assert res.error.category == ErrorCategory.AUTH_EXPIRED
    finally:
        _core.set_transport_override(None)

    # 429 -> RATE_LIMITED
    _core.save_accounts_pool([{"api_key": "sk-tinyfish-testkey123456", "status": "active"}])

    def handler_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Too many requests"})

    _core.set_transport_override(httpx.MockTransport(handler_429))
    try:
        res = await generate_text(build_context())
        assert not res.succeeded
        assert res.error.category == ErrorCategory.RATE_LIMITED
    finally:
        _core.set_transport_override(None)

    # 500 -> RETRYABLE_SERVER_ERROR
    _core.save_accounts_pool([{"api_key": "sk-tinyfish-testkey123456", "status": "active"}])

    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Error")

    _core.set_transport_override(httpx.MockTransport(handler_500))
    try:
        res = await generate_text(build_context())
        assert not res.succeeded
        assert res.error.category == ErrorCategory.RETRYABLE_SERVER_ERROR
    finally:
        _core.set_transport_override(None)


def test_tinyfish_dynamic_discovery_temp_domains():
    """Verify dynamic discovery of __دومينات مؤقته directory without namespace clash."""
    root = _core.discover_temp_domains_root()
    assert root is not None
    assert root.name == "__دومينات مؤقته"
    assert (root / "providers").exists()
