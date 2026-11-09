"""IvyCraft AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Enforces strict contract validation on input payloads for generate_text, generate_image, synthesize_speech.
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
from providers.ivycraft import _core


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


def _validate_image_payload(payload: dict[str, Any]) -> str | None:
    """Validate image generation payload schema."""
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return "payload.prompt is required and must be a non-empty string"

    size = payload.get("size")
    if size is not None and not isinstance(size, str):
        return "payload.size must be a string"

    count = payload.get("count")
    if count is not None:
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            return "payload.count must be a positive integer"

    return None


def _validate_speech_payload(payload: dict[str, Any]) -> str | None:
    """Validate speech synthesis payload schema."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return "payload.text is required and must be a non-empty string"

    voice = payload.get("voice")
    if voice is not None and not isinstance(voice, str):
        return "payload.voice must be a string"

    fmt = payload.get("audio_format")
    if fmt is not None and not isinstance(fmt, str):
        return "payload.audio_format must be a string"

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
    """Handle canonical text generation request."""
    # 1. Validate credential mode
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                _SAFE_MESSAGES[ErrorCategory.INVALID_CREDENTIAL],
                provider_code="CREDENTIAL_MODE_MISMATCH",
            ),
        )

    # 2. Validate payload schema
    val_err = _validate_messages_payload(context.payload)
    if val_err:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, val_err, provider_code="INVALID_PAYLOAD"),
        )

    # 3. Execute via Layer 1
    messages = context.payload["messages"]
    temperature = context.payload.get("temperature")
    max_tokens = context.payload.get("max_tokens")

    try:
        res = await _core.generate_text_internal(
            model=context.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_ms=context.timeout_ms,
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception as exc:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.RETRYABLE_SERVER_ERROR,
                _SAFE_MESSAGES[ErrorCategory.RETRYABLE_SERVER_ERROR],
                provider_code="INTERNAL_EXCEPTION",
            ),
        )

    return FacadeResult(
        succeeded=True,
        output={
            "text": res["text"],
            "finish_reason": res.get("finish_reason", "stop"),
        },
        usage=Usage(
            input_tokens=res.get("input_tokens"),
            output_tokens=res.get("output_tokens"),
            units=1,
        ),
    )


async def generate_image(context: ProviderContext) -> FacadeResult:
    """Handle canonical image generation request."""
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                _SAFE_MESSAGES[ErrorCategory.INVALID_CREDENTIAL],
                provider_code="CREDENTIAL_MODE_MISMATCH",
            ),
        )

    val_err = _validate_image_payload(context.payload)
    if val_err:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, val_err, provider_code="INVALID_PAYLOAD"),
        )

    prompt = context.payload["prompt"]
    size = context.payload.get("size", "1024x1024")
    count = context.payload.get("count", 1)

    try:
        images = await _core.generate_image_internal(
            model=context.model,
            prompt=prompt,
            size=size,
            count=count,
            timeout_ms=context.timeout_ms,
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.RETRYABLE_SERVER_ERROR,
                _SAFE_MESSAGES[ErrorCategory.RETRYABLE_SERVER_ERROR],
                provider_code="INTERNAL_EXCEPTION",
            ),
        )

    return FacadeResult(
        succeeded=True,
        output={"images": images},
        usage=Usage(units=len(images)),
    )


async def synthesize_speech(context: ProviderContext) -> FacadeResult:
    """Handle canonical speech synthesis request."""
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                _SAFE_MESSAGES[ErrorCategory.INVALID_CREDENTIAL],
                provider_code="CREDENTIAL_MODE_MISMATCH",
            ),
        )

    val_err = _validate_speech_payload(context.payload)
    if val_err:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, val_err, provider_code="INVALID_PAYLOAD"),
        )

    text = context.payload["text"]
    voice = context.payload.get("voice")
    audio_format = context.payload.get("audio_format", "wav")

    try:
        res = await _core.synthesize_speech_internal(
            model=context.model,
            text=text,
            voice=voice,
            audio_format=audio_format,
            timeout_ms=context.timeout_ms,
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.RETRYABLE_SERVER_ERROR,
                _SAFE_MESSAGES[ErrorCategory.RETRYABLE_SERVER_ERROR],
                provider_code="INTERNAL_EXCEPTION",
            ),
        )

    return FacadeResult(
        succeeded=True,
        output={
            "audio_b64": res["audio_b64"],
            "audio_format": res["audio_format"],
        },
        usage=Usage(input_tokens=len(text), units=1),
    )


HANDLERS: dict[GatewayOperation, Any] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.GENERATE_IMAGE: generate_image,
    GatewayOperation.SYNTHESIZE_SPEECH: synthesize_speech,
}
