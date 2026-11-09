"""Transport and failure categorization tests for Syntx Layer 1."""

import httpx
import pytest

from providers.syntx import _core


@pytest.fixture(autouse=True)
def clean_transport():
    yield
    _core.set_transport_override(None)


def test_http_request_with_mock_transport():
    """Verify http_request dispatches to injected transport."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok", "url": str(request.url)})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    resp = _core.http_request("GET", "https://api.syntx.ai/api/v1/test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.parametrize(
    "category,message,retry_ms",
    [
        ("auth_expired", "Session token expired", None),
        ("invalid_credential", "Invalid credentials", None),
        ("rate_limited", "Rate limit hit", 2000),
        ("model_unavailable", "Model not found", None),
        ("provider_unavailable", "Upstream down", None),
        ("bad_request", "Bad payload", None),
        ("timeout", "Request timed out", None),
    ],
)
def test_upstream_failure_exception_properties(category, message, retry_ms):
    """Verify UpstreamFailure exception properties."""
    exc = _core.UpstreamFailure(category, message, retry_after_ms=retry_ms)
    assert exc.category == category
    assert exc.message == message
    assert exc.retry_after_ms == retry_ms
    assert str(exc) == message
