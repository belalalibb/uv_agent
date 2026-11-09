"""Hermetic Voyage AI provider tests — facade + Layer 1 with MockTransport only.

ZERO network. The upstream is an httpx.MockTransport installed through
the Layer-1 test seam; credentials come from a test sentinel.

Proves:
- Canonical success shape for create_embeddings & rerank_documents
- Category mapping to the 12 ErrorCategory values
- No-leak: keys/secrets never appear in output or error message
- DEFINITION <-> HANDLERS parity
- Schema policing: extra keys rejected as bad_request
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from gateway.contracts import (
    CAPABILITY_KEYS,
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.voyage import _core
from providers.voyage.adapter import HANDLERS, create_embeddings, rerank_documents
from providers.voyage.definition import DEFINITION

FAKE_KEY = "pa-TEST_ONLY_fake_voyage_key_never_real"


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_core.VOYAGE_API_KEY_ENV, FAKE_KEY)


@pytest.fixture
def recorder() -> list[httpx.Request]:
    return []


def _install(
    monkeypatch: pytest.MonkeyPatch,
    responder: Any,
    log: list[httpx.Request],
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        return responder(request)

    monkeypatch.setattr(_core, "_default_transport", httpx.MockTransport(_handler))


def _embeddings_context(payload: dict[str, Any] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.CREATE_EMBEDDINGS,
        model="voyage-3",
        request_id="req_voyage_emb_1",
        tenant_id="ten_voyage_1",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,
        payload=payload
        if payload is not None
        else {"inputs": ["Hello world", "Artificial intelligence"]},
        timeout_ms=5_000,
    )


def _rerank_context(payload: dict[str, Any] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.RERANK_DOCUMENTS,
        model="rerank-2",
        request_id="req_voyage_rerank_1",
        tenant_id="ten_voyage_1",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,
        payload=payload
        if payload is not None
        else {
            "query": "deep learning",
            "documents": ["neural networks", "cats and dogs", "transformer architecture"],
            "top_n": 2,
        },
        timeout_ms=5_000,
    )


# --------------------------------------------------------------------------- #
# 1. Declaration & Parity Tests                                               #
# --------------------------------------------------------------------------- #


def test_definition_parity_with_handlers() -> None:
    """Operations declared in DEFINITION must strictly match HANDLERS."""
    declared = {GatewayOperation(op) for op in DEFINITION["operations"]}
    assert set(HANDLERS.keys()) == declared


def test_capabilities_are_in_closed_set() -> None:
    """All declared capabilities must exist in the canonical closed set."""
    caps = set(DEFINITION["capabilities"].keys())
    assert caps <= CAPABILITY_KEYS


def test_models_have_valid_context_windows() -> None:
    """All declared models must specify a positive context window."""
    models = DEFINITION["models"]
    assert len(models) >= 2
    for m in models:
        assert isinstance(m["name"], str) and m["name"]
        assert isinstance(m["context_window"], int) and m["context_window"] > 0


# --------------------------------------------------------------------------- #
# 2. create_embeddings Tests                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_embeddings_success(
    monkeypatch: pytest.MonkeyPatch,
    recorder: list[httpx.Request],
) -> None:
    """create_embeddings succeeds and matches canonical schema."""
    fake_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    def _responder(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == f"Bearer {FAKE_KEY}"
        data = json.loads(request.read())
        assert data["model"] == "voyage-3"
        assert len(data["input"]) == 2
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "embedding": fake_embeddings[0], "index": 0},
                    {"object": "embedding", "embedding": fake_embeddings[1], "index": 1},
                ],
                "model": "voyage-3",
                "usage": {"total_tokens": 15},
            },
        )

    _install(monkeypatch, _responder, recorder)
    ctx = _embeddings_context()
    res = await create_embeddings(ctx)

    assert res.succeeded is True
    assert res.error is None
    assert res.output is not None
    assert res.output["embeddings"] == fake_embeddings
    assert res.output["dimensions"] == 3
    assert res.usage is not None
    assert res.usage.input_tokens == 15
    assert res.usage.units == 2


@pytest.mark.asyncio
async def test_create_embeddings_schema_policing() -> None:
    """create_embeddings rejects extra keys and empty input list."""
    # Extra key
    ctx_extra = _embeddings_context({"inputs": ["hi"], "extra_forbidden": True})
    res_extra = await create_embeddings(ctx_extra)
    assert res_extra.succeeded is False
    assert res_extra.error is not None
    assert res_extra.error.category == ErrorCategory.BAD_REQUEST

    # Empty list
    ctx_empty = _embeddings_context({"inputs": []})
    res_empty = await create_embeddings(ctx_empty)
    assert res_empty.succeeded is False
    assert res_empty.error is not None
    assert res_empty.error.category == ErrorCategory.BAD_REQUEST


# --------------------------------------------------------------------------- #
# 3. rerank_documents Tests                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rerank_documents_success(
    monkeypatch: pytest.MonkeyPatch,
    recorder: list[httpx.Request],
) -> None:
    """rerank_documents succeeds, orders results descending, and respects top_n."""

    def _responder(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == f"Bearer {FAKE_KEY}"
        data = json.loads(request.read())
        assert data["model"] == "rerank-2"
        assert data["query"] == "deep learning"
        assert len(data["documents"]) == 3
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"index": 0, "relevance_score": 0.85},
                    {"index": 1, "relevance_score": 0.12},
                    {"index": 2, "relevance_score": 0.94},
                ],
                "model": "rerank-2",
                "usage": {"total_tokens": 40},
            },
        )

    _install(monkeypatch, _responder, recorder)
    ctx = _rerank_context()  # top_n=2
    res = await rerank_documents(ctx)

    assert res.succeeded is True
    assert res.error is None
    assert res.output is not None
    results = res.output["results"]
    assert len(results) == 2  # top_n was 2
    # Sorted descending by score: index 2 (0.94) first, then index 0 (0.85)
    assert results[0]["index"] == 2
    assert results[0]["relevance_score"] == 0.94
    assert results[1]["index"] == 0
    assert results[1]["relevance_score"] == 0.85
    assert res.usage is not None
    assert res.usage.units == 3


@pytest.mark.asyncio
async def test_rerank_documents_schema_policing() -> None:
    """rerank_documents rejects missing query, empty docs, and extra keys."""
    # Extra key
    ctx_extra = _rerank_context({"query": "q", "documents": ["d"], "unsupported": 123})
    res_extra = await rerank_documents(ctx_extra)
    assert res_extra.succeeded is False
    assert res_extra.error is not None
    assert res_extra.error.category == ErrorCategory.BAD_REQUEST

    # Missing query
    ctx_no_q = _rerank_context({"documents": ["d"]})
    res_no_q = await rerank_documents(ctx_no_q)
    assert res_no_q.succeeded is False
    assert res_no_q.error is not None
    assert res_no_q.error.category == ErrorCategory.BAD_REQUEST

    # Empty documents
    ctx_empty_docs = _rerank_context({"query": "q", "documents": []})
    res_empty_docs = await rerank_documents(ctx_empty_docs)
    assert res_empty_docs.succeeded is False
    assert res_empty_docs.error is not None
    assert res_empty_docs.error.category == ErrorCategory.BAD_REQUEST


# --------------------------------------------------------------------------- #
# 4. Error Mapping & Zero-Leak Tests                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("http_status", "expected_category"),
    [
        (401, ErrorCategory.INVALID_CREDENTIAL),
        (403, ErrorCategory.INVALID_CREDENTIAL),
        (404, ErrorCategory.MODEL_UNAVAILABLE),
        (429, ErrorCategory.RATE_LIMITED),
        (400, ErrorCategory.BAD_REQUEST),
        (500, ErrorCategory.RETRYABLE_SERVER_ERROR),
        (503, ErrorCategory.RETRYABLE_SERVER_ERROR),
    ],
)
@pytest.mark.asyncio
async def test_error_status_mapping(
    monkeypatch: pytest.MonkeyPatch,
    recorder: list[httpx.Request],
    http_status: int,
    expected_category: ErrorCategory,
) -> None:
    """Upstream HTTP statuses map to exact closed error categories."""

    def _responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(http_status, text=f"Error {http_status} detail with {FAKE_KEY}")

    _install(monkeypatch, _responder, recorder)
    res = await create_embeddings(_embeddings_context())

    assert res.succeeded is False
    assert res.error is not None
    assert res.error.category == expected_category
    # Zero leak assertion: secret key never leaks in error message
    assert FAKE_KEY not in res.error.message


@pytest.mark.asyncio
async def test_timeout_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network timeout maps to ErrorCategory.TIMEOUT."""

    def _responder(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(_core, "_default_transport", httpx.MockTransport(_responder))
    res = await create_embeddings(_embeddings_context())

    assert res.succeeded is False
    assert res.error is not None
    assert res.error.category == ErrorCategory.TIMEOUT
    assert res.error.retryable is True


# --------------------------------------------------------------------------- #
# 5. Rigorous Capabilities & Architecture Diagnostic Tests                    #
# --------------------------------------------------------------------------- #


class TestLiveRegistrationAndWiring:
    def test_register_live_providers_includes_voyage(self) -> None:
        """Voyage AI must be registered in app.py and pass eager verification."""
        from app import register_live_providers
        from gateway.provider_registry import ProviderRegistry

        registry = ProviderRegistry()
        register_live_providers(registry)
        registry.eager_verify_all()
        reg = registry.get("voyage")
        assert reg is not None
        assert reg.definition.display_name == "Voyage AI"
        assert GatewayOperation.CREATE_EMBEDDINGS in reg.definition.operations
        assert GatewayOperation.RERANK_DOCUMENTS in reg.definition.operations
        assert reg.definition.capabilities.get("vision_input") is True
        assert reg.definition.capabilities.get("embeddings") is True
        assert reg.definition.capabilities.get("rerank") is True


@pytest.mark.asyncio
async def test_multimodal_embeddings_routing(
    monkeypatch: pytest.MonkeyPatch,
    recorder: list[httpx.Request],
) -> None:
    """voyage-multimodal-3 routes to /multimodalembeddings with formatted content."""

    def _responder(request: httpx.Request) -> httpx.Response:
        assert "/multimodalembeddings" in str(request.url)
        data = json.loads(request.read())
        assert data["model"] == "voyage-multimodal-3"
        assert "inputs" in data
        assert data["inputs"][0]["content"][0]["text"] == "Image description"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "embedding": [0.1] * 1024, "index": 0},
                ],
                "model": "voyage-multimodal-3",
                "usage": {"total_tokens": 12},
            },
        )

    _install(monkeypatch, _responder, recorder)
    ctx = ProviderContext(
        operation=GatewayOperation.CREATE_EMBEDDINGS,
        model="voyage-multimodal-3",
        request_id="req_multimodal_test",
        tenant_id="ten_test",
        credential_mode=CredentialMode.PLATFORM,
        payload={"inputs": ["Image description"]},
        timeout_ms=5_000,
    )
    res = await create_embeddings(ctx)
    assert res.succeeded is True
    assert res.output["dimensions"] == 1024


