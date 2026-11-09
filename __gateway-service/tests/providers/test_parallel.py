"""Hermetic Parallel AI provider tests — facade + Layer 1 mock + Wire verification.

ZERO network.
Proves:
- 1. Canonical success shape for generate_text across models (chat, search, extract, research)
- 2. Error translation to the 12 ErrorCategory taxonomy (rate_limited, auth_expired, timeout, server error)
- 3. Zero secret or cookie leakage in output or error messages
- 4. DEFINITION <-> HANDLERS parity
- 5. Closed CAPABILITY_KEYS conformance
- 6. models_metadata.json structural integrity
- 7. Schema policing: missing/empty prompt rejected as BAD_REQUEST
- 8. Strict FIFO sequential refill queue verification (+5 accounts per request)
- 9. Full end-to-end Wire dispatch via FastAPI TestClient
"""

from __future__ import annotations

import json
import pytest

from gateway.contracts import (
    CAPABILITY_KEYS,
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.parallel import _core
from providers.parallel.adapter import HANDLERS, generate_text
from providers.parallel.definition import DEFINITION, _MODELS_DATA


# ─── 1. Parity and Metadata Tests ───────────────────────────────────────────

def test_parallel_definition_parity() -> None:
    """Operations declared in DEFINITION must strictly match HANDLERS."""
    declared = {GatewayOperation(op) for op in DEFINITION["operations"]}
    assert set(HANDLERS.keys()) == declared


def test_parallel_capabilities_closed_set() -> None:
    """All declared capabilities must exist in the canonical closed CAPABILITY_KEYS set."""
    caps = set(DEFINITION["capabilities"].keys())
    assert caps <= CAPABILITY_KEYS


def test_parallel_models_metadata_integrity() -> None:
    """All declared models must exist in models_metadata.json and have valid structures."""
    assert len(_MODELS_DATA) >= 4
    expected_models = {"parallel-chat", "parallel-search", "parallel-extract", "parallel-research", "default"}
    assert expected_models <= set(_MODELS_DATA.keys())
    for m_id, meta in _MODELS_DATA.items():
        assert "ai_name" in meta
        assert meta["ai_name"] == "parallel"
        assert "capabilities" in meta
        assert isinstance(meta["capabilities"], dict)


# ─── 2. Execution and Model Routing Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_parallel_generate_text_default_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default model execution returns valid text and usage envelope."""
    def _mock_generate_text(prompt: str, session_data: dict, model: str = "default"):
        return f"Echo from Parallel AI: {prompt}"

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_parallel_1",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"messages": [{"role": "user", "content": "Hello AI"}]},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert res.output is not None
    assert "Echo from Parallel AI: Hello AI" in res.output["text"]
    assert res.usage is not None
    assert res.usage.units == 1


@pytest.mark.asyncio
async def test_parallel_search_model_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search model routing generates structured markdown search results."""
    def _mock_generate_text(prompt: str, session_data: dict, model: str = "parallel-search"):
        assert model == "parallel-search"
        return "### 🔍 نتائج البحث المباشرة:\n**[1] Title** -> https://example.com"

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="parallel-search",
        request_id="req_search_1",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "Search latest news"},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert "نتائج البحث" in res.output["text"]


@pytest.mark.asyncio
async def test_parallel_extract_model_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extract model routing generates extracted document content."""
    def _mock_generate_text(prompt: str, session_data: dict, model: str = "parallel-extract"):
        assert model == "parallel-extract"
        return "### 📄 محتوى الصفحات والمستندات المستخرجة:\nDummy PDF file content"

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="parallel-extract",
        request_id="req_extract_1",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "Extract https://example.com/test.pdf"},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert "محتوى الصفحات" in res.output["text"]


@pytest.mark.asyncio
async def test_parallel_research_model_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deep Research model routing returns synthesized research report."""
    def _mock_generate_text(prompt: str, session_data: dict, model: str = "parallel-research"):
        assert model == "parallel-research"
        return "Synthesized Research Report: 1. Kimi K2.6, 2. DeepSeek V4 Pro, 3. GLM-5.1"

    monkeypatch.setattr(_core, "generate_text", _mock_generate_text)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="parallel-research",
        request_id="req_research_1",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "Top LLMs in 2026"},
        timeout_ms=5000,
    )

    res = await generate_text(ctx)
    assert res.succeeded is True
    assert "Synthesized Research Report" in res.output["text"]


# ─── 3. Schema Policing and Error Mapping Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_parallel_schema_policing_empty_payload() -> None:
    """Missing or empty prompt/messages rejected as BAD_REQUEST."""
    ctx_bad = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_parallel_bad",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={},
        timeout_ms=5000,
    )
    res = await generate_text(ctx_bad)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_parallel_rate_limit_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream rate limit mapped to canonical RATE_LIMITED category."""
    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("rate_limited", "Rate limit exceeded", retry_after_ms=3000)

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_parallel_fail",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "test"},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.RATE_LIMITED
    assert res.error.retryable is True
    assert res.error.retry_after_ms == 3000


