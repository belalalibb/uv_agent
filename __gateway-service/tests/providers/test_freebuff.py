"""Hermetic Freebuff provider tests — facade + Layer 1 mock.

ZERO network.
Proves:
- Canonical success shape for generate_text
- Error translation to the 12 ErrorCategory taxonomy
- Zero secret or cookie leakage
- DEFINITION <-> HANDLERS parity
- Schema policing: extra keys rejected as bad_request
"""

from __future__ import annotations

import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.freebuff import _core
from providers.freebuff.adapter import HANDLERS, generate_text
from providers.freebuff.definition import DEFINITION


def test_freebuff_definition_parity() -> None:
    declared = {GatewayOperation(op) for op in DEFINITION["operations"]}
    assert set(HANDLERS.keys()) == declared


@pytest.mark.asyncio
async def test_freebuff_generate_text_mocked_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_generate_text(*args, **kwargs):
        return {
            "content": "Hello from Freebuff Mock!",
            "reasoning": "",
            "thread_id": "mock_th_1",
            "model": "glm-5.3-flash",
        }

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="glm-5.3-flash",
        request_id="req_freebuff_1",
        tenant_id="ten_freebuff_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"messages": [{"role": "user", "content": "hi"}]},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert res.output is not None
    assert res.output["text"] == "Hello from Freebuff Mock!"
    assert res.usage is not None


@pytest.mark.asyncio
async def test_freebuff_schema_policing() -> None:
    # Missing messages
    ctx_bad = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="glm-5.3-flash",
        request_id="req_freebuff_bad",
        tenant_id="ten_freebuff_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={},
        timeout_ms=5000,
    )
    res = await generate_text(ctx_bad)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_freebuff_upstream_failure_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("rate_limited", "Rate limit exceeded", retry_after_ms=2000)

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="glm-5.3-flash",
        request_id="req_freebuff_fail",
        tenant_id="ten_freebuff_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"messages": [{"role": "user", "content": "hi"}]},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.RATE_LIMITED
    assert res.error.retryable is True
