"""Syntx AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & UNIVERSAL_PROVIDER_SPEC_AND_BLUEPRINT.md
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Enforces strict contract validation on input payloads (messages, vision fields).
- Enforces Non-Vision Model Protection (unsupported_capability) before touching network.
- Absolute zero leakage: no credentials, internal paths, or tokens in output or errors.
"""

from __future__ import annotations

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
from providers.syntx import _core


def _validate_messages_payload(payload: dict[str, Any]) -> str | None:
    """Validate messages schema strictly matching canonical text contract."""
    # Disallow unsupported extra payload fields like files in text generation
    if "files" in payload:
        return "payload contains unsupported field 'files'"

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


def _format_conversation(messages: list[dict[str, str]]) -> str:
    """Assemble multi-turn messages into single text prompt."""
    if len(messages) == 1:
        return messages[0]["content"]

    history_lines: list[str] = []
    for m in messages[:-1]:
        history_lines.append(f"{m['role']}: {m['content']}")

    last_msg = messages[-1]
    return (
        "Previous conversation:\n"
        + "\n\n".join(history_lines)
        + f"\n\nCurrent request:\n{last_msg['role']}: {last_msg['content']}"
    )


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
    """generate_text facade handler."""
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
                "Syntx operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    err_msg = _validate_messages_payload(context.payload)
    if err_msg:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err_msg),
        )

    messages: list[dict[str, str]] = context.payload["messages"]
    prompt = _format_conversation(messages)
    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        reply = _core.ask(
            model=context.model,
            prompt=prompt,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={"text": reply["text"], "finish_reason": reply.get("finish_reason", "stop")},
            usage=Usage(
                input_tokens=reply.get("input_tokens"),
                output_tokens=reply.get("output_tokens"),
                units=1,
            ),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected internal failure during text generation",
            ),
        )


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """analyze_vision facade handler with non-vision model protection."""
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
                "Syntx operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    # 1. Non-vision model check (zero network touch)
    if not _core.is_vision_model(context.model):
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Model {context.model!r} does not support vision/image inputs",
            ),
        )

    # 2. Input validation
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

    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        reply = _core.ask(
            model=context.model,
            prompt=instruction,
            image_b64=image_b64,
            image_format=image_format,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={"text": reply["text"]},
            usage=Usage(
                input_tokens=reply.get("input_tokens"),
                output_tokens=reply.get("output_tokens"),
                units=1,
            ),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected internal failure during vision analysis",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
}
