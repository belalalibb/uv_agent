"""Asynchronous, provider-name-oriented Gateway client."""

from __future__ import annotations

from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self

import httpx

from . import discovery, execution
from .config import GatewayConfig, normalize_provider_name
from .exceptions import (
    GatewayProtocolError,
    GatewaySDKError,
    GatewayTransportError,
)
from .models import JSONObject


class GatewayClient:
    """Thin async client that forwards generic operations and JSON payloads.

    Public methods accept provider names only. If a legacy
    ``ROUTE_TOKEN_<PROVIDER>`` mapping is configured, it is used for older
    Gateways; otherwise the name is sent to the Gateway's provider resolver.
    Route tokens stay private to the compatibility transport and are never
    returned from discovery or included in request bodies or URLs.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        api_key_version: int | None = None,
        provider_routes: Mapping[str, str] | None = None,
        default_tenant_id: str | None = None,
        default_timeout_ms: int | None = None,
        http_client: httpx.AsyncClient | None = None,
        config: GatewayConfig | None = None,
    ) -> None:
        if config is not None and any(
            value is not None
            for value in (
                base_url,
                api_key,
                api_key_version,
                provider_routes,
                default_tenant_id,
                default_timeout_ms,
            )
        ):
            raise ValueError("pass either config or individual settings, not both")
        self.config = config or GatewayConfig.from_env(
            base_url=base_url,
            api_key=api_key,
            api_key_version=api_key_version,
            provider_routes=provider_routes,
            default_tenant_id=default_tenant_id,
            default_timeout_ms=default_timeout_ms,
        )
        timeout = self.config.http_timeout_seconds or max(
            5.0, self.config.default_timeout_ms / 1000.0 + 5.0
        )
        self._owns_http_client = http_client is None
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    def _provider_selector(self, provider: str) -> tuple[str, str]:
        provider_name = provider.strip()
        if not provider_name:
            raise ValueError("provider must be a non-empty name")
        route_token = self.config.provider_routes.get(
            normalize_provider_name(provider_name)
        )
        if route_token:
            return "X-Route-Token", route_token
        return "X-Provider-Name", provider_name

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        provider: str | None = None,
        **kwargs: Any,
    ) -> JSONObject:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Gateway-Secret"] = self.config.api_key
        headers["X-Gateway-Secret-Version"] = str(self.config.api_key_version)
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        if provider is not None:
            # Prefer the Gateway-owned resolver; use the token selector only
            # when bridging a legacy deployment with a local route mapping.
            header_name, selector = self._provider_selector(provider)
            headers[header_name] = selector

        try:
            response = await self._http.request(
                method,
                f"{self.config.base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise GatewayTransportError("Gateway request timed out") from exc
        except httpx.RequestError as exc:
            raise GatewayTransportError("Could not connect to the Gateway") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise GatewayProtocolError(
                "Gateway response was not valid JSON",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise GatewayProtocolError(
                "Gateway response must be a JSON object",
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            raise GatewaySDKError.from_response(data, http_status=response.status_code)
        return data

    async def discover(self) -> list[JSONObject]:
        """Return the Gateway catalog, or bridge configured legacy aliases."""
        if not self.config.provider_routes:
            return await discovery.discover_gateway_providers(self._request_json)
        names = sorted(self.config.provider_routes)
        return await discovery.discover_providers(self._request_json, names)

    async def describe(self, provider: str) -> JSONObject:
        return await discovery.describe_provider(self._request_json, provider)

    async def list_models(self, provider: str) -> list[Any]:
        """Return raw models with Gateway-resolved effective support fields."""
        return await discovery.list_provider_models(self._request_json, provider)

    async def list_operations(self, provider: str) -> list[Any]:
        """Return provider-level defaults; model-specific support is in list_models()."""
        return await discovery.list_provider_operations(self._request_json, provider)

    async def execute(
        self,
        *,
        provider: str,
        operation: str,
        model: str,
        payload: Mapping[str, Any],
        request_id: str | None = None,
        tenant_id: str | None = None,
        credential_mode: str = "platform",
        credential_value: str | None = None,
        timeout_ms: int | None = None,
    ) -> JSONObject:
        """Execute any string operation; payload is passed through generically."""
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation must be a non-empty string")
        return await execution.execute_operation(
            self._request_json,
            self.config,
            provider=provider,
            operation=operation,
            model=model,
            payload=payload,
            request_id=request_id,
            tenant_id=tenant_id,
            credential_mode=credential_mode,
            credential_value=credential_value,
            timeout_ms=timeout_ms,
        )

    async def check_gateway_health(self) -> JSONObject:
        """Check Gateway process liveness via the unauthenticated /healthz path."""
        try:
            response = await self._http.get(f"{self.config.base_url}/healthz")
        except httpx.TimeoutException as exc:
            raise GatewayTransportError("Gateway health check timed out") from exc
        except httpx.RequestError as exc:
            raise GatewayTransportError(
                "Could not reach Gateway health endpoint"
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise GatewayProtocolError(
                "Gateway health response was not valid JSON",
                http_status=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise GatewayProtocolError(
                "Gateway health response must be a JSON object",
                http_status=response.status_code,
            )
        if response.status_code >= 400:
            raise GatewaySDKError.from_response(data, http_status=response.status_code)
        return data

    async def check_provider_health(self, provider: str) -> JSONObject:
        return await self._request_json("GET", "/v1/health", provider=provider)


# A short alias for applications that prefer ``Gateway(...)``.
Gateway = GatewayClient
