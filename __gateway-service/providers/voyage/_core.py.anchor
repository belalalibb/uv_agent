"""Layer 1 — Voyage AI upstream client. Internal territory; nothing here crosses.

Features:
- Real asynchronous HTTP calls to Voyage AI's API via httpx.
- Operations:
  * POST https://api.voyageai.com/v1/embeddings
  * POST https://api.voyageai.com/v1/rerank
- Multi-key pool rotation across accounts in accounts_voyage.json or GW_VOYAGE_API_KEY.
- Test seam (_default_transport) enabling 100% hermetic unit testing without network.
- Zero secret leakage: keys are never logged, never returned in reply text.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

VOYAGE_BASE_URL = "https://api.voyageai.com/v1"
VOYAGE_API_KEY_ENV = "GW_VOYAGE_API_KEY"

_ACCOUNTS_FILE = Path(__file__).resolve().parent / "accounts_voyage.json"

#: Test seam: when set, used as httpx transport for hermetic testing.
_default_transport: httpx.AsyncBaseTransport | None = None

_key_cursor: int = 0


@dataclass(frozen=True)
class UpstreamEmbeddingReply:
    """Internal embeddings reply shape (Layer 1 freedom) — facade translates it."""

    ok: bool
    embeddings: list[list[float]] = field(default_factory=list)
    dimensions: int = 0
    total_tokens: int = 0
    fail_kind: str | None = None  # "no_key" | "timeout" | "network" | "http"
    http_status: int | None = None
    error_code: str | None = None
    retry_after_ms: int | None = None


@dataclass(frozen=True)
class UpstreamRerankReply:
    """Internal rerank reply shape (Layer 1 freedom) — facade translates it."""

    ok: bool
    results: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    fail_kind: str | None = None  # "no_key" | "timeout" | "network" | "http"
    http_status: int | None = None
    error_code: str | None = None
    retry_after_ms: int | None = None


def load_pool_keys() -> list[str]:
    """Load active API keys from environment or accounts pool."""
    env_key = os.getenv(VOYAGE_API_KEY_ENV)
    if env_key:
        return [env_key]

    keys: list[str] = []
    if _ACCOUNTS_FILE.exists():
        try:
            with open(_ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for acc in data.get("accounts", []):
                    k = acc.get("api_key")
                    if k and acc.get("status") == "active":
                        keys.append(k)
        except Exception:
            pass

    return keys


def get_next_api_key(user_key: str | None = None) -> str | None:
    """Retrieve an API key: user_key if supplied, otherwise next key from pool."""
    global _key_cursor
    if user_key:
        return user_key

    pool = load_pool_keys()
    if not pool:
        return None

    key = pool[_key_cursor % len(pool)]
    _key_cursor += 1
    return key


def _sanitize_error_code(status_code: int, body: str) -> str:
    """Extract a short, safe error token (e.g. '429') with zero secrets."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and "detail" in parsed:
            # If rate-limited or payment required
            if "rate limits" in str(parsed["detail"]):
                return "rate_limited"
    except Exception:
        pass
    return str(status_code)


