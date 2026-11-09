"""Account maintenance, token refresh, and health checking tests for Syntx Layer 1."""

import json
import httpx
import pytest

from providers.syntx import _core


@pytest.fixture(autouse=True)
def setup_maint_env(tmp_path, monkeypatch):
    test_acc_file = tmp_path / "accounts_syntx.json"
    initial_accs = [
        {"email": "maint@example.com", "token": "maint-token-active", "status": "active"},
        {"email": "dead@example.com", "token": "maint-token-dead", "status": "active"},
    ]
    test_acc_file.write_text(json.dumps(initial_accs), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_acc_file))
    yield test_acc_file
    _core.set_transport_override(None)


def test_refresh_healthy_account():
    """Verify refresh returns True when account has remaining balance."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balance": 50})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    acc = {"email": "maint@example.com", "token": "maint-token-active"}
    is_healthy = _core.refresh(acc)
    assert is_healthy is True

    # Ensure account is still in pool
    accounts = _core.load_accounts_pool()
    assert any(a["token"] == "maint-token-active" for a in accounts)


def test_refresh_depleted_zero_balance_eviction():
    """Verify refresh evicts account from pool when balance is 0."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"balance": 0})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    acc = {"email": "dead@example.com", "token": "maint-token-dead"}
    is_healthy = _core.refresh(acc)
    assert is_healthy is False

    # Account must be evicted from pool
    accounts = _core.load_accounts_pool()
    assert not any(a["token"] == "maint-token-dead" for a in accounts)


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_refresh_http_failure_eviction(status_code):
    """Verify refresh evicts account from pool on auth or rate-limit HTTP codes."""
    def mock_responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "unauthorized or exhausted"})

    _core.set_transport_override(httpx.MockTransport(mock_responder))

    acc = {"email": "maint@example.com", "token": "maint-token-active"}
    is_healthy = _core.refresh(acc)
    assert is_healthy is False

    accounts = _core.load_accounts_pool()
    assert not any(a["token"] == "maint-token-active" for a in accounts)


def test_background_refill_trigger_respects_lock(monkeypatch):
    """Verify background refill does not trigger when lock is held or disabled."""
    # When disabled by env
    monkeypatch.setenv("GW_SYNTX_DISABLE_BG_REFILL", "1")
    _core.trigger_background_refill(count=2)
    assert not _core._REFILL_LOCK.locked()

    # When lock is acquired by another process
    monkeypatch.delenv("GW_SYNTX_DISABLE_BG_REFILL")
    _core._REFILL_LOCK.acquire()
    try:
        # Should return without blocking or error
        _core._background_refill_worker(count=2)
    finally:
        _core._REFILL_LOCK.release()

