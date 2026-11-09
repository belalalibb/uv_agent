"""Configuration for the Gateway SDK.

``provider_routes`` temporarily bridges Gateway versions that require
``X-Route-Token``. Current Gateway versions resolve public provider names
server-side, so callers should not depend on this compatibility field.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def normalize_provider_name(name: str) -> str:
    """Normalize a public provider alias without exposing its route token."""
    return name.strip().casefold()


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Client settings. Secret and transitional route values are hidden in repr."""

    base_url: str
    api_key: str = field(repr=False)
    api_key_version: int = 1
    provider_routes: Mapping[str, str] = field(default_factory=dict, repr=False)
    default_tenant_id: str = "default_platform_tenant"
    default_timeout_ms: int = 60_000
    http_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP or HTTPS URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain user information")
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ValueError("api_key is required")
        if self.api_key_version < 1:
            raise ValueError("api_key_version must be a positive integer")
        if self.default_timeout_ms < 1:
            raise ValueError("default_timeout_ms must be positive")
        if self.http_timeout_seconds is not None and self.http_timeout_seconds <= 0:
            raise ValueError("http_timeout_seconds must be positive")

        normalized: dict[str, str] = {}
        for name, route_token in self.provider_routes.items():
            alias = normalize_provider_name(name)
            token = route_token.strip()
            if not alias or not token:
                raise ValueError(
                    "provider route entries must have non-empty names and values"
                )
            if alias in normalized:
                raise ValueError(f"duplicate provider alias: {alias!r}")
            normalized[alias] = token

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "provider_routes", normalized)

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_version: int | None = None,
        provider_routes: Mapping[str, str] | None = None,
        default_tenant_id: str | None = None,
        default_timeout_ms: int | None = None,
        http_timeout_seconds: float | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> GatewayConfig:
        """Build settings from explicit arguments and environment variables.

        No secret or provider token is supplied as a built-in default. The
        environment route mapping exists only to bridge older Gateway servers.
        """
        env = os.environ if environ is None else environ
        key = (
            api_key
            or env.get("GATEWAY_API_KEY")
            or env.get("GATEWAY_SECRET")
            or env.get("GW_SECRET_CURRENT")
        )
        if not key:
            raise ValueError("api_key is required (pass it or set GATEWAY_API_KEY)")

        version_value: int
        if api_key_version is not None:
            version_value = api_key_version
        else:
            raw_version = (
                env.get("GATEWAY_API_KEY_VERSION")
                or env.get("GATEWAY_SECRET_VERSION")
                or env.get("GW_SECRET_CURRENT_VERSION")
                or "1"
            )
            try:
                version_value = int(raw_version)
            except (TypeError, ValueError) as exc:
                raise ValueError("gateway API key version must be an integer") from exc

        routes: dict[str, str] = {}
        for env_name, value in env.items():
            if env_name.startswith("ROUTE_TOKEN_") and value.strip():
                alias = normalize_provider_name(
                    env_name[len("ROUTE_TOKEN_") :].replace("__", "-")
                )
                routes[alias] = value.strip()
        if provider_routes is not None:
            for name, route_token in provider_routes.items():
                routes[normalize_provider_name(name)] = route_token

        raw_timeout = env.get("GATEWAY_TIMEOUT_MS", "60000")
        if default_timeout_ms is None:
            try:
                timeout_ms = int(raw_timeout)
            except (TypeError, ValueError) as exc:
                raise ValueError("GATEWAY_TIMEOUT_MS must be an integer") from exc
        else:
            timeout_ms = default_timeout_ms

        configured_url = base_url or env.get("GATEWAY_URL", "http://127.0.0.1:8800")
        configured_tenant = default_tenant_id or env.get(
            "GATEWAY_TENANT_ID", "default_platform_tenant"
        )
        return cls(
            base_url=configured_url,
            api_key=key,
            api_key_version=version_value,
            provider_routes=routes,
            default_tenant_id=configured_tenant,
            default_timeout_ms=timeout_ms,
            http_timeout_seconds=http_timeout_seconds,
        )
