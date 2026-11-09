"""Discovery calls.

New Gateways expose an authenticated provider catalog. For older deployments,
``discover`` can still enumerate temporary locally configured aliases and fetch
their manifests using route tokens.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .exceptions import GatewayProtocolError
from .models import JSONObject

RequestJSON = Callable[..., Awaitable[JSONObject]]


async def describe_provider(request_json: RequestJSON, provider: str) -> JSONObject:
    return await request_json("GET", "/v1/describe", provider=provider)


async def list_provider_models(request_json: RequestJSON, provider: str) -> list[Any]:
    """Return raw Gateway model rows, including effective support metadata.

    The SDK intentionally does not parse or normalize model fields. Gateway
    resolves Provider defaults and per-model overrides before returning rows.
    """
    response = await request_json("GET", "/v1/models", provider=provider)
    models = response.get("models", [])
    return models if isinstance(models, list) else []


async def list_provider_operations(
    request_json: RequestJSON,
    provider: str,
) -> list[Any]:
    """Return the Provider-level default operations from the live manifest.

    This method retains its provider-only signature. Per-model effective
    operations are carried on each raw model row returned by ``list_models``.
    """
    description = await describe_provider(request_json, provider)
    operations = description.get("operations", [])
    return operations if isinstance(operations, list) else []


async def discover_gateway_providers(request_json: RequestJSON) -> list[JSONObject]:
    """Read the Gateway-owned catalog without local provider/token lists."""

    response = await request_json("GET", "/v1/providers")
    providers = response.get("providers")
    if not isinstance(providers, list) or any(
        not isinstance(item, dict) for item in providers
    ):
        raise GatewayProtocolError("Gateway provider catalog has an invalid shape")
    return providers


async def discover_providers(
    request_json: RequestJSON,
    configured_provider_names: list[str],
) -> list[JSONObject]:
    """Discover configured providers while preserving each raw manifest."""
    manifests = await asyncio.gather(
        *(describe_provider(request_json, name) for name in configured_provider_names)
    )
    return [
        {"name": name, "description": manifest}
        for name, manifest in zip(configured_provider_names, manifests, strict=True)
    ]
