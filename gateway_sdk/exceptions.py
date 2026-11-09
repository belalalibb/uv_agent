"""Small, open-ended error types for transport and Gateway failures."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class GatewaySDKError(Exception):
    """A Gateway-reported or HTTP-level failure without a closed category enum."""

    def __init__(
        self,
        message: str,
        *,
        category: str | None = None,
        retryable: bool | None = None,
        retry_after_ms: int | None = None,
        provider_code: str | None = None,
        http_status: int | None = None,
        response: Mapping[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code
        self.http_status = http_status
        self.response = dict(response or {})
        prefix = f"[{category}] " if category else ""
        super().__init__(f"{prefix}{message}")

    @classmethod
    def from_response(
        cls,
        response: Mapping[str, Any],
        *,
        http_status: int | None = None,
    ) -> GatewaySDKError:
        error = response.get("error")
        error_data = error if isinstance(error, Mapping) else {}
        return cls(
            str(error_data.get("message") or "Gateway request failed"),
            category=_optional_str(error_data.get("category")),
            retryable=_optional_bool(error_data.get("retryable")),
            retry_after_ms=_optional_int(error_data.get("retry_after_ms")),
            provider_code=_optional_str(error_data.get("provider_code")),
            http_status=http_status,
            response=response,
        )


class GatewayTransportError(GatewaySDKError):
    """The SDK could not complete an HTTP exchange with the Gateway."""


class GatewayProtocolError(GatewaySDKError):
    """The Gateway returned a body that was not a JSON object."""


class ProviderNotConfiguredError(GatewaySDKError):
    """Legacy exception type retained for callers of older SDK releases."""


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
