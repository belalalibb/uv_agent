"""TinyFish AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Handles generate_text and analyze_vision operations.
- Enforces strict contract validation on input payloads.
- Absolute zero leakage: no credentials, internal paths, or tokens in output or errors.
"""

from __future__ import annotations

import base64
import math
from typing import Any

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers.tinyfish import _core


def _validate_messages_payload(payload: dict[str, Any]) -> str | None:
    """Validate messages schema strictly matching canonical text contract."""
    temp = payload.get("temperature")
    if temp is not None:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)) or math.isnan(temp):
            return "temperature must be a finite number"

    max_tok = payload.get("max_tokens")
    if max_tok is not None:
        if isinstance(max_tok, bool) or not isinstance(max_tok, int) or max_tok <= 0:
            return "max_tokens must be a positive integer"

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return "payload.messages is required and must be a non-empty list"

    allowed_roles = {"system", "user", "assistant"}
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return f"payload.messages[{idx}] must be a dict"
        extra_keys = set(msg) - {"role", "content"}
        if extra_keys:
            return f"payload.messages[{idx}] contains extra forbidden keys {sorted(extra_keys)}"
        role = msg.get("role")
        content = msg.get("content")
        if role not in allowed_roles:
            return f"payload.messages[{idx}].role must be one of {sorted(allowed_roles)}"
        if not isinstance(content, str) or not content:
            return f"payload.messages[{idx}].content must be a non-empty string"

    return None


_SAFE_MESSAGES: dict[ErrorCategory, str] = {
    ErrorCategory.AUTH_EXPIRED: "upstream authentication expired",
    ErrorCategory.INVALID_CREDENTIAL: "upstream credential invalid",
    ErrorCategory.RATE_LIMITED: "upstream rate limit reached",
    ErrorCategory.QUOTA_EXCEEDED: "upstream quota exceeded",
    ErrorCategory.MODEL_UNAVAILABLE: "upstream model unavailable",
    ErrorCategory.PROVIDER_UNAVAILABLE: "upstream provider unavailable",
    ErrorCategory.UNSUPPORTED_CAPABILITY: "unsupported capability",
    ErrorCategory.BAD_REQUEST: "bad request payload",
    ErrorCategory.CONTENT_REJECTED: "content rejected by upstream policy",
    ErrorCategory.TIMEOUT: "upstream call timed out",
    ErrorCategory.RETRYABLE_SERVER_ERROR: "upstream server error",
    ErrorCategory.NON_RETRYABLE_ERROR: "upstream call failed",
}


def _translate_upstream_failure(exc: _core.UpstreamFailure) -> FacadeResult:
    """Translate Layer 1 failure shape into canonical wire error using safe fixed messages only."""
    try:
        category = ErrorCategory(exc.category)
    except ValueError:
        category = ErrorCategory.NON_RETRYABLE_ERROR

    safe_msg = _SAFE_MESSAGES.get(category, "upstream call failed")
    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            safe_msg,
            retry_after_ms=exc.retry_after_ms if category is ErrorCategory.RATE_LIMITED else None,
            provider_code=exc.provider_code,
        ),
    )


async def generate_text(context: ProviderContext) -> FacadeResult:
    """Handle canonical text generation/reasoning request via TinyFish."""
    if context.operation != GatewayOperation.GENERATE_TEXT:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler generate_text cannot serve operation {context.operation!r}",
            ),
        )

    # 1. Validate credential mode
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "TinyFish AI requires platform credential mode without caller-supplied value",
            ),
        )

    # 2. Validate payload schema
    err = _validate_messages_payload(context.payload)
    if err:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err),
        )

    messages = context.payload["messages"]

    # 3. Call Layer 1 internal engine
    try:
        text, finish_reason, usage_dict, latency_ms = _core.ask(
            model=context.model,
            messages=messages,
            session_id=context.request_id,
            timeout_ms=context.timeout_ms,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "text": text,
                "finish_reason": finish_reason,
            },
            usage=Usage(
                input_tokens=usage_dict.get("input_tokens"),
                output_tokens=usage_dict.get("output_tokens"),
                units=usage_dict.get("units", 1),
            ),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "upstream call failed unexpectedly",
            ),
        )


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """Handle canonical vision analysis request via TinyFish."""
    if context.operation != GatewayOperation.ANALYZE_VISION:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler analyze_vision cannot serve operation {context.operation!r}",
            ),
        )

    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "TinyFish AI requires platform credential mode without caller-supplied value",
            ),
        )

    image_b64 = context.payload.get("image_b64")
    instruction = context.payload.get("instruction")
    image_format = context.payload.get("image_format", "png")

    if not isinstance(image_b64, str) or not image_b64:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.image_b64 is required and must be a string"),
        )
    if not isinstance(instruction, str) or not instruction:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.instruction is required and must be a string"),
        )

    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.image_b64 is not valid base64"),
        )

    try:
        text, usage_dict, latency_ms = _core.analyze_vision(
            model=context.model,
            image_bytes=image_bytes,
            image_format=image_format,
            instruction=instruction,
            session_id=context.request_id,
            timeout_ms=context.timeout_ms,
        )
        return FacadeResult(
            succeeded=True,
            output={"text": text},
            usage=Usage(
                input_tokens=usage_dict.get("input_tokens"),
                output_tokens=usage_dict.get("output_tokens"),
                units=usage_dict.get("units", 1),
            ),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected failure during vision analysis",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
}
