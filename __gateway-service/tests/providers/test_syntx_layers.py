"""Three-Layer Architectural Separation Tests for Syntx Provider."""

import json
from pathlib import Path

import pytest

from gateway.contracts import GatewayOperation, ProviderDefinition
from providers.syntx import DEFINITION, HANDLERS, _core
from providers.syntx.adapter import generate_text, analyze_vision


@pytest.fixture(autouse=True)
def setup_layer_env(tmp_path, monkeypatch):
    test_acc_file = tmp_path / "accounts_syntx.json"
    initial_accs = [
        {"email": "layer_tester@example.com", "token": "layer-token-1", "status": "active"},
        {"email": "layer_tester2@example.com", "token": "layer-token-2", "status": "expired"},
    ]
    test_acc_file.write_text(json.dumps(initial_accs), encoding="utf-8")
    monkeypatch.setenv("GW_SYNTX_ACCOUNTS_FILE", str(test_acc_file))
    yield test_acc_file
    _core.set_transport_override(None)


def test_layer1_pool_atomic_operations(setup_layer_env):
    """Verify Layer 1 manages account pool atomically under lock."""
    accounts = _core.load_accounts_pool()
    assert len(accounts) == 2

    active = _core.get_active_account()
    assert active is not None
    assert active["token"] == "layer-token-1"

    # Evict active account
    _core.evict_account("layer-token-1")
    reloaded = _core.load_accounts_pool()
    assert len(reloaded) == 1
    assert reloaded[0]["token"] == "layer-token-2"

    # No active accounts remaining
    assert _core.get_active_account() is None


def test_layer2_facade_contract_integrity():
    """Verify Layer 2 adapter exports only recognized async handlers."""
    assert GatewayOperation.GENERATE_TEXT in HANDLERS
    assert GatewayOperation.ANALYZE_VISION in HANDLERS
    assert HANDLERS[GatewayOperation.GENERATE_TEXT] is generate_text
    assert HANDLERS[GatewayOperation.ANALYZE_VISION] is analyze_vision


def test_layer3_contract_wire_parity():
    """Verify Layer 3 DEFINITION complies with Gateway wire contracts."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "Syntx AI"
    assert parsed.definition_version == "1.0.0"
    assert len(parsed.models) >= 28
    assert set(parsed.operations) == {
        GatewayOperation.GENERATE_TEXT,
        GatewayOperation.ANALYZE_VISION,
    }
