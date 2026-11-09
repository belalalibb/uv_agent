"""Error normalization helpers + provider_code sanitizer.

Fixes prior-art weakness #8: exception class names NEVER cross the wire.
``provider_code`` is sanitized to short alphanumeric/dash/underscore/dot
tokens (HTTP codes, upstream short codes) — anything else is dropped.
"""

from __future__ import annotations

import re

from gateway.contracts import ErrorCategory, GatewayError

_PROVIDER_CODE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Retryability defaults per category (facades may override retryable
# explicitly; these are the canonical defaults used by helpers).
RETRYABLE_DEFAULTS: dict[ErrorCategory, bool] = {
    ErrorCategory.AUTH_EXPIRED: True,
    ErrorCategory.INVALID_CREDENTIAL: False,
    ErrorCategory.RATE_LIMITED: True,
    ErrorCategory.QUOTA_EXCEEDED: False,
    ErrorCategory.MODEL_UNAVAILABLE: False,
    ErrorCategory.PROVIDER_UNAVAILABLE: False,
    ErrorCategory.UNSUPPORTED_CAPABILITY: False,
    ErrorCategory.BAD_REQUEST: False,
    ErrorCategory.CONTENT_REJECTED: False,
    ErrorCategory.TIMEOUT: True,
    ErrorCategory.RETRYABLE_SERVER_ERROR: True,
    ErrorCategory.NON_RETRYABLE_ERROR: False,
}


def is_retryable(category: ErrorCategory | str) -> bool:
    """Return canonical retryability for an ErrorCategory or category string."""
    if isinstance(category, str):
        try:
            category = ErrorCategory(category)
        except ValueError:
            return False
    return RETRYABLE_DEFAULTS.get(category, False)


def sanitize_provider_code(raw: str | None) -> str | None:
    """Keep short safe diagnostic codes; drop anything resembling internals."""

    if raw is None:
        return None
    candidate = raw.strip()
    if _PROVIDER_CODE_RE.fullmatch(candidate):
        return candidate
    return None


def make_error(
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool | None = None,
    retry_after_ms: int | None = None,
    provider_code: str | None = None,
) -> GatewayError:
    """Build a canonical GatewayError with sanitized diagnostics."""

    return GatewayError(
        category=category,
        retryable=RETRYABLE_DEFAULTS[category] if retryable is None else retryable,
        message=message,
        retry_after_ms=retry_after_ms,
        provider_code=sanitize_provider_code(provider_code),
    )


def internal_fault() -> GatewayError:
    """500-path error — deliberately generic; never carries exception names."""

    return make_error(
        ErrorCategory.RETRYABLE_SERVER_ERROR,
        "gateway internal fault",
        provider_code=None,
    )


def classify_http_status(status: int, body: str = "") -> ErrorCategory:
    """Canonical HTTP status to ErrorCategory mapper.

    Translates upstream HTTP response status and optional body diagnostics
    into one of the 12 canonical ErrorCategory values defined in ADR-0008.
    """
    low = (body or "").lower()
    if status in (401, 403):
        if "captcha" in low or "cloudflare" in low or "attention required" in low or "turnstile" in low:
            return ErrorCategory.PROVIDER_UNAVAILABLE
        if "invalid" in low or "wrong" in low or "bad credentials" in low:
            return ErrorCategory.INVALID_CREDENTIAL
        return ErrorCategory.AUTH_EXPIRED
    if status == 429:
        return ErrorCategory.QUOTA_EXCEEDED if ("quota" in low or "credit" in low or "balance" in low) else ErrorCategory.RATE_LIMITED
    if status == 404:
        return ErrorCategory.MODEL_UNAVAILABLE
    if status in (413, 422) and ("context" in low or "token" in low or "too long" in low or "length" in low):
        return ErrorCategory.BAD_REQUEST
    if status == 451 or "content_policy" in low or "safety" in low or "filtered" in low or "harmful" in low:
        return ErrorCategory.CONTENT_REJECTED
    if status == 503:
        return ErrorCategory.PROVIDER_UNAVAILABLE
    if status in (408, 504):
        return ErrorCategory.TIMEOUT
    if status in (500, 502):
        return ErrorCategory.RETRYABLE_SERVER_ERROR
    return ErrorCategory.NON_RETRYABLE_ERROR
