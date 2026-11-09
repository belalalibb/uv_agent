"""LlamaCoder Together AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Handles generate_text and analyze_vision.
- Supports multi-turn messages, code/text attachments, and image screenshots.
- Rejects non-image binary media (such as audio) with clear BAD_REQUEST.
- Non-blocking execution using asyncio.to_thread for upstream network calls.
- Maps all upstream errors to canonical 12 ErrorCategory taxonomy.
- Absolute zero credential or internal leakage.
"""

from __future__ import annotations

import asyncio
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
from providers.llamacoder import _core

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
    """Translate Layer 1 failure shape into canonical wire error."""
    cat_str = str(exc.category).lower().strip()
    try:
        category = ErrorCategory(cat_str)
    except ValueError:
        category = ErrorCategory.NON_RETRYABLE_ERROR

    safe_msg = _SAFE_MESSAGES.get(category, "upstream call failed")
    if category is ErrorCategory.BAD_REQUEST and exc.message:
        # Include specific validation/format hints when safe
        safe_msg = exc.message

    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            safe_msg,
            retry_after_ms=exc.retry_after_ms if category is ErrorCategory.RATE_LIMITED else None,
            provider_code=exc.provider_code,
        ),
    )


def _validate_messages_payload(payload: dict[str, Any]) -> str | None:
    """Validate messages schema for text generation."""
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


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade handler for LlamaCoder."""
    if context.operation != GatewayOperation.GENERATE_TEXT:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler generate_text cannot serve operation {context.operation!r}",
            ),
        )

    if context.credential_mode is not CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "LlamaCoder operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    err_msg = _validate_messages_payload(context.payload)
    if err_msg:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err_msg),
        )

    messages: list[dict[str, str]] = list(context.payload["messages"])
    files_payload = context.payload.get("files")
    screenshot_token: str | None = context.payload.get("screenshot_token")
    timeout_s = max(1, context.timeout_ms // 1000)
    # Ensure heavy reasoning models are never prematurely cut off by low default client timeouts
    if context.model.lower() in ("kimi-k3", "glm-5.3", "glm-5.3-flash", "qwen-3.7-max") and timeout_s < 180:
        timeout_s = max(timeout_s, 180)

    try:
        reply = await asyncio.to_thread(
            _core.ask,
            model=context.model,
            messages=messages,
            files=files_payload,
            screenshot_token=screenshot_token,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "text": reply["text"],
                "finish_reason": "stop",
                "chat_id": reply.get("chat_id"),
                "title": reply.get("title"),
            },
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                f"Unexpected internal failure during text generation: {exc}",
            ),
        )


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """analyze_vision facade handler for LlamaCoder."""
    if context.operation != GatewayOperation.ANALYZE_VISION:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler analyze_vision cannot serve operation {context.operation!r}",
            ),
        )

    if context.credential_mode is not CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "LlamaCoder operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    payload = context.payload
    image_b64 = payload.get("image_b64")
    image_format = payload.get("image_format", "png")
    instruction = payload.get("instruction", "Analyze this image and describe its UI structure and code components in detail.")

    if not isinstance(image_b64, str) or not image_b64:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.image_b64 is required and must be a string"),
        )

    try:
        img_bytes = base64.b64decode(image_b64)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.image_b64 is not valid base64"),
        )

    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        reply = await asyncio.to_thread(
            _core.analyze_vision,
            model=context.model,
            image_bytes=img_bytes,
            image_format=image_format,
            instruction=instruction,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "text": reply["text"],
                "chat_id": reply.get("chat_id"),
            },
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                f"Unexpected internal failure during vision analysis: {exc}",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
}
