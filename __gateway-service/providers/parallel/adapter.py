#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parallel AI — adapter.py | تحويل نواتج _core إلى FacadeResult مع عزل تام للمعلومات السرية"""
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
from providers.parallel import _core


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


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text facade handler for Parallel AI."""
    if context.operation != GatewayOperation.GENERATE_TEXT:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.UNSUPPORTED_CAPABILITY,
                f"Handler generate_text cannot serve operation {context.operation!r}",
            ),
        )

    model = context.model or "default"
    messages = context.payload.get("messages", [])
    prompt = messages[-1].get("content", "") if messages else context.payload.get("prompt", "")

    if not prompt:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.BAD_REQUEST, "Prompt or messages must not be empty"),
        )

    try:
        text = await asyncio.to_thread(_core.generate_text, prompt, {}, model)
        return FacadeResult(
            succeeded=True,
            output={"text": text},
            usage=Usage(input_tokens=0, output_tokens=0, units=1),
        )
    except _core.UpstreamFailure as exc:
        return _translate_upstream_failure(exc)
    except Exception:
        return FacadeResult(
            succeeded=False,
            error=make_error(ErrorCategory.RETRYABLE_SERVER_ERROR, "upstream communication failure"),
        )


HANDLERS = {
    GatewayOperation.GENERATE_TEXT: generate_text,
}