async def call_embeddings(
    model: str,
    inputs: list[str],
    timeout_ms: int,
    user_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpstreamEmbeddingReply:
    """Send embedding request to Voyage AI /v1/embeddings."""
    api_key = get_next_api_key(user_key)
    if not api_key:
        return UpstreamEmbeddingReply(ok=False, fail_kind="no_key", error_code="no_key")

    effective_transport = transport if transport is not None else _default_transport
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if model.startswith("voyage-multimodal"):
        endpoint = f"{VOYAGE_BASE_URL}/multimodalembeddings"
        formatted_inputs = [
            {"content": [{"type": "text", "text": item}]}
            for item in inputs
        ]
        payload = {
            "model": model,
            "inputs": formatted_inputs,
        }
    else:
        endpoint = f"{VOYAGE_BASE_URL}/embeddings"
        payload = {
            "model": model,
            "input": inputs,
        }

    timeout = httpx.Timeout(timeout_ms / 1000.0)
    try:
        async with httpx.AsyncClient(transport=effective_transport, timeout=timeout) as client:
            resp = await client.post(
                endpoint,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", [])
            embeddings = [item["embedding"] for item in items if "embedding" in item]
            dims = len(embeddings[0]) if embeddings else 0
            usage_info = data.get("usage", {})
            total_tokens = usage_info.get("total_tokens", len(inputs))

            return UpstreamEmbeddingReply(
                ok=True,
                embeddings=embeddings,
                dimensions=dims,
                total_tokens=total_tokens,
                http_status=resp.status_code,
            )

    except httpx.TimeoutException:
        return UpstreamEmbeddingReply(ok=False, fail_kind="timeout", error_code="timeout")
    except httpx.HTTPStatusError as exc:
        code = _sanitize_error_code(exc.response.status_code, exc.response.text)
        retry_after = None
        if exc.response.status_code == 429:
            retry_after = 2000
        return UpstreamEmbeddingReply(
            ok=False,
            fail_kind="http",
            http_status=exc.response.status_code,
            error_code=code,
            retry_after_ms=retry_after,
        )
    except httpx.RequestError:
        return UpstreamEmbeddingReply(ok=False, fail_kind="network", error_code="network")
    except Exception:
        return UpstreamEmbeddingReply(ok=False, fail_kind="http", error_code="internal")


async def call_rerank(
    model: str,
    query: str,
    documents: list[str],
    top_n: int | None = None,
    timeout_ms: int = 30000,
    user_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpstreamRerankReply:
    """Send rerank request to Voyage AI /v1/rerank."""
    api_key = get_next_api_key(user_key)
    if not api_key:
        return UpstreamRerankReply(ok=False, fail_kind="no_key", error_code="no_key")

    effective_transport = transport if transport is not None else _default_transport
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
    }

    timeout = httpx.Timeout(timeout_ms / 1000.0)
    try:
        async with httpx.AsyncClient(transport=effective_transport, timeout=timeout) as client:
            resp = await client.post(
                f"{VOYAGE_BASE_URL}/rerank",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            raw_results = data.get("data", [])
            results = [
                {
                    "index": item["index"],
                    "relevance_score": float(item["relevance_score"]),
                }
                for item in raw_results
            ]
            usage_info = data.get("usage", {})
            total_tokens = usage_info.get("total_tokens", len(documents))

            return UpstreamRerankReply(
                ok=True,
                results=results,
                total_tokens=total_tokens,
                http_status=resp.status_code,
            )

    except httpx.TimeoutException:
        return UpstreamRerankReply(ok=False, fail_kind="timeout", error_code="timeout")
    except httpx.HTTPStatusError as exc:
        code = _sanitize_error_code(exc.response.status_code, exc.response.text)
        retry_after = None
        if exc.response.status_code == 429:
            retry_after = 2000
        return UpstreamRerankReply(
            ok=False,
            fail_kind="http",
            http_status=exc.response.status_code,
            error_code=code,
            retry_after_ms=retry_after,
        )
    except httpx.RequestError:
        return UpstreamRerankReply(ok=False, fail_kind="network", error_code="network")
    except Exception:
        return UpstreamRerankReply(ok=False, fail_kind="http", error_code="internal")


class UpstreamFailure(Exception):
    """Normalized internal failure exception conforming to provider standards."""

    def __init__(
        self,
        category: str = "non_retryable_error",
        message: str = "upstream call failed",
        provider_code: str | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.provider_code = provider_code
        self.retry_after_ms = retry_after_ms


async def ask(
    prompt: str,
    model: str = "rerank-2",
    documents: list[str] | None = None,
    user_key: str | None = None,
) -> str:
    """Convenience semantic query interface returning the most relevant document."""
    docs = documents if documents else [prompt]
    reply = await call_rerank(
        model=model,
        query=prompt,
        documents=docs,
        user_key=user_key,
    )
    if not reply.ok:
        cat = "rate_limited" if reply.http_status == 429 else "non_retryable_error"
        raise UpstreamFailure(
            category=cat,
            message="rerank ask failed",
            provider_code=reply.error_code,
            retry_after_ms=reply.retry_after_ms,
        )

    if reply.results:
        top_idx = reply.results[0]["index"]
        return docs[top_idx]
    return ""