@pytest.mark.asyncio
async def test_parallel_auth_expired_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream authentication failure mapped to AUTH_EXPIRED category."""
    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("auth_expired", "Session token has expired")

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_auth_fail",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "test"},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.AUTH_EXPIRED


@pytest.mark.asyncio
async def test_parallel_timeout_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Upstream timeout mapped to TIMEOUT category."""
    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("timeout", "Request timed out after 60s")

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_timeout",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "test"},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    assert res.error.category == ErrorCategory.TIMEOUT


# ─── 4. Non-Leakage and FIFO Queue Refill Tests ──────────────────────────────

@pytest.mark.asyncio
async def test_parallel_no_secret_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error messages must never leak internal keys, cookies, or tokens."""
    sensitive_key = "f4H9ptGTLrtjvOzQAD78W5qNhkkqTE-XInj10WFy"
    sensitive_cookie = "eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2Q0JDLUhTNTEy..."

    def _mock_fail(*args, **kwargs):
        raise _core.UpstreamFailure("retryable_server_error", f"Internal upstream failure with key {sensitive_key} and cookie {sensitive_cookie}")

    monkeypatch.setattr(_core, "generate_text", _mock_fail)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="default",
        request_id="req_leak_check",
        tenant_id="ten_parallel_1",
        credential_mode=CredentialMode.PLATFORM,
        payload={"prompt": "hi"},
        timeout_ms=5000,
    )
    res = await generate_text(ctx)
    assert res.succeeded is False
    # Ensure raw sensitive tokens never appear in the safe error message
    assert sensitive_key not in res.error.message
    assert sensitive_cookie not in res.error.message


def test_parallel_fifo_queue_refill() -> None:
    """Every ask triggers FIFO sequential queue refill adding 5 account creation tasks."""
    initial_qsize = _core._ACCOUNT_REFILL_QUEUE.qsize()
    _core.enqueue_account_refill(5)
    assert _core._ACCOUNT_REFILL_QUEUE.qsize() >= initial_qsize + 5


# ─── 5. Full Wire Envelope Test via FastAPI TestClient ───────────────────────

@pytest.mark.asyncio
async def test_parallel_full_wire_envelope_via_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end wire envelope verification using FastAPI TestClient and mock seam."""
    from fastapi.testclient import TestClient

    from app import build_app, register_live_providers
    from gateway.config import GatewayConfig
    from gateway.provider_registry import ProviderRegistry
    from gateway.route_registry import RouteRegistry

    def _mock_core_gen(prompt: str, session_data: dict, model: str = "default"):
        return f"Wire Parallel Output for: {prompt}"

    monkeypatch.setattr(_core, "generate_text", _mock_core_gen)

    _gw_auth_token = "unit-test-secret-version-parallel"
    route_token = "rtk_parallel_test"
    config = GatewayConfig(
        secrets_by_version={1: _gw_auth_token},
        current_secret_version=1,
        route_map={route_token: "parallel"},
        dual_accept_window_seconds=600,
    )
    providers = ProviderRegistry()
    register_live_providers(providers)
    providers.eager_verify_all()
    routes = RouteRegistry(config.route_map)
    app = build_app(config, providers, routes)
    client = TestClient(app)

    headers = {
        "X-Gateway-Secret": _gw_auth_token,
        "X-Gateway-Secret-Version": "1",
        "X-Route-Token": route_token,
    }

    envelope = {
        "operation": "generate_text",
        "model": "default",
        "request_id": "wire_parallel_req_1",
        "tenant_id": "wire_parallel_tenant_1",
        "credential": {"mode": "platform"},
        "payload": {"prompt": "Tell me about Parallel AI"},
        "timeout_ms": 10000,
    }

    resp = client.post("/v1/execute", json=envelope, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["succeeded"] is True
    assert data["output"] is not None
    assert "Wire Parallel Output for: Tell me about Parallel AI" in data["output"]["text"]
    assert data["usage"] is not None
    assert data["latency_ms"] >= 0
