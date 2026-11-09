# -*- coding: utf-8 -*-
"""Layer 2 — RunPod Console Assistant Facade Adapter.

The only module the gateway sees.
Translates ProviderContext into canonical FacadeResults for:
1. GatewayOperation.GENERATE_TEXT
2. GatewayOperation.ANALYZE_VISION
"""

from __future__ import annotations

from typing import Any

from gateway.contracts import (
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers.runpod_console._upstream import UpstreamReply, call_runpod_assistant

_ALLOWED_TEXT_PAYLOAD_KEYS = frozenset({"messages", "temperature", "max_tokens"})
_ALLOWED_VISION_PAYLOAD_KEYS = frozenset({"image_b64", "instruction", "image_format"})

_HTTP_STATUS_MAP: dict[int, ErrorCategory] = {
    401: ErrorCategory.INVALID_CREDENTIAL,
    403: ErrorCategory.INVALID_CREDENTIAL,
    404: ErrorCategory.MODEL_UNAVAILABLE,
    429: ErrorCategory.RATE_LIMITED,
    400: ErrorCategory.BAD_REQUEST,
    413: ErrorCategory.BAD_REQUEST,
    422: ErrorCategory.BAD_REQUEST,
    500: ErrorCategory.RETRYABLE_SERVER_ERROR,
    502: ErrorCategory.RETRYABLE_SERVER_ERROR,
    503: ErrorCategory.RETRYABLE_SERVER_ERROR,
    504: ErrorCategory.RETRYABLE_SERVER_ERROR,
}


def _validate_text_payload(payload: dict[str, Any]) -> FacadeResult | None:
    """Canonical generate_text schema policing; returns a bad_request FacadeResult or None."""
    if not isinstance(payload, dict):
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload must be a JSON object"),
        )

    extra = set(payload.keys()) - _ALLOWED_TEXT_PAYLOAD_KEYS
    if extra:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"payload contains disallowed keys: {sorted(extra)}",
            ),
        )

    messages = payload.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "messages must be a non-empty list of message objects",
            ),
        )

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    f"messages[{i}] must be a JSON object",
                ),
            )
        role = msg.get("role")
        if not isinstance(role, str) or not role:
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    f"messages[{i}].role must be a non-empty string",
                ),
            )
        if "content" not in msg:
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    f"messages[{i}] missing required 'content' field",
                ),
            )

    return None


def _validate_vision_payload(payload: dict[str, Any]) -> FacadeResult | None:
    """Canonical analyze_vision schema policing."""
    if not isinstance(payload, dict):
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload must be a JSON object"),
        )

    extra = set(payload.keys()) - _ALLOWED_VISION_PAYLOAD_KEYS
    if extra:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"payload contains disallowed keys: {sorted(extra)}",
            ),
        )

    image_b64 = payload.get("image_b64")
    instruction = payload.get("instruction")

    if not isinstance(image_b64, str) or not image_b64:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.image_b64 is required and must be a non-empty string"),
        )
    if not isinstance(instruction, str) or not instruction:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.instruction is required and must be a non-empty string"),
        )

    return None


def _translate_reply(reply: UpstreamReply) -> FacadeResult:
    """Translate Layer 1 internal reply shape to canonical FacadeResult."""
    if reply.ok:
        return FacadeResult(
            succeeded=True,
            output={
                "text": reply.text,
                "finish_reason": reply.finish_reason or "stop",
            },
            usage=Usage(
                input_tokens=reply.usage.get("prompt_tokens"),
                output_tokens=reply.usage.get("completion_tokens"),
                units=1,
            ),
        )

    fail_kind = reply.fail_kind
    if fail_kind == "no_session":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "No active RunPod session credentials configured",
                provider_code=reply.error_code,
            ),
        )
    if fail_kind == "auth_expired":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.AUTH_EXPIRED,
                "RunPod Clerk session or token expired and cannot be refreshed",
                provider_code=reply.error_code,
            ),
        )
    if fail_kind == "timeout":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.TIMEOUT,
                "Upstream call timed out",
                retryable=True,
            ),
        )
    if fail_kind == "network":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.RETRYABLE_SERVER_ERROR,
                "Network transport failure communicating with RunPod",
                retryable=True,
                provider_code=reply.error_code,
            ),
        )
    if fail_kind == "http":
        status = reply.http_status or 500
        category = _HTTP_STATUS_MAP.get(status, ErrorCategory.NON_RETRYABLE_ERROR)
        retryable = category in (
            ErrorCategory.RATE_LIMITED,
            ErrorCategory.RETRYABLE_SERVER_ERROR,
        )
        return FacadeResult(
            succeeded=False,
            error=make_error(
                category,
                f"Upstream returned HTTP {status}",
                retryable=retryable,
                retry_after_ms=reply.retry_after_ms,
                provider_code=f"HTTP_{status}",
            ),
        )

    return FacadeResult(
        succeeded=False,
        error=make_error(
            ErrorCategory.NON_RETRYABLE_ERROR,
            "Unknown upstream failure",
        ),
    )


async def generate_text(context: ProviderContext) -> FacadeResult:
    """Handle GatewayOperation.GENERATE_TEXT for RunPod Console Assistant."""
    err = _validate_text_payload(context.payload)
    if err is not None:
        return err

    messages = context.payload["messages"]
    reply = await call_runpod_assistant(
        messages=messages,
        timeout_ms=context.timeout_ms,
    )
    return _translate_reply(reply)


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """Handle GatewayOperation.ANALYZE_VISION for RunPod Console Assistant."""
    err = _validate_vision_payload(context.payload)
    if err is not None:
        return err

    image_b64 = context.payload["image_b64"]
    instruction = context.payload["instruction"]
    image_format = context.payload.get("image_format", "png")

    file_obj = {
        "filename": f"image.{image_format}",
        "mediaType": f"image/{image_format}",
        "url": f"data:image/{image_format};base64,{image_b64}",
    }

    reply = await call_runpod_assistant(
        messages=[{"role": "user", "content": instruction}],
        files=[file_obj],
        timeout_ms=context.timeout_ms,
    )
    return _translate_reply(reply)


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
}
