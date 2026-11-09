"""End-to-end Gateway SDK ↔ Gateway API checks with a test-only new provider.

Run from this project with Python 3.12+: ``pytest tests/test_sdk_gateway_integration.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPOSITORY_ROOT / "__gateway-service"
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT))

from gateway_sdk import GatewayClient, GatewayConfig, GatewaySDKError  # noqa: E402

from app import build_app  # noqa: E402
from gateway.config import GatewayConfig as ServiceConfig  # noqa: E402
from gateway.contracts import (  # noqa: E402
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.provider_registry import ProviderRegistry  # noqa: E402
from gateway.route_registry import RouteRegistry  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_sdk_discovers_and_executes_a_gateway_added_provider(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No provider name, route token, or operation list is added to the SDK."""

    provider_name = "Integration-Only Fresh Provider"
    provider_slug = "integration_only_fresh_provider"
    route_token = "rtk_integration_only_server_side"
    gateway_secret = "integration-gateway-secret-not-a-real-value"
    module_name = "providers._integration_added.adapter"

    package = ModuleType("providers._integration_added")
    package.__path__ = []  # type: ignore[attr-defined]
    adapter = ModuleType(module_name)

    async def generate_text(context: ProviderContext) -> FacadeResult:
        return FacadeResult(
            succeeded=True,
            output={"model": context.model, "payload": context.payload},
            usage=Usage(units=1),
        )

    async def analyze_vision(context: ProviderContext) -> FacadeResult:
        return FacadeResult(
            succeeded=True,
            output={"model": context.model, "vision": context.payload},
            usage=Usage(units=1),
        )

    adapter.HANDLERS = {
        GatewayOperation.GENERATE_TEXT: generate_text,
        GatewayOperation.ANALYZE_VISION: analyze_vision,
    }  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "providers._integration_added", package)
    monkeypatch.setitem(sys.modules, module_name, adapter)

    providers = ProviderRegistry()
    providers.register(
        slug=provider_slug,
        raw_definition={
            "display_name": provider_name,
            "definition_version": "1.0.0",
            "credential_mode": "platform",
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": [
                {"name": "integration-model", "context_window": 4096},
                {
                    "name": "vision-model",
                    "support": {
                        "operations": ["analyze_vision"],
                        "capabilities": {"vision_input": True},
                    },
                },
            ],
            "health_supported": False,
        },
        facade_module=module_name,
    )
    providers.eager_verify_all()

    service_config = ServiceConfig(
        secrets_by_version={1: gateway_secret},
        current_secret_version=1,
        route_map={route_token: provider_slug},
        allowed_provider_slugs=frozenset({provider_slug}),
    )
    routes = RouteRegistry(service_config.route_map)
    app = build_app(service_config, providers, routes)

    observed_requests: list[tuple[str, str, dict[bytes, bytes]]] = []

    async def capture_requests(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            observed_requests.append((scope["method"], scope["path"], dict(scope["headers"])))
        await app(scope, receive, send)

    transport = httpx.ASGITransport(app=capture_requests)
    http = httpx.AsyncClient(transport=transport, base_url="http://gateway.test")
    # No provider_routes / ROUTE_TOKEN_* values are configured in the new SDK.
    sdk = GatewayClient(
        config=GatewayConfig(
            base_url="http://gateway.test",
            api_key=gateway_secret,
        ),
        http_client=http,
    )
    legacy_sdk = GatewayClient(
        config=GatewayConfig(
            base_url="http://gateway.test",
            api_key=gateway_secret,
            provider_routes={provider_name: route_token},
        ),
        http_client=http,
    )

    try:
        catalog = await sdk.discover()
        assert [entry["name"] for entry in catalog] == [provider_name]
        assert catalog[0]["description"]["operations"] == ["generate_text"]
        assert catalog[0]["description"]["models"] == [
            {
                "name": "integration-model",
                "context_window": 4096,
                "operations": ["generate_text"],
                "capabilities": {"chat": True},
            },
            {
                "name": "vision-model",
                "context_window": None,
                "operations": ["analyze_vision"],
                "capabilities": {"vision_input": True},
            },
        ]

        manifest = await sdk.describe(provider_name)
        models = await sdk.list_models(provider_name)
        provider_operations = await sdk.list_operations(provider_name)
        payload = {"new_input_field": {"nested": [1, 2, 3]}}
        result = await sdk.execute(
            provider=provider_name,
            operation="generate_text",
            model="integration-model",
            payload=payload,
        )
        vision_result = await sdk.execute(
            provider=provider_name,
            operation="analyze_vision",
            model="vision-model",
            payload={"image": "opaque"},
        )
        assert manifest["display_name"] == provider_name
        assert models == catalog[0]["description"]["models"]
        assert provider_operations == ["generate_text"]
        assert result["output"] == {"model": "integration-model", "payload": payload}
        assert vision_result["output"] == {
            "model": "vision-model",
            "vision": {"image": "opaque"},
        }
        with pytest.raises(GatewaySDKError) as unsupported:
            await sdk.execute(
                provider=provider_name,
                operation="generate_text",
                model="vision-model",
                payload={"messages": []},
            )
        assert unsupported.value.category == "unsupported_capability"

        # Existing SDK consumers configured with a token still use the legacy route.
        legacy_catalog = await legacy_sdk.discover()
        legacy_result = await legacy_sdk.execute(
            provider=provider_name,
            operation="generate_text",
            model="integration-model",
            payload={"legacy": True},
        )
        assert legacy_catalog[0]["name"] == provider_name.lower()
        assert legacy_result["output"]["payload"] == {"legacy": True}

        # Unknown names are uniformly rejected, without exposing the private route.
        with pytest.raises(GatewaySDKError) as unknown:
            await sdk.describe("not a registered provider")
        assert unknown.value.http_status == 404
        assert unknown.value.response["error"]["message"] == "unknown route"

        # A known but disabled provider is equally unavailable by name.
        routes.set_disabled(provider_slug, True)
        with pytest.raises(GatewaySDKError) as disabled:
            await sdk.execute(
                provider=provider_name,
                operation="generate_text",
                model="integration-model",
                payload={"must_not_run": True},
            )
        assert disabled.value.http_status == 404
        assert disabled.value.response["error"] == unknown.value.response["error"]
        assert await sdk.discover() == []
    finally:
        await http.aclose()

    rendered_responses = json.dumps(
        [
            catalog,
            manifest,
            result,
            legacy_catalog,
            legacy_result,
            unknown.value.response,
            disabled.value.response,
        ]
    )
    assert route_token not in rendered_responses
    assert provider_slug not in rendered_responses
    assert gateway_secret not in rendered_responses
    assert route_token not in caplog.text
    assert provider_slug not in caplog.text
    assert gateway_secret not in caplog.text

    name_requests = [
        headers for _method, _path, headers in observed_requests if b"x-provider-name" in headers
    ]
    legacy_requests = [
        headers for _method, _path, headers in observed_requests if b"x-route-token" in headers
    ]
    assert name_requests
    assert all(b"x-route-token" not in headers for headers in name_requests)
    assert legacy_requests
    assert all(headers[b"x-route-token"] == route_token.encode() for headers in legacy_requests)
