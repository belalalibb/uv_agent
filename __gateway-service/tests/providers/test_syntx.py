"""Canonical Syntx Provider Facade Tests — 100% Hermetic with Mock Transport.

Compliance: Bolla Constitution v1.2 & UNIVERSAL_PROVIDER_SPEC_AND_BLUEPRINT.md
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests Non-vision model rejection (grok-4.6) with zero network touch.
- Tests Zero-leak: no credentials, tokens, or internal paths cross the wire.
"""

import json
from uuid import uuid4

import httpx
import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
    ProviderDefinition,
)
from providers.syntx import DEFINITION, HANDLERS, _core
from providers.syntx.adapter import analyze_vision, generate_text

PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="
SENTINEL_TOKEN = "sentinel_secret_token_12345"


def build_context(payload=None, operation=GatewayOperation.GENERATE_TEXT, **overrides) -> ProviderContext:
    data = dict(
        operation=operation,
        model="claude-opus-4-8",
        request_id="req-test-123",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={"messages": [{"role": "user", "content": "hello"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


@pytest.fixture(autouse=True)
def hermetic_pool(tmp_path, monkeypatch):
    """Ensure tests run against an isolated temporary accounts pool."""
    test_accounts_file = tmp_path / "test_accounts.json"
    initial_accounts = [
        {
            "email": "test@example.com",
            "token": SENTINEL_TOKEN,
            "chat_uuid": "mock-chat-uuid-1234",
            "provider": "tempmailclub",
            "status": "active",
            "created_at": "2026-09-12 12:00:00",
        }
    ]
    test_accounts_file.write_text(json.dumps(initial_accounts), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_accounts_file))
    yield test_accounts_file
    _core.set_transport_override(None)


def test_definition_parity_and_honesty():
    """Verify DEFINITION matches Gateway v1 contracts and HANDLERS parity."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert {op.value for op in HANDLERS} == set(DEFINITION["operations"])
    assert set(DEFINITION["operations"]) == {"generate_text", "analyze_vision"}
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.capabilities["vision_input"] is True
    assert parsed.capabilities["chat"] is True
    assert parsed.capabilities["reasoning"] is True
    assert parsed.capabilities["code"] is True
    assert parsed.capabilities["browser"] is True
    assert parsed.health_supported is False
    assert len(parsed.models) >= 28
    model_names = {m.name for m in parsed.models}
    assert "claude-opus-4-8" in model_names
    assert "gpt-5.6-terra" in model_names
    assert "grok-4.6" in model_names


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"messages": []},
        {"messages": "invalid"},
        {"messages": [None]},
        {"messages": [{"role": "user", "content": []}]},
        {"messages": [{"role": "user", "content": "x", "forbidden_key": True}]},
        {"messages": [{"role": "user", "content": "x"}], "files": []},
        {"messages": [{"role": "user", "content": "x"}], "temperature": True},
        {"messages": [{"role": "user", "content": "x"}], "temperature": float("nan")},
        {"messages": [{"role": "user", "content": "x"}], "max_tokens": "not_an_int"},
    ],
)
async def test_bad_schema_rejected_immediately(payload):
    """Ensure malformed payloads fail before touching upstream."""
    result = await generate_text(build_context(payload=payload))
    assert not result.succeeded
    assert result.error.category is ErrorCategory.BAD_REQUEST


async def test_non_vision_model_protection():
    """Ensure text-only model (grok-4.6) is rejected for analyze_vision with zero network touch."""
    ctx = build_context(
        payload={"image_b64": PNG_B64, "instruction": "describe image"},
        operation=GatewayOperation.ANALYZE_VISION,
        model="grok-4.6",
    )
    result = await analyze_vision(ctx)
    assert not result.succeeded
    assert result.error.category is ErrorCategory.UNSUPPORTED_CAPABILITY
    assert "does not support vision" in result.error.message


async def test_success_text_generation():
    """Verify canonical generate_text execution and output schema with history preservation."""
    captured_payloads = []
    call_counts = {"messages": 0}

    def mock_responder(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path.endswith("/chats"):
            return httpx.Response(201, json={"uuid": str(uuid4())})
        if url_path.endswith("/llm/generate"):
            data = json.loads(request.content.decode("utf-8"))
            captured_payloads.append(data)
            return httpx.Response(200, json={"job_id": "test-job-id"})
        if "/messages" in url_path:
            call_counts["messages"] += 1
            if call_counts["messages"] == 1:
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "id": 999,
                            "author_id": -1,
                            "usage": {"input_tokens": 12, "output_tokens": 25},
                            "message_object": [
                                {"object_type": "text", "object_text": "Syntx generated reply", "completed": True}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    ctx = build_context(
        payload={
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "What is Python?"},
            ],
            "temperature": 0.7,
            "max_tokens": 100,
        }
    )
    result = await generate_text(ctx)
    assert result.succeeded
    assert result.output == {"text": "Syntx generated reply", "finish_reason": "stop"}
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 25
    assert result.usage.units == 1
    assert len(captured_payloads) == 1
    assert "Previous conversation:\nsystem: You are helpful." in captured_payloads[0]["text"]
    assert "Current request:\nuser: What is Python?" in captured_payloads[0]["text"]


async def test_success_vision_analysis():
    """Verify canonical analyze_vision execution and output schema."""
    call_counts = {"messages": 0}

    def mock_responder(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path.endswith("/upload-files"):
            return httpx.Response(
                200, json={"files": [{"url": "https://r2.syntx.ai/test_bucket/test_image.png"}]}
            )
        if url_path.endswith("/llm/generate"):
            data = json.loads(request.content.decode("utf-8"))
            assert data["files"][0]["object_type"] == "image"
            assert "r2.syntx.ai" in data["files"][0]["object_url"]
            return httpx.Response(200, json={"job_id": "test-job-vision"})
        if "/messages" in url_path:
            call_counts["messages"] += 1
            if call_counts["messages"] == 1:
                return httpx.Response(200, json={"messages": []})
            return httpx.Response(
                200,
                json={
                    "messages": [
                        {
                            "id": 1001,
                            "author_id": -1,
                            "message_object": [
                                {"object_type": "text", "object_text": "I see a single pixel.", "completed": True}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    ctx = build_context(
        payload={"image_b64": PNG_B64, "image_format": "png", "instruction": "What is in this image?"},
        operation=GatewayOperation.ANALYZE_VISION,
        model="claude-opus-4-8",
    )
    result = await analyze_vision(ctx)
    assert result.succeeded
    assert result.output == {"text": "I see a single pixel."}


@pytest.mark.parametrize(
    "status,expected_category",
    [
        (401, ErrorCategory.INVALID_CREDENTIAL),
        (403, ErrorCategory.INVALID_CREDENTIAL),
        (404, ErrorCategory.MODEL_UNAVAILABLE),
        (429, ErrorCategory.RATE_LIMITED),
        (400, ErrorCategory.BAD_REQUEST),
        (500, ErrorCategory.RETRYABLE_SERVER_ERROR),
    ],
)
async def test_http_failures_and_zero_leak(status, expected_category):
    """Verify canonical error mapping and ensure zero leakage of secrets or paths."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={
                "detail": {
                    "message": f"secret={SENTINEL_TOKEN} internal=/var/log/private https://secret.invalid",
                    "retry_after_seconds": 5,
                }
            },
        )

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    result = await generate_text(build_context())
    assert not result.succeeded
    assert result.error.category is expected_category
    assert result.output is None
    dump = result.model_dump_json()
    assert SENTINEL_TOKEN not in dump
    assert "/var/log/private" not in dump
    if status == 429:
        assert result.error.retry_after_ms == 5000


async def test_operation_and_credential_guards():
    """Verify operation matching and platform credential enforcement."""
    # Wrong operation
    res1 = await generate_text(build_context(operation=GatewayOperation.GENERATE_IMAGE))
    assert res1.error.category is ErrorCategory.UNSUPPORTED_CAPABILITY

    # Caller supplied credential value (forbidden in platform mode)
    res2 = await generate_text(
        build_context(credential_mode=CredentialMode.USER_KEY, credential_value="secret")
    )
    assert res2.error.category is ErrorCategory.INVALID_CREDENTIAL
