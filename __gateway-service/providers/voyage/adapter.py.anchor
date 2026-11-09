"""Layer 2 — Voyage AI Facade Adapter. The only layer the gateway sees.

ProviderContext in, FacadeResult out — success matches the canonical
schemas (CONTRACT §5 for create_embeddings, §6 for rerank_documents).
Errors map to exactly one of the 12 closed ErrorCategory values.
"""

from __future__ import annotations

from typing import Any

from gateway.contracts import (
    ErrorCategory,
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    Usage,
)
from gateway.errors import make_error
from providers.voyage import _core

_ALLOWED_EMBEDDING_KEYS = frozenset({"inputs"})
_ALLOWED_RERANK_KEYS = frozenset({"query", "documents", "top_n"})

_HTTP_STATUS_MAP: dict[int, ErrorCategory] = {
    401: ErrorCategory.INVALID_CREDENTIAL,
    403: ErrorCategory.INVALID_CREDENTIAL,
    404: ErrorCategory.MODEL_UNAVAILABLE,
    429: ErrorCategory.RATE_LIMITED,
    400: ErrorCategory.BAD_REQUEST,
    413: ErrorCategory.BAD_REQUEST,
    422: ErrorCategory.BAD_REQUEST,
    500: ErrorCategory.RETRYABLE_SERVER_ERROR,
    502: ErrorCategory.RETRYABLE_SERVER_ERROR,
    503: ErrorCategory.RETRYABLE_SERVER_ERROR,
    504: ErrorCategory.RETRYABLE_SERVER_ERROR,
}


def _validate_embeddings_payload(payload: dict[str, Any]) -> FacadeResult | None:
    """Validate create_embeddings payload schema per CONTRACT §5."""
    extras = set(payload) - _ALLOWED_EMBEDDING_KEYS
    if extras:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"payload contains extra forbidden keys {sorted(extras)}",
            ),
        )

    inputs = payload.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "payload.inputs is required and must be a non-empty list of strings",
            ),
        )

    for idx, item in enumerate(inputs):
        if not isinstance(item, str) or not item:
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    f"payload.inputs[{idx}] must be a non-empty string",
                ),
            )

    return None


def _validate_rerank_payload(payload: dict[str, Any]) -> FacadeResult | None:
    """Validate rerank_documents payload schema per CONTRACT §6."""
    extras = set(payload) - _ALLOWED_RERANK_KEYS
    if extras:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"payload contains extra forbidden keys {sorted(extras)}",
            ),
        )

    query = payload.get("query")
    if not isinstance(query, str) or not query:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "payload.query is required and must be a non-empty string",
            ),
        )

    documents = payload.get("documents")
    if not isinstance(documents, list) or not documents:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                "payload.documents is required and must be a non-empty list of strings",
            ),
        )

    for idx, item in enumerate(documents):
        if not isinstance(item, str) or not item:
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    f"payload.documents[{idx}] must be a non-empty string",
                ),
            )

    top_n = payload.get("top_n")
    if top_n is not None:
        if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
            return FacadeResult(
                succeeded=False,
                error=make_error(
                    ErrorCategory.BAD_REQUEST,
                    "payload.top_n must be a positive integer",
                ),
            )

    return None


def _translate_failure(
    fail_kind: str | None,
    http_status: int | None,
    error_code: str | None,
    retry_after_ms: int | None,
) -> FacadeResult:
    """Translate Layer 1 failure shape into canonical wire error."""
    if fail_kind == "no_key":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.INVALID_CREDENTIAL,
                "no active API key available in pool",
                provider_code="no_key",
            ),
        )
    if fail_kind == "timeout":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.TIMEOUT,
                "upstream call timed out",
                retryable=True,
                provider_code="timeout",
            ),
        )
    if fail_kind == "network":
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.PROVIDER_UNAVAILABLE,
                "upstream network failure",
                retryable=True,
                provider_code="network",
            ),
        )

    category = _HTTP_STATUS_MAP.get(http_status or 0, ErrorCategory.NON_RETRYABLE_ERROR)
    retryable = category in {
        ErrorCategory.RATE_LIMITED,
        ErrorCategory.TIMEOUT,
        ErrorCategory.RETRYABLE_SERVER_ERROR,
    }

    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            "upstream call failed",
            retryable=retryable,
            retry_after_ms=retry_after_ms,
            provider_code=error_code or (str(http_status) if http_status else None),
        ),
    )


