from __future__ import annotations

import json

import httpx
import pytest

from gateway_sdk import (
    GatewayClient,
    GatewayConfig,
    GatewaySDKError,
)


@pytest.fixture
def gateway_config() -> GatewayConfig:
    return GatewayConfig(
        base_url="https://gateway.example.test",
        api_key="unit-test-gateway-key-not-a-real-secret",
        provider_routes={"groq": "unit-test-route-token"},
    )


def test_repr_does_not_include_keys_or_route_tokens(
    gateway_config: GatewayConfig,
) -> None:
    rendered = repr(gateway_config)
    assert "unit-test-gateway-key-not-a-real-secret" not in rendered
    assert "unit-test-route-token" not in rendered


@pytest.mark.asyncio
async def test_execute_passes_unknown_operation_and_payload_through(
    gateway_config: GatewayConfig,
) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "succeeded": True,
                "output": {"new_field_from_future_operation": {"ok": True}},
                "usage": {"units": 1},
                "latency_ms": 4,
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=gateway_config, http_client=http)
    try:
        result = await gateway.execute(
            provider="groq",
            operation="operation_added_after_this_sdk_version",
            model="model-name",
            payload={"future_parameter": {"value": 7}, "temperature": 0.7},
        )
    finally:
        await http.aclose()

    body = seen["body"]
    headers = seen["headers"]
    assert isinstance(body, dict)
    assert body["operation"] == "operation_added_after_this_sdk_version"
    assert body["payload"]["future_parameter"] == {"value": 7}
    assert "unit-test-route-token" not in json.dumps(body)
    assert "unit-test-route-token" not in str(seen["url"])
    assert headers["x-route-token"] == "unit-test-route-token"
    assert result["output"]["new_field_from_future_operation"] == {"ok": True}


