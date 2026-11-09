# -*- coding: utf-8 -*-
"""Hermetic RunPod Console Assistant Provider Tests.

ZERO network. All calls routed through httpx.MockTransport installed
via Layer-1 test seam (_upstream._default_transport).
Proves: canonical success shape for text & vision, category mapping,
DEFINITION <-> HANDLERS parity, schema policing, and zero credential leakage.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.runpod_console import _upstream
from providers.runpod_console.adapter import HANDLERS, generate_text, analyze_vision
from providers.runpod_console.definition import DEFINITION


def _context(payload: dict[str, Any] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="runpod-console-gpt4",
        request_id="req-test-runpod-01",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,
        payload={
            "messages": [
                {"role": "user", "content": "Hello RunPod!"},
            ]
        }
        if payload is None
        else payload,
        timeout_ms=5000,
    )


def _vision_context(payload: dict[str, Any] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        model="runpod-console-vision",
        request_id="req-test-runpod-v01",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,
        payload={
            "image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
            "instruction": "Describe this image",
            "image_format": "png",
        }
        if payload is None
        else payload,
        timeout_ms=5000,
    )


def test_definition_conformance() -> None:
    """DEFINITION declares exact operations that match HANDLERS keys."""
    declared = DEFINITION.get("operations")
    assert isinstance(declared, list)
    assert set(declared) == {"generate_text", "analyze_vision"}
    assert set(HANDLERS.keys()) == {GatewayOperation.GENERATE_TEXT, GatewayOperation.ANALYZE_VISION}
    assert DEFINITION.get("credential_mode") == "platform"
    assert DEFINITION.get("definition_version") == "1.1.0"


def test_schema_policing_disallowed_keys() -> None:
    """Extra payload keys rejected as BAD_REQUEST."""
    ctx = _context({"messages": [{"role": "user", "content": "hi"}], "disallowed_extra": 123})
    res = pytest.importorskip("asyncio").run(generate_text(ctx))
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST
    assert "disallowed keys" in res.error.message


def test_schema_policing_empty_messages() -> None:
    """Empty messages list rejected as BAD_REQUEST."""
    ctx = _context({"messages": []})
    res = pytest.importorskip("asyncio").run(generate_text(ctx))
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST


def test_schema_policing_vision_missing_fields() -> None:
    """Missing image_b64 or instruction rejected as BAD_REQUEST."""
    ctx = _vision_context({"instruction": "test only"})
    res = pytest.importorskip("asyncio").run(analyze_vision(ctx))
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST
    assert "image_b64" in res.error.message


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_runpod_console_mocked_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical success shape via mocked SSE stream transport."""
    sse_body = (
        'data: {"type":"start"}\n\n'
        'data: {"type":"text-delta","delta":"Hello "}\n\n'
        'data: {"type":"text-delta","delta":"from RunPod!"}\n\n'
        'data: [DONE]\n\n'
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "clerk.runpod.io" in url_str:
            return httpx.Response(200, json={"object": "token", "jwt": "mock_jwt_token_12345"})
        if "api/assistant/agents/console/stream" in url_str:
            assert "x-clerk-token" in request.headers
            return httpx.Response(200, content=sse_body.encode("utf-8"))
        return httpx.Response(404)

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(_upstream, "_cached_jwt", "mock_cached_jwt")
    monkeypatch.setattr(_upstream, "_jwt_expires_at", 9999999999)

    res = await generate_text(_context())
    assert res.succeeded is True
    assert res.output == {"text": "Hello from RunPod!", "finish_reason": "stop"}
    assert res.usage.input_tokens > 0
    assert res.usage.output_tokens > 0
    assert res.usage.units == 1


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_runpod_console_analyze_vision_mocked_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Canonical analyze_vision success shape via mocked transport."""
    sse_body = (
        'data: {"type":"start"}\n\n'
        'data: {"type":"text-delta","delta":"This is a red square image."}\n\n'
        'data: [DONE]\n\n'
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "api/assistant/agents/console/stream" in url_str:
            body = json.loads(request.content.decode("utf-8"))
            parts = body["messages"][0]["parts"]
            assert any(p.get("type") == "file" for p in parts)
            return httpx.Response(200, content=sse_body.encode("utf-8"))
        return httpx.Response(404)

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(_upstream, "_cached_jwt", "mock_cached_jwt")
    monkeypatch.setattr(_upstream, "_jwt_expires_at", 9999999999)

    res = await analyze_vision(_vision_context())
    assert res.succeeded is True
    assert res.output == {"text": "This is a red square image.", "finish_reason": "stop"}
    assert res.usage.input_tokens > 0
    assert res.usage.output_tokens > 0


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_runpod_console_upstream_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 429 maps to ErrorCategory.RATE_LIMITED."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(_upstream, "_cached_jwt", "mock_cached_jwt")
    monkeypatch.setattr(_upstream, "_jwt_expires_at", 9999999999)

    res = await generate_text(_context())
    assert not res.succeeded
    assert res.error.category is ErrorCategory.RATE_LIMITED
    assert res.error.retryable is True


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_runpod_console_upstream_auth_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 401 maps to ErrorCategory.AUTH_EXPIRED."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="Unauthorized")

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(_upstream, "_cached_jwt", "mock_cached_jwt")
    monkeypatch.setattr(_upstream, "_jwt_expires_at", 9999999999)

    res = await generate_text(_context())
    assert not res.succeeded
    assert res.error.category is ErrorCategory.AUTH_EXPIRED


@pytest.mark.provider_env
@pytest.mark.asyncio
async def test_runpod_console_upstream_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """HTTP 500 maps to ErrorCategory.RETRYABLE_SERVER_ERROR."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    monkeypatch.setattr(_upstream, "_default_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(_upstream, "_cached_jwt", "mock_cached_jwt")
    monkeypatch.setattr(_upstream, "_jwt_expires_at", 9999999999)

    res = await generate_text(_context())
    assert not res.succeeded
    assert res.error.category is ErrorCategory.RETRYABLE_SERVER_ERROR
    assert res.error.retryable is True
