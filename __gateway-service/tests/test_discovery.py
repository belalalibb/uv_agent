"""Discovery tests — /v1/describe, /v1/models, /v1/health projections."""

from __future__ import annotations

import sys
from dataclasses import replace
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from app import build_app
from gateway.contracts import FacadeResult, GatewayOperation
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from tests.conftest import (
    EXAMPLE_DEFINITION,
    ROUTE_TOKEN,
    auth_headers,
    routed_headers,
    valid_envelope,
)

pytestmark = pytest.mark.integration


def test_provider_catalog_lists_enabled_public_names_and_operations(client) -> None:
    response = client.get("/v1/providers", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert len(body["providers"]) == 1
    provider = body["providers"][0]
    assert provider["name"] == "Example Provider (mock)"
    assert provider["description"]["operations"] == ["generate_text"]
    assert "example_mock" not in str(body)
    assert "rtk_unit_test_opaque_token_value" not in str(body)


def test_provider_catalog_requires_auth(client) -> None:
    assert client.get("/v1/providers").status_code == 401


def test_build_app_auto_discovers_provider_packages(config) -> None:
    """Production composition needs no manually populated registry."""
    app = build_app(config, routes=RouteRegistry({}))

    with TestClient(app) as test_client:
        response = test_client.get("/v1/providers", headers=auth_headers())
        discovered = response.json()["providers"]
        assert discovered
        name_headers = auth_headers()
        name_headers["X-Provider-Name"] = discovered[0]["name"]
        describe = test_client.get("/v1/describe", headers=name_headers)

    assert response.status_code == 200
    assert discovered
    assert all(item["name"] != "Example Provider (mock)" for item in discovered)
    assert describe.status_code == 200
    assert describe.json()["display_name"] == discovered[0]["name"]
    assert "_example" not in response.text
    assert "_template" not in response.text


def test_provider_catalog_hides_disabled_provider(client, routes) -> None:
    routes.set_disabled("example_mock", True)

    response = client.get("/v1/providers", headers=auth_headers())

    assert response.status_code == 200
    assert response.json() == {"providers": []}


def test_name_catalog_and_routing_need_no_legacy_route_map(config, providers) -> None:
    """Discovered provider names work without GW_ROUTE_MAP entries."""
    config_without_routes = replace(config, route_map={})
    routes_without_legacy_tokens = RouteRegistry({})
    headers = auth_headers()
    headers["X-Provider-Name"] = "Example Provider (mock)"

    with TestClient(
        build_app(config_without_routes, providers, routes_without_legacy_tokens)
    ) as test_client:
        catalog = test_client.get("/v1/providers", headers=auth_headers())
        describe = test_client.get("/v1/describe", headers=headers)
        execution = test_client.post(
            "/v1/execute", headers=headers, json=valid_envelope()
        )
        legacy_execution = test_client.post(
            "/v1/execute", headers=routed_headers(), json=valid_envelope()
        )

    assert catalog.status_code == 200
    assert [item["name"] for item in catalog.json()["providers"]] == [
        "Example Provider (mock)"
    ]
    assert describe.status_code == 200
    assert execution.status_code == 200
    assert execution.json()["succeeded"] is True
    assert legacy_execution.status_code == 404


def test_name_resolution_is_independent_of_legacy_token_revocation(
    client, routes
) -> None:
    routes.revoke(ROUTE_TOKEN)
    name_headers = auth_headers()
    name_headers["X-Provider-Name"] = "Example Provider (mock)"

    catalog = client.get("/v1/providers", headers=auth_headers())
    describe_by_name = client.get("/v1/describe", headers=name_headers)
    describe_by_token = client.get("/v1/describe", headers=routed_headers())

    assert [item["name"] for item in catalog.json()["providers"]] == [
        "Example Provider (mock)"
    ]
    assert describe_by_name.status_code == 200
    assert describe_by_token.status_code == 404
    assert describe_by_token.json()["error"]["message"] == "unknown route"


def test_public_provider_name_selects_all_discovery_surfaces(client) -> None:
    headers = auth_headers()
    headers["X-Provider-Name"] = "Example Provider (mock)"

    describe = client.get("/v1/describe", headers=headers)
    models = client.get("/v1/models", headers=headers)
    health = client.get("/v1/health", headers=headers)

    assert describe.status_code == models.status_code == health.status_code == 200
    assert describe.json()["operations"] == ["generate_text"]
    assert models.json()["models"][0]["name"] == "example-mock-model"
    assert health.json()["status"] == "UNKNOWN"


def test_describe_projection(client) -> None:
    response = client.get("/v1/describe", headers=routed_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Example Provider (mock)"
    assert body["credential_mode"] == "user_key"
    assert body["operations"] == ["generate_text"]
    assert body["models"] == [
        {
            "name": "example-mock-model",
            "context_window": 8192,
            "operations": ["generate_text"],
            "capabilities": {"chat": True},
        }
    ]
    assert body["definition_version"] == "1.0.0"
    assert body["health_supported"] is False


def test_describe_requires_auth(client) -> None:
    response = client.get("/v1/describe", headers={"X-Route-Token": "anything"})
    assert response.status_code == 401


def test_describe_route_token_in_header_not_url(client) -> None:
    # OPEN-3: the token travels ONLY in X-Route-Token. A token in the query
    # string must NOT route (and without the header the lookup fails 404).
    response = client.get(
        "/v1/describe?route_token=rtk_unit_test_opaque_token_value",
        headers=auth_headers(),
    )
    assert response.status_code == 404


def test_models_subset(client) -> None:
    response = client.get("/v1/models", headers=routed_headers())
    assert response.status_code == 200
    assert response.json() == {
        "models": [
            {
                "name": "example-mock-model",
                "context_window": 8192,
                "operations": ["generate_text"],
                "capabilities": {"chat": True},
            }
        ]
    }


def test_health_unknown_is_honest(client) -> None:
    response = client.get("/v1/health", headers=routed_headers())
    assert response.status_code == 200
    assert response.json() == {"status": "UNKNOWN", "checked_at": None}


def test_discovery_unknown_route_uniform_404(client) -> None:
    for path in ("/v1/describe", "/v1/models", "/v1/health"):
        headers = auth_headers()
        headers["X-Route-Token"] = "rtk_ghost"
        response = client.get(path, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "unknown route"


def test_model_support_defaults_and_overrides_are_resolved_and_enforced(
    config, routes
) -> None:
    definition = dict(EXAMPLE_DEFINITION)
    definition["models"] = [
        {"name": "example-mock-model", "context_window": 8192},
        {
            "name": "text-only-model",
            "support": {
                "operations": [],
                "capabilities": {"chat": False},
            },
        },
    ]
    providers = ProviderRegistry()
    providers.register(
        slug="example_mock",
        raw_definition=definition,
        facade_module="providers._example.adapter",
    )

    with TestClient(build_app(config, providers, routes)) as test_client:
        described = test_client.get("/v1/describe", headers=routed_headers())
        models = test_client.get("/v1/models", headers=routed_headers())
        default_execute = test_client.post(
            "/v1/execute", headers=routed_headers(), json=valid_envelope()
        )
        override_execute = test_client.post(
            "/v1/execute",
            headers=routed_headers(),
            json=valid_envelope(model="text-only-model"),
        )

    expected_models = [
        {
            "name": "example-mock-model",
            "context_window": 8192,
            "operations": ["generate_text"],
            "capabilities": {"chat": True},
        },
        {
            "name": "text-only-model",
            "context_window": None,
            "operations": [],
            "capabilities": {"chat": False},
        },
    ]
    assert described.status_code == models.status_code == 200
    assert described.json()["models"] == expected_models
    assert models.json()["models"] == expected_models
    assert "support" not in str(models.json())
    assert default_execute.status_code == 200
    assert default_execute.json()["succeeded"] is True
    assert override_execute.status_code == 200
    assert override_execute.json()["succeeded"] is False
    assert override_execute.json()["error"]["category"] == "unsupported_capability"


def test_model_override_can_add_an_operation_to_provider_defaults(
    config, routes, monkeypatch
) -> None:
    module = ModuleType("tests.model_override_facade")

    async def generate_text(_context):
        return FacadeResult(succeeded=True, output={"text": "default"})

    async def analyze_vision(_context):
        return FacadeResult(succeeded=True, output={"vision": "ok"})

    module.HANDLERS = {
        GatewayOperation.GENERATE_TEXT: generate_text,
        GatewayOperation.ANALYZE_VISION: analyze_vision,
    }
    monkeypatch.setitem(sys.modules, module.__name__, module)

    definition = dict(EXAMPLE_DEFINITION)
    definition["models"] = [
        {
            "name": "vision-model",
            "support": {"operations": ["analyze_vision"]},
        }
    ]
    providers = ProviderRegistry()
    providers.register(
        slug="example_mock",
        raw_definition=definition,
        facade_module=module.__name__,
    )

    with TestClient(build_app(config, providers, routes)) as test_client:
        response = test_client.post(
            "/v1/execute",
            headers=routed_headers(),
            json=valid_envelope(operation="analyze_vision", model="vision-model"),
        )

    assert response.status_code == 200
    assert response.json()["succeeded"] is True
    assert response.json()["output"] == {"vision": "ok"}