@pytest.mark.asyncio
async def test_unicode_legacy_alias_matches_gateway_casefolding() -> None:
    """ROUTE_TOKEN env aliases and display names use the same casefold rule."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"succeeded": True, "output": {"ok": True}})

    config = GatewayConfig.from_env(
        base_url="https://gateway.example.test",
        api_key="unit-test-gateway-key-not-a-real-secret",
        environ={"ROUTE_TOKEN_STRAẞE": "unit-test-route-token"},
    )
    assert config.provider_routes == {"strasse": "unit-test-route-token"}
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=config, http_client=http)
    try:
        await gateway.execute(
            provider="STRASSE",
            operation="generate_text",
            model="model-name",
            payload={},
        )
    finally:
        await http.aclose()

    assert seen[0].headers["X-Route-Token"] == "unit-test-route-token"
    assert "X-Provider-Name" not in seen[0].headers


@pytest.mark.asyncio
async def test_discover_uses_configured_names_and_preserves_manifest(
    gateway_config: GatewayConfig,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/describe"
        assert request.headers["X-Route-Token"] == "unit-test-route-token"
        return httpx.Response(
            200,
            json={
                "display_name": "Groq",
                "operations": ["generate_text", "future_operation"],
                "capabilities": {"chat": True, "future_capability": True},
                "future_manifest_field": {"retained": True},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=gateway_config, http_client=http)
    try:
        catalog = await gateway.discover()
    finally:
        await http.aclose()

    assert catalog == [
        {
            "name": "groq",
            "description": {
                "display_name": "Groq",
                "operations": ["generate_text", "future_operation"],
                "capabilities": {"chat": True, "future_capability": True},
                "future_manifest_field": {"retained": True},
            },
        }
    ]
    assert "unit-test-route-token" not in repr(catalog)


@pytest.mark.asyncio
async def test_execute_resolves_name_without_local_route_mapping() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"succeeded": True, "output": {"text": "ok"}})

    config = GatewayConfig(
        base_url="https://gateway.example.test",
        api_key="unit-test-gateway-key-not-a-real-secret",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=config, http_client=http)
    try:
        result = await gateway.execute(
            provider="Groq",
            operation="new_operation",
            model="model-name",
            payload={"future_payload_field": {"value": 5}},
        )
    finally:
        await http.aclose()

    request = seen[0]
    assert request.headers["X-Provider-Name"] == "Groq"
    assert "X-Route-Token" not in request.headers
    assert result["output"]["text"] == "ok"


@pytest.mark.asyncio
async def test_discover_uses_gateway_catalog_without_local_route_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/providers"
        assert "X-Route-Token" not in request.headers
        return httpx.Response(
            200,
            json={
                "providers": [
                    {
                        "name": "Groq",
                        "description": {
                            "display_name": "Groq",
                            "operations": ["generate_text", "future_operation"],
                            "future_field": {"retained": True},
                        },
                    }
                ]
            },
        )

    config = GatewayConfig(
        base_url="https://gateway.example.test",
        api_key="unit-test-gateway-key-not-a-real-secret",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=config, http_client=http)
    try:
        catalog = await gateway.discover()
    finally:
        await http.aclose()

    assert catalog[0]["name"] == "Groq"
    assert catalog[0]["description"]["operations"] == [
        "generate_text",
        "future_operation",
    ]
    assert catalog[0]["description"]["future_field"] == {"retained": True}


@pytest.mark.asyncio
async def test_health_methods_use_separate_gateway_and_provider_paths(
    gateway_config: GatewayConfig,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"status": "UNKNOWN", "checked_at": None})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=gateway_config, http_client=http)
    try:
        gateway_health = await gateway.check_gateway_health()
        provider_health = await gateway.check_provider_health("groq")
    finally:
        await http.aclose()

    assert gateway_health["status"] == "ok"
    assert provider_health["status"] == "UNKNOWN"
    assert seen == ["/healthz", "/v1/health"]


@pytest.mark.asyncio
async def test_name_resolution_covers_describe_models_operations_and_health() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers["X-Provider-Name"] == "Groq"
        assert "X-Route-Token" not in request.headers
        if request.url.path == "/v1/describe":
            return httpx.Response(200, json={"operations": ["generate_text"]})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"models": [{"name": "model-a"}]})
        return httpx.Response(200, json={"status": "UNKNOWN"})

    config = GatewayConfig(
        base_url="https://gateway.example.test",
        api_key="unit-test-gateway-key-not-a-real-secret",
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=config, http_client=http)
    try:
        description = await gateway.describe("Groq")
        models = await gateway.list_models("Groq")
        operations = await gateway.list_operations("Groq")
        health = await gateway.check_provider_health("Groq")
    finally:
        await http.aclose()

    assert description["operations"] == ["generate_text"]
    assert models == [{"name": "model-a"}]
    assert operations == ["generate_text"]
    assert health["status"] == "UNKNOWN"
    assert seen_paths == ["/v1/describe", "/v1/models", "/v1/describe", "/v1/health"]


@pytest.mark.asyncio
async def test_execution_failure_is_open_ended_and_keeps_raw_response(
    gateway_config: GatewayConfig,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "succeeded": False,
                "error": {
                    "category": "future_error_category",
                    "message": "operation declined",
                    "retryable": False,
                    "future_error_field": "kept",
                },
                "latency_ms": 1,
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=gateway_config, http_client=http)
    try:
        with pytest.raises(GatewaySDKError) as caught:
            await gateway.execute(
                provider="groq",
                operation="future_operation",
                model="model-name",
                payload={},
            )
    finally:
        await http.aclose()

    assert caught.value.category == "future_error_category"
    assert caught.value.response["error"]["future_error_field"] == "kept"


@pytest.mark.asyncio
async def test_list_models_preserves_effective_support_and_future_fields(
    gateway_config: GatewayConfig,
) -> None:
    expected = {
        "name": "model-a",
        "context_window": 32768,
        "operations": ["generate_text"],
        "capabilities": {"chat": True},
        "future_gateway_field": {"preserved": True},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"models": [expected]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = GatewayClient(config=gateway_config, http_client=http)
    try:
        models = await gateway.list_models("groq")
    finally:
        await http.aclose()

    assert models == [expected]
