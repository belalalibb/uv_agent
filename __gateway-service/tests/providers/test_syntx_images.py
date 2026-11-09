"""Vision and image upload tests for Syntx Layer 1 & 2."""

import base64
import json
import httpx
import pytest

from gateway.contracts import ErrorCategory, GatewayOperation, ProviderContext, CredentialMode
from providers.syntx import _core
from providers.syntx.adapter import analyze_vision

PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="


@pytest.fixture(autouse=True)
def setup_images(tmp_path, monkeypatch):
    test_accounts_file = tmp_path / "accounts_syntx.json"
    initial_accounts = [
        {
            "email": "image_tester@example.com",
            "token": "token-syntx-img-123",
            "chat_uuid": "chat-uuid-session-img",
            "provider": "tempmailclub",
            "status": "active",
            "created_at": "2026-09-12 12:00:00",
        }
    ]
    test_accounts_file.write_text(json.dumps(initial_accounts), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_accounts_file))
    yield test_accounts_file
    _core.set_transport_override(None)


def test_vision_model_capabilities_matrix():
    """Verify vision capability detection against models_metadata.json."""
    assert _core.is_vision_model("claude-opus-4-8") is True
    assert _core.is_vision_model("gpt-5.6-terra") is True
    assert _core.is_vision_model("claude-sonnet-5") is True
    assert _core.is_vision_model("grok-4.6") is False
    assert _core.is_vision_model("non-existent-model") is False


def test_upload_image_bytes_success_and_failure():
    """Verify multipart upload to Syntx R2 bucket."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chats/upload-files"):
            return httpx.Response(
                200, json={"files": [{"url": "https://r2.syntx.ai/bucket/photo.png"}]}
            )
        return httpx.Response(400, json={"detail": "fail"})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    raw_png = base64.b64decode(PNG_B64)
    url = _core.upload_image_bytes("token-123", raw_png, "photo.png")
    assert url == "https://r2.syntx.ai/bucket/photo.png"

    # Test failure on upload
    def mock_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "s3 error"})

    _core.set_transport_override(httpx.MockTransport(mock_fail))
    with pytest.raises(_core.UpstreamFailure) as exc_info:
        _core.upload_image_bytes("token-123", raw_png, "photo.png")
    assert exc_info.value.category == "bad_request"


async def test_bad_image_payloads_in_facade():
    """Verify analyze_vision rejects missing or non-string image data."""
    ctx_missing_b64 = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        model="claude-opus-4-8",
        request_id="test-req",
        tenant_id="test-tenant",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={"instruction": "describe"},
    )
    res = await analyze_vision(ctx_missing_b64)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST

    ctx_missing_inst = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        model="claude-opus-4-8",
        request_id="test-req",
        tenant_id="test-tenant",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={"image_b64": PNG_B64},
    )
    res2 = await analyze_vision(ctx_missing_inst)
    assert not res2.succeeded
    assert res2.error.category is ErrorCategory.BAD_REQUEST
