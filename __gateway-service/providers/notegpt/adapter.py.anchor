"""NoteGPT AI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Enforces strict contract validation on input payloads (messages schema).
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
from providers.notegpt import _core


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
                "NoteGPT AI requires platform credential mode without caller-supplied value",
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
    session_id = context.payload.get("session_id") or context.payload.get("conversation_id")
    try:
        text, finish_reason, usage_dict, latency_ms = _core.ask(
            model=context.model,
            messages=messages,
            session_id=session_id,
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


async def synthesize_speech(context: ProviderContext) -> FacadeResult:
    """Handle canonical speech synthesis request."""
    # 1. Validate credential mode
    if context.credential_mode != CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "NoteGPT AI requires platform credential mode without caller-supplied value",
            ),
        )

    # 2. Validate payload schema
    err = _validate_speech_payload(context.payload)
    if err:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err),
        )

    text = context.payload["text"]
    voice = context.payload.get("voice")
    speed = context.payload.get("speed", 1.0)
    pitch = context.payload.get("pitch", 0)
    audio_format = context.payload.get("audio_format", "mp3")

    # 3. Call Layer 1 internal speech synthesis engine
    try:
        res = _core.synthesize_speech_internal(
            model=context.model,
            text=text,
            voice=voice,
            speed=speed,
            pitch=pitch,
            audio_format=audio_format,
            timeout_ms=context.timeout_ms,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "audio_b64": res["audio_b64"],
                "audio_format": res["audio_format"],
                "cdn_url": res.get("cdn_url"),
            },
            usage=Usage(
                input_tokens=len(text),
                units=1,
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


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.SYNTHESIZE_SPEECH: synthesize_speech,
}

