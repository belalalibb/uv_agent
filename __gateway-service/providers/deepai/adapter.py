"""DeepAI Facade Adapter — Layer 2.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Translates canonical ProviderContext -> Layer 1 (_core) -> canonical FacadeResult.
- Handles generate_text, analyze_vision, and transcribe_audio.
- Supports multi-extension file attachments (.py, .md, .txt, .json, .pdf, etc.).
- Supports multi-turn conversation and session continuity.
- Maps all upstream errors to canonical 12 ErrorCategory taxonomy.
- Absolute zero credential or internal leakage.
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
from providers.deepai import _core


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
    """generate_text facade handler for DeepAI."""
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
                "DeepAI operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    err_msg = _validate_messages_payload(context.payload)
    if err_msg:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, err_msg),
        )

    messages: list[dict[str, str]] = list(context.payload["messages"])
    session_id: str | None = context.payload.get("session_id")
    files_payload = context.payload.get("files")
    attachment_uuids: list[str] = []

    # Handle file attachments (any extension: .py, .md, .txt, .json, .pdf, etc.)
    if files_payload and isinstance(files_payload, list):
        for f_idx, f_item in enumerate(files_payload):
            if not isinstance(f_item, dict) or "name" not in f_item:
                continue
            filename = str(f_item["name"])
            raw_content = f_item.get("content", "")
            is_b64 = f_item.get("is_base64", False)
            if is_b64 and isinstance(raw_content, str):
                try:
                    f_bytes = base64.b64decode(raw_content)
                except Exception:
                    f_bytes = raw_content.encode("utf-8")
            elif isinstance(raw_content, bytes):
                f_bytes = raw_content
            else:
                f_bytes = str(raw_content).encode("utf-8")

            try:
                att = _core.upload_attachment(f_bytes, filename=filename, timeout=context.timeout_ms // 1000)
                attachment_uuids.append(att["uuid"])
                # For code/text files, prepend content into conversation context for absolute accuracy
                if any(filename.endswith(ext) for ext in [".py", ".md", ".txt", ".json", ".js", ".html", ".css", ".csv", ".xml", ".sh", ".yaml", ".yml"]):
                    try:
                        text_content = f_bytes.decode("utf-8", errors="replace")
                        if messages and messages[-1]["role"] == "user":
                            messages[-1] = {
                                "role": "user",
                                "content": f"[Attached File: {filename}]\n```\n{text_content}\n```\n\n{messages[-1]['content']}",
                            }
                    except Exception:
                        pass
            except _core.UpstreamFailure as exc:
                return _translate_upstream_failure(exc)
            except Exception:
                return FacadeResult(
                    succeeded=False,
                    error=make_error(ErrorCategory.NON_RETRYABLE_ERROR, f"Failed uploading attachment {filename}"),
                )

    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        reply = _core.ask(
            model=context.model,
            messages=messages,
            session_id=session_id,
            attachment_uuids=attachment_uuids if attachment_uuids else None,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "text": reply["text"],
                "finish_reason": "stop",
                "session_id": reply.get("session_id"),
            },
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected internal failure during text generation",
            ),
        )


async def analyze_vision(context: ProviderContext) -> FacadeResult:
    """analyze_vision facade handler for DeepAI."""
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
                "DeepAI operates in platform credential mode; caller credentials are not permitted",
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

    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        attachment = _core.upload_attachment(
            image_bytes,
            filename=f"image.{image_format}",
            content_type=f"image/{image_format}",
            timeout=timeout_s,
        )
        reply = _core.ask(
            model=context.model,
            prompt=instruction,
            attachment_uuids=[attachment["uuid"]],
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={"text": reply["text"]},
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected internal failure during vision analysis",
            ),
        )


async def transcribe_audio(context: ProviderContext) -> FacadeResult:
    """transcribe_audio facade handler for DeepAI."""
    if context.operation != GatewayOperation.TRANSCRIBE_AUDIO:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler transcribe_audio cannot serve operation {context.operation!r}",
            ),
        )

    if context.credential_mode is not CredentialMode.PLATFORM or context.credential_value:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "DeepAI operates in platform credential mode; caller credentials are not permitted",
            ),
        )

    audio_b64 = context.payload.get("audio_b64")
    audio_format = context.payload.get("audio_format", "wav")

    if not isinstance(audio_b64, str) or not audio_b64:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.audio_b64 is required and must be a string"),
        )
    if not isinstance(audio_format, str) or not audio_format:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.audio_format is required and must be a string"),
        )

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "payload.audio_b64 is not valid base64"),
        )

    timeout_s = max(1, context.timeout_ms // 1000)

    try:
        reply = _core.transcribe_audio(
            audio_bytes=audio_bytes,
            audio_format=audio_format,
            timeout=timeout_s,
        )
        return FacadeResult(
            succeeded=True,
            output={
                "text": reply["text"],
                "language": reply.get("language"),
            },
            usage=Usage(units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.NON_RETRYABLE_ERROR,
                "Unexpected internal failure during audio transcription",
            ),
        )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.GENERATE_TEXT: generate_text,
    GatewayOperation.ANALYZE_VISION: analyze_vision,
    GatewayOperation.TRANSCRIBE_AUDIO: transcribe_audio,
}
