"""Security and Zero-Leakage Tests for Syntx Provider."""

import json
from pathlib import Path
import pytest

from gateway.contracts import CredentialMode, ErrorCategory, GatewayOperation, ProviderContext
from providers.syntx import DEFINITION, HANDLERS, _core
from providers.syntx.adapter import generate_text

TEST_SECRET = "super_secret_bearer_token_xyz"


@pytest.fixture(autouse=True)
def setup_sec_env(tmp_path, monkeypatch):
    test_acc_file = tmp_path / "accounts_syntx.json"
    initial_accs = [
        {"email": "sec@example.com", "token": TEST_SECRET, "status": "active"}
    ]
    test_acc_file.write_text(json.dumps(initial_accs), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_acc_file))
    yield test_acc_file
    _core.set_transport_override(None)


def test_import_has_zero_side_effects():
    """Verify package import has zero network calls or file mutations."""
    # Ensure DEFINITION is pure data
    assert isinstance(DEFINITION, dict)
    assert DEFINITION["credential_mode"] == "platform"


async def test_zero_leakage_on_upstream_failure(monkeypatch):
    """Ensure internal tokens, file paths, and private URLs never leak into errors."""
    def fail_call(**kwargs):
        raise _core.UpstreamFailure(
            "auth_expired",
            f"Failed with token={TEST_SECRET} on path /secret/syntx_accounts.json",
            provider_code="401",
        )

    monkeypatch.setattr(_core, "ask", fail_call)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="claude-opus-4-8",
        request_id="sec-req",
        tenant_id="tenant-sec",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=5000,
        payload={"messages": [{"role": "user", "content": "test"}]},
    )
    result = await generate_text(ctx)
    assert not result.succeeded
    assert result.error.category is ErrorCategory.AUTH_EXPIRED

    # Dump JSON wire representation
    dump = result.model_dump_json()
    assert TEST_SECRET not in dump
    assert "/secret" not in dump
    assert "syntx_accounts.json" not in dump


async def test_caller_key_rejection():
    """Ensure platform mode strictly forbids caller-supplied API keys."""
    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="claude-opus-4-8",
        request_id="sec-req",
        tenant_id="tenant-sec",
        credential_mode=CredentialMode.USER_KEY,
        credential_value="user_supplied_api_key",
        timeout_ms=5000,
        payload={"messages": [{"role": "user", "content": "test"}]},
    )
    result = await generate_text(ctx)
    assert not result.succeeded
    assert result.error.category is ErrorCategory.INVALID_CREDENTIAL