async def create_embeddings(context: ProviderContext) -> FacadeResult:
    """create_embeddings facade — canonical payload in, canonical result out."""
    if context.operation != GatewayOperation.CREATE_EMBEDDINGS:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"operation mismatch: expected create_embeddings, got {context.operation}",
            ),
        )

    invalid = _validate_embeddings_payload(context.payload)
    if invalid is not None:
        return invalid

    inputs = context.payload["inputs"]
    reply = await _core.call_embeddings(
        model=context.model,
        inputs=inputs,
        timeout_ms=context.timeout_ms,
        user_key=context.credential_value,
    )

    if not reply.ok:
        return _translate_failure(
            reply.fail_kind,
            reply.http_status,
            reply.error_code,
            reply.retry_after_ms,
        )

    return FacadeResult(
        succeeded=True,
        output={
            "embeddings": reply.embeddings,
            "dimensions": reply.dimensions,
        },
        usage=Usage(
            input_tokens=reply.total_tokens,
            units=len(inputs),
        ),
    )


async def rerank_documents(context: ProviderContext) -> FacadeResult:
    """rerank_documents facade — canonical payload in, canonical result out."""
    if context.operation != GatewayOperation.RERANK_DOCUMENTS:
        return FacadeResult(
            succeeded=False,
            error=make_error(
                ErrorCategory.BAD_REQUEST,
                f"operation mismatch: expected rerank_documents, got {context.operation}",
            ),
        )

    invalid = _validate_rerank_payload(context.payload)
    if invalid is not None:
        return invalid

    query = context.payload["query"]
    documents = context.payload["documents"]
    top_n = context.payload.get("top_n")

    reply = await _core.call_rerank(
        model=context.model,
        query=query,
        documents=documents,
        top_n=top_n,
        timeout_ms=context.timeout_ms,
        user_key=context.credential_value,
    )

    if not reply.ok:
        return _translate_failure(
            reply.fail_kind,
            reply.http_status,
            reply.error_code,
            reply.retry_after_ms,
        )

    # Sort results by relevance_score descending per CONTRACT §6
    results = sorted(reply.results, key=lambda x: x["relevance_score"], reverse=True)
    if top_n is not None and top_n > 0:
        results = results[:top_n]

    return FacadeResult(
        succeeded=True,
        output={"results": results},
        usage=Usage(
            units=len(documents),
        ),
    )


HANDLERS: dict[GatewayOperation, object] = {
    GatewayOperation.CREATE_EMBEDDINGS: create_embeddings,
    GatewayOperation.RERANK_DOCUMENTS: rerank_documents,
}


def _translate_upstream_failure(exc: _core.UpstreamFailure) -> FacadeResult:
    """Translate Layer 1 failure shape into canonical wire error."""
    try:
        category = ErrorCategory(exc.category)
    except ValueError:
        category = ErrorCategory.NON_RETRYABLE_ERROR

    return FacadeResult(
        succeeded=False,
        error=make_error(
            category,
            exc.message or "upstream call failed",
            retryable=category in {
                ErrorCategory.RATE_LIMITED,
                ErrorCategory.TIMEOUT,
                ErrorCategory.RETRYABLE_SERVER_ERROR,
            },
            retry_after_ms=exc.retry_after_ms,
            provider_code=exc.provider_code,
        ),
    )


async def generate_text(context: ProviderContext) -> FacadeResult:
    """generate_text fallback — Voyage AI is an embeddings and reranking engine."""
    return FacadeResult(
        succeeded=False,
        error=make_error(
            ErrorCategory.UNSUPPORTED_CAPABILITY,
            "Voyage AI is an embeddings and reranking engine; text generation is not supported",
        ),
    )

