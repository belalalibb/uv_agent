"""Configuration and connection settings for the Gateway Client."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayConfig:
    """Configuration parameters for connecting to the AI Gateway Service."""

    base_url: str = "http://127.0.0.1:8800"
    gateway_secret: str = ""
    secret_version: int = 1
    default_timeout: float = 60.0
    default_tenant_id: str = "default_platform_tenant"
    route_tokens: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        if not self.gateway_secret:
            # Fallback to GATEWAY_SECRET or GW_SECRET_CURRENT from env
            self.gateway_secret = (
                os.getenv("GATEWAY_SECRET")
                or os.getenv("GW_SECRET_CURRENT")
                or "live-demo-secret-key-bolla-zizo"
            )
        if not self.gateway_secret:
            raise ValueError("gateway_secret is required and must not be empty.")

    @classmethod
    def from_env(cls, **overrides: Any) -> GatewayConfig:
        """Create configuration automatically reading from environment variables."""
        # Try loading .env if dotenv is installed
        try:
            import dotenv
            dotenv.load_dotenv()
        except ImportError:
            pass

        base_url = os.getenv("GATEWAY_URL", "http://127.0.0.1:8800")
        secret = (
            os.getenv("GATEWAY_SECRET")
            or os.getenv("GW_SECRET_CURRENT")
            or "live-demo-secret-key-bolla-zizo"
        )
        version_raw = os.getenv("GATEWAY_SECRET_VERSION") or os.getenv("GW_SECRET_CURRENT_VERSION") or "1"
        secret_version = int(version_raw)
        timeout = float(os.getenv("GATEWAY_TIMEOUT", "60.0"))
        tenant_id = os.getenv("GATEWAY_TENANT_ID", "default_platform_tenant")

        # Discover pre-configured route tokens from environment
        tokens: dict[str, str] = {}
        for key, val in os.environ.items():
            if key.startswith("ROUTE_TOKEN_") and val:
                slug = key.replace("ROUTE_TOKEN_", "").lower()
                tokens[slug] = val

        data: dict[str, Any] = {
            "base_url": base_url,
            "gateway_secret": secret,
            "secret_version": secret_version,
            "default_timeout": timeout,
            "default_tenant_id": tenant_id,
            "route_tokens": tokens,
        }
        data.update(overrides)
        return cls(**data)

