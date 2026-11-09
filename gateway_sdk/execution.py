"""Generic operation execution; no provider or operation enums are defined."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .config import GatewayConfig
from .exceptions import GatewaySDKError
from .models import JSONObject

RequestJSON = Callable[..., Awaitable[JSONObject]]


def build_envelope(
    config: GatewayConfig,
    *,
    operation: str,
    model: str,
    payload: Mapping[str, Any],
    request_id: str | None = None,
    tenant_id: str | None = None,
    credential_mode: str = "platform",
    credential_value: str | None = None,
    timeout_ms: int | None = None,
) -> JSONObject:
    """Build only the current wire envelope; operation payload stays opaque."""
    credential: JSONObject = {"mode": credential_mode}
    if credential_value is not None:
        credential["value"] = credential_value

    return {
        "operation": operation,
        "model": model,
        "request_id": request_id or f"req_{uuid.uuid4().hex}",
        "tenant_id": tenant_id or config.default_tenant_id,
        "credential": credential,
        "payload": dict(payload),
        "timeout_ms": timeout_ms
        if timeout_ms is not None
        else config.default_timeout_ms,
    }


async def execute_operation(
    request_json: RequestJSON,
    config: GatewayConfig,
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
    envelope = build_envelope(
        config,
        operation=operation,
        model=model,
        payload=payload,
        request_id=request_id,
        tenant_id=tenant_id,
        credential_mode=credential_mode,
        credential_value=credential_value,
        timeout_ms=timeout_ms,
    )
    effective_timeout = envelope["timeout_ms"]
    http_timeout = max(5.0, float(effective_timeout) / 1000.0 + 5.0)
    response = await request_json(
        "POST",
        "/v1/execute",
        provider=provider,
        json=envelope,
        timeout=http_timeout,
    )
    if response.get("succeeded") is False:
        raise GatewaySDKError.from_response(response, http_status=200)
    return response