def test_models_metadata_integrity() -> None:
    """All models in models_metadata.json must have valid context window and dimensions."""
    from providers.voyage.definition import _MODELS_DATA

    assert len(_MODELS_DATA) >= 8
    for m_id, meta in _MODELS_DATA.items():
        assert meta.get("context_window", 0) > 0
        if "dimensions" in meta:
            assert meta["dimensions"] in (512, 1024)
        assert "capabilities" in meta


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_wire_envelope_via_fastapi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test full end-to-end wire envelope dispatch via FastAPI TestClient."""
    from fastapi.testclient import TestClient

    from app import build_app, register_live_providers
    from gateway.config import GatewayConfig
    from gateway.provider_registry import ProviderRegistry
    from gateway.route_registry import RouteRegistry

    def _responder(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "embeddings" in url:
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"object": "embedding", "embedding": [0.1, 0.2], "index": 0},
                    ],
                    "model": "voyage-3",
                    "usage": {"total_tokens": 5},
                },
            )
        if "rerank" in url:
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [{"index": 0, "relevance_score": 0.95}],
                    "model": "rerank-2",
                    "usage": {"total_tokens": 10},
                },
            )
        return httpx.Response(404)

    monkeypatch.setattr(_core, "_default_transport", httpx.MockTransport(_responder))

    _gw_auth_token = "unit-test-secret-version-seven"
    route_token = "rtk_voyage_test"
    config = GatewayConfig(
        secrets_by_version={1: _gw_auth_token},
        current_secret_version=1,
        route_map={route_token: "voyage"},
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

    # Test embeddings through HTTP endpoint
    emb_envelope = {
        "operation": "create_embeddings",
        "model": "voyage-3",
        "request_id": "wire_emb_1",
        "tenant_id": "wire_tenant_1",
        "credential": {"mode": "platform"},
        "payload": {"inputs": ["Arabic and English text"]},
        "timeout_ms": 10000,
    }
    resp_emb = client.post("/v1/execute", json=emb_envelope, headers=headers)
    assert resp_emb.status_code == 200
    data_emb = resp_emb.json()
    assert data_emb["succeeded"] is True
    assert data_emb["output"]["dimensions"] == 2

    # Test rerank through HTTP endpoint
    rerank_envelope = {
        "operation": "rerank_documents",
        "model": "rerank-2",
        "request_id": "wire_rerank_1",
        "tenant_id": "wire_tenant_1",
        "credential": {"mode": "platform"},
        "payload": {
            "query": "search query",
            "documents": ["doc 1"],
        },
        "timeout_ms": 10000,
    }
    resp_rerank = client.post("/v1/execute", json=rerank_envelope, headers=headers)
    assert resp_rerank.status_code == 200
    data_rerank = resp_rerank.json()
    assert data_rerank["succeeded"] is True
    assert len(data_rerank["output"]["results"]) == 1
