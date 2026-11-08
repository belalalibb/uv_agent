"""Typed exceptions mapped directly from the 12 Canonical Error Categories."""

from __future__ import annotations

from typing import Any
from .models import ErrorCategory


class GatewayError(Exception):
    """Base exception for all Gateway and Upstream provider errors."""

    def __init__(
        self,
        category: str,
        message: str,
        retryable: bool = False,
        retry_after_ms: int | None = None,
        provider_code: str | None = None,
        http_status: int = 200,
        raw_error: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{category}] {message}")
        self.category = category
        self.message = message
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code
        self.http_status = http_status
        self.raw_error = raw_error or {}


class AuthExpiredError(GatewayError):
    """Upstream/Gateway credential expired; retryable if credentials can be refreshed."""


class InvalidCredentialError(GatewayError):
    """Invalid or revoked credential / secret."""


class RateLimitedError(GatewayError):
    """Upstream rate limit reached (HTTP 429). Retry after retry_after_ms."""


class QuotaExceededError(GatewayError):
    """Provider quota or credits exhausted."""


class ModelUnavailableError(GatewayError):
    """Requested model does not exist or is deprecated upstream."""


class ProviderUnavailableError(GatewayError):
    """Upstream provider is unreachable or down."""


class UnsupportedCapabilityError(GatewayError):
    """Operation or feature not supported by this provider."""


class BadRequestError(GatewayError):
    """Caller request payload was invalid."""


class ContentRejectedError(GatewayError):
    """Content rejected by safety or moderation policy."""


class TimeoutError(GatewayError):
    """Upstream call exceeded specified timeout_ms."""


class RetryableServerError(GatewayError):
    """Upstream 5xx temporary server error."""


class NonRetryableError(GatewayError):
    """Permanent unclassified failure."""


class RouteNotFoundError(GatewayError):
    """Unknown, revoked or disabled X-Route-Token (HTTP 404)."""


_CATEGORY_TO_EXCEPTION: dict[str, type[GatewayError]] = {
    ErrorCategory.AUTH_EXPIRED: AuthExpiredError,
    ErrorCategory.INVALID_CREDENTIAL: InvalidCredentialError,
    ErrorCategory.RATE_LIMITED: RateLimitedError,
    ErrorCategory.QUOTA_EXCEEDED: QuotaExceededError,
    ErrorCategory.MODEL_UNAVAILABLE: ModelUnavailableError,
    ErrorCategory.PROVIDER_UNAVAILABLE: ProviderUnavailableError,
    ErrorCategory.UNSUPPORTED_CAPABILITY: UnsupportedCapabilityError,
    ErrorCategory.BAD_REQUEST: BadRequestError,
    ErrorCategory.CONTENT_REJECTED: ContentRejectedError,
    ErrorCategory.TIMEOUT: TimeoutError,
    ErrorCategory.RETRYABLE_SERVER_ERROR: RetryableServerError,
    ErrorCategory.NON_RETRYABLE_ERROR: NonRetryableError,
}


def create_gateway_error(
    category: str,
    message: str,
    retryable: bool = False,
    retry_after_ms: int | None = None,
    provider_code: str | None = None,
    http_status: int = 200,
    raw_error: dict[str, Any] | None = None,
) -> GatewayError:
    """Instantiate the exact typed Exception based on the canonical category."""
    exc_cls = _CATEGORY_TO_EXCEPTION.get(category, GatewayError)
    return exc_cls(
        category=category,
        message=message,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        provider_code=provider_code,
        http_status=http_status,
        raw_error=raw_error,
    )

