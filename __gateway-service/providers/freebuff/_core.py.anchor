"""Freebuff Core Engine — Layer 1.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Handles direct upstream communication with Freebuff chat stream endpoint.
- Autonomous cookie management via FREEBUFF_COOKIE environment variable or local file.
- Server-Sent Events (SSE) streaming with byte-perfect UTF-8 decoding.
- Extracts reasoning deltas, content deltas, and thread session continuity.
- Error taxonomy mapping to Gateway standard categories.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Generator, Optional
import requests

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = CURRENT_DIR.parent.parent
COOKIE_FILE = GATEWAY_DIR / "FREEBUFF_COOKIE.txt"
METADATA_FILE = CURRENT_DIR / "models_metadata.json"

API_CHAT_URL = "https://freebuff.com/api/chat/stream"
API_SESSION_URL = "https://freebuff.com/api/auth/session"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

# Load metadata
try:
    with open(METADATA_FILE, "r", encoding="utf-8") as _f:
        MODELS_METADATA = json.load(_f)
except Exception:
    MODELS_METADATA = {"glm-5.3-flash": {"id": "glm-5.3-flash", "display_name": "GLM 5.3 Flash"}}


class UpstreamFailure(Exception):
    """Normalized Layer 1 upstream exception matching Gateway taxonomy."""

    def __init__(
        self,
        category: str,
        message: str,
        retry_after_ms: Optional[int] = None,
        provider_code: Optional[str] = None,
    ):
        super().__init__(message)
        self.category = category
        self.message = message
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code


def get_cookie() -> str:
    """Retrieve active session cookie from environment or local storage."""
    env_cookie = os.environ.get("FREEBUFF_COOKIE", "").strip()
    if env_cookie:
        return env_cookie
    if COOKIE_FILE.exists():
        try:
            return COOKIE_FILE.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.warning("Failed to read FREEBUFF_COOKIE.txt: %s", e)
    return ""


def clean_cookie(raw: str) -> str:
    """Clean and normalize cookie string."""
    c = raw.replace("\r", " ").replace("\n", " ").strip()
    parts = [p.strip() for p in c.split(";") if "=" in p.strip()]
    return "; ".join(parts)


def check_health(timeout: int = 15) -> bool:
    """Check whether the active session cookie is valid and authorized."""
    cookie = clean_cookie(get_cookie())
    if not cookie:
        return False

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://freebuff.com/chat",
        "Cookie": cookie,
    }

    try:
        r = requests.get(API_SESSION_URL, headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            return bool(data.get("user"))
        return False
    except Exception:
        return False


def generate_text(
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 60,
    thread_id: Optional[str] = None,
) -> dict[str, Any]:
    """Blocking text inference executing SSE stream and returning complete response."""
    cookie = clean_cookie(get_cookie())
    if not cookie:
        raise UpstreamFailure("invalid_credential", "No active session cookie found for Freebuff")

    # Extract user prompt from last message
    prompt = messages[-1].get("content", "") if messages else ""

    # Cloudflare WAF Guard (Payload > 6000 chars triggers 403)
    if len(prompt) > 6000:
        logger.warning("Prompt length (%d) exceeds 6000 chars; trimming to prevent WAF 403", len(prompt))
        prompt = prompt[:5800] + "\n...[truncated for wire safety]"

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Content-Type": "application/json",
        "Origin": "https://freebuff.com",
        "Referer": "https://freebuff.com/chat",
        "Cookie": cookie,
    }

    payload = {
        "threadId": thread_id,
        "content": prompt,
        "model": model or "glm-5.3-flash",
        "reasoningEffort": "max",
        "gravity": {
            "user_data": {
                "visitor_id": "gruid_bvofl0dwqzz02atp",
                "session_id": "gr_sess_r2x4tvotz9jcvfjt",
                "client_user_agent": DEFAULT_USER_AGENT,
            },
            "event_source_url": "https://freebuff.com/chat",
            "client_context": {
                "timezone": "Africa/Cairo",
                "screen": {"width": 1552, "height": 873, "color_depth": 24, "pixel_depth": 24},
                "viewport": {"width": 1301, "height": 709},
                "platform": "Windows",
            },
        },
        "images": [],
        "attachments": [],
    }

    try:
        res = requests.post(API_CHAT_URL, json=payload, headers=headers, stream=True, timeout=timeout)
    except requests.Timeout as e:
        raise UpstreamFailure("timeout", f"Freebuff connection timed out after {timeout}s") from e
    except requests.RequestException as e:
        raise UpstreamFailure("retryable_server_error", f"Freebuff transport failure: {e}") from e

    if res.status_code == 401:
        raise UpstreamFailure("auth_expired", "Freebuff session expired (HTTP 401)")
    if res.status_code == 403:
        raise UpstreamFailure("invalid_credential", f"Freebuff access forbidden (HTTP 403): {res.text[:200]}")
    if res.status_code == 429:
        raise UpstreamFailure("rate_limited", "Freebuff rate limit exceeded (HTTP 429)")
    if res.status_code >= 500:
        raise UpstreamFailure("retryable_server_error", f"Freebuff server error (HTTP {res.status_code})")
    if res.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"Freebuff unexpected HTTP {res.status_code}: {res.text[:200]}")

    captured_thread_id = thread_id
    reasoning_chunks = []
    content_chunks = []

    try:
        for raw_line in res.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if line.startswith("data: "):
                raw_data = line[6:].strip()
                if raw_data == "[DONE]" or raw_data == '{"type":"done"}':
                    break
                try:
                    event = json.loads(raw_data)
                    ev_type = event.get("type")
                    if ev_type == "meta":
                        if not captured_thread_id:
                            captured_thread_id = event.get("threadId")
                    elif ev_type == "reasoning_delta":
                        reasoning_chunks.append(event.get("text", ""))
                    elif ev_type == "delta":
                        content_chunks.append(event.get("text", ""))
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        logger.warning("Stream read interrupted: %s", e)

    final_content = "".join(content_chunks)
    final_reasoning = "".join(reasoning_chunks)

    return {
        "content": final_content,
        "reasoning": final_reasoning,
        "thread_id": captured_thread_id,
        "model": model or "glm-5.3-flash",
    }


def stream_text(
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 60,
    thread_id: Optional[str] = None,
) -> Generator[str, None, None]:
    """Generator yielding content deltas from Freebuff SSE stream."""
    cookie = clean_cookie(get_cookie())
    if not cookie:
        raise UpstreamFailure("invalid_credential", "No active session cookie found for Freebuff")

    prompt = messages[-1].get("content", "") if messages else ""
    if len(prompt) > 6000:
        prompt = prompt[:5800] + "\n...[truncated for wire safety]"

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://freebuff.com",
        "Referer": "https://freebuff.com/chat",
        "Cookie": cookie,
    }

    payload = {
        "threadId": thread_id,
        "content": prompt,
        "model": model or "glm-5.3-flash",
        "reasoningEffort": "max",
        "gravity": {
            "user_data": {
                "visitor_id": "gruid_bvofl0dwqzz02atp",
                "session_id": "gr_sess_r2x4tvotz9jcvfjt",
                "client_user_agent": DEFAULT_USER_AGENT,
            },
            "event_source_url": "https://freebuff.com/chat",
            "client_context": {
                "timezone": "Africa/Cairo",
                "screen": {"width": 1552, "height": 873, "color_depth": 24, "pixel_depth": 24},
                "viewport": {"width": 1301, "height": 709},
                "platform": "Windows",
            },
        },
        "images": [],
        "attachments": [],
    }

    res = requests.post(API_CHAT_URL, json=payload, headers=headers, stream=True, timeout=timeout)
    if res.status_code != 200:
        if res.status_code in (401, 403):
            raise UpstreamFailure("auth_expired", f"HTTP {res.status_code}: {res.text[:200]}")
        elif res.status_code == 429:
            raise UpstreamFailure("rate_limited", f"HTTP {res.status_code}: {res.text[:200]}")
        elif res.status_code in (500, 502, 503):
            raise UpstreamFailure("retryable_server_error", f"HTTP {res.status_code}: {res.text[:200]}")
        else:
            raise UpstreamFailure("non_retryable_error", f"HTTP {res.status_code}: {res.text[:200]}")

    for raw_line in res.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("data: "):
            raw_data = line[6:].strip()
            if raw_data == "[DONE]" or raw_data == '{"type":"done"}':
                break
            try:
                event = json.loads(raw_data)
                if event.get("type") == "delta":
                    text = event.get("text", "")
                    if text:
                        yield text
            except json.JSONDecodeError:
                pass
