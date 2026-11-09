"""Freebuff Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Handles generate_text with support for multi-turn messages and thread_id session continuity.
- Non-blocking execution using asyncio.to_thread for upstream network calls.
- Maps all upstream errors to canonical 12 ErrorCategory taxonomy.
- Absolute zero credential or internal leakage.
"""

from __future__ import annotations

import asyncio
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
from providers.freebuff import _core


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


def _validate_messages_payload(payload: dict[str, Any]) -> str | None:
    """Validate canonical messages payload structure."""
    if not isinstance(payload, dict):
        return "payload must be a dict"

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return "payload.messages must be a non-empty list"

    allowed_roles = {"system", "user", "assistant"}
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return f"payload.messages[{idx}] must be a dict"
        role = msg.get("role")
        content = msg.get("content")
        if role not in allowed_roles:
            return f"payload.messages[{idx}].role must be one of {sorted(allowed_roles)}"
        if not isinstance(content, str) or not content:
            return f"payload.messages[{idx}].content must be a non-empty string"

    return None


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade handler for Freebuff."""
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
                "Freebuff operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    err_msg = _validate_messages_payload(context.payload)
    if err_msg:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err_msg),
        )

    messages: list[dict[str, str]] = list(context.payload["messages"])
    model: str = context.payload.get("model", "glm-5.3-flash")
    session_id: str | None = context.payload.get("session_id")
    timeout_s: int = max(1, context.timeout_ms // 1000)

    try:
        # Asynchronous dispatch to thread to prevent blocking event loop
        reply = await asyncio.to_thread(
            _core.generate_text,
            model=model,
            messages=messages,
            timeout=timeout_s,
            thread_id=session_id,
        )

        output_dict: dict[str, Any] = {
            "text": reply["content"],
            "finish_reason": "stop",
            "model": reply.get("model", model),
        }

        # Include reasoning if present
        if reply.get("reasoning"):
            output_dict["reasoning"] = reply["reasoning"]
        if reply.get("thread_id"):
            output_dict["session_id"] = reply["thread_id"]

        return FacadeResult(
            succeeded=True,
            output=output_dict,
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                f"Unexpected internal failure during Freebuff text generation: {exc}",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
}
