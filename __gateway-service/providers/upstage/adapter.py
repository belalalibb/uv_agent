"""Upstage AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Enforces strict contract validation on input payloads (messages schema).
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
from providers.upstage import _core


def _validate_messages_payload(payload: dict[str, Any]) -> str | None:
    """Validate messages schema strictly matching canonical text contract."""
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
        category = ErrorCategory(exc.category.lower())
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
    """Handle canonical text generation request."""
    # 1. Validate credential mode
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "Upstage provider requires platform credential mode with no caller credentials",
            ),
        )

    # 2. Validate input schema
    validation_err = _validate_messages_payload(context.payload)
    if validation_err:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"Invalid request payload: {validation_err}",
            ),
        )

    # 3. Model mapping
    model_name = context.model or "auto"

    # 4. Invoke Layer 1
    timeout_s = (context.timeout_ms / 1000.0) if context.timeout_ms else 60.0

    try:
        result = _core.ask(
            messages=context.payload["messages"],
            model=model_name,
            timeout_s=timeout_s,
        )

        usage_dict = result.get("usage", {})
        usage = Usage(
            input_tokens=usage_dict.get("prompt_tokens"),
            output_tokens=usage_dict.get("completion_tokens"),
            units=1,
        )

        return FacadeResult(
            succeeded=True,
            output={
                "text": result["text"],
                "finish_reason": "stop",
            },
            usage=usage,
        )

    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "upstream call failed unexpectedly",
            ),
        )


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """Handle canonical vision analysis request."""
    # 1. Operation check
    if context.operation != GatewayOperation.ANALYZE_VISION:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler analyze_vision cannot serve operation {context.operation!r}",
            ),
        )

    # 2. Validate credential mode
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "Upstage provider requires platform credential mode with no caller credentials",
            ),
        )

    # 3. Model mapping & Non-vision model check (zero network touch)
    model_name = context.model or "solar-docvision"
    if not _core.is_vision_model(model_name):
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Model {model_name!r} does not support vision/image inputs",
            ),
        )

    # 4. Input validation
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
            error=make_error(ErrorCategory.BAD_REQUEST, "invalid base64 image data"),
        )

    timeout_s = (context.timeout_ms / 1000.0) if context.timeout_ms else 60.0
    filename = f"image.{image_format}"
    mime_type = f"image/{image_format}"

    try:
        file_id = _core.upload_file_bytes(
            data=image_bytes,
            filename=filename,
            mime_type=mime_type,
            timeout_s=timeout_s,
        )
        result = _core.ask(
            messages=instruction,
            model=model_name,
            timeout_s=timeout_s,
            file_ids=[file_id],
            files_meta=[{"id": file_id, "name": filename}],
        )

        usage_dict = result.get("usage", {})
        usage = Usage(
            input_tokens=usage_dict.get("prompt_tokens"),
            output_tokens=usage_dict.get("completion_tokens"),
            units=1,
        )

        return FacadeResult(
            succeeded=True,
            output={
                "text": result["text"],
            },
            usage=usage,
        )

    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "upstream call failed unexpectedly during vision analysis",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
}
