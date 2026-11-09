# -*- coding: utf-8 -*-
"""Layer 1 — RunPod Console Assistant Upstream Client & Autonomous Capsule.

Autonomous 3-Function Capsule:
1. register(email, password, captcha_token=None) -> dict
2. refresh(account=None, force=False) -> str | None
3. ask(prompt, files=None, timeout_ms=30000) -> UpstreamReply

Hermeticity: supports test transport override via `set_default_transport`.
"""

from __future__ import annotations

import json
import os
import uuid
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Dict

import httpx

# Optional curl_cffi in production, graceful fallback to httpx
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

CLERK_API_VERSION = "2025-11-10"
CLERK_JS_VERSION = "5.127.1"
CLERK_BASE = "https://clerk.runpod.io/v1/client"
CLERK_REFRESH_URL_TEMPLATE = (
    f"{CLERK_BASE}/sessions/{{session_id}}/tokens"
    f"?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"
)
STREAM_URL = "https://console.runpod.io/api/assistant/agents/console/stream"

_default_transport: httpx.AsyncBaseTransport | None = None

# Cached JWT across requests in process
_cached_jwt: str | None = None
_jwt_expires_at: int = 0


@dataclass(frozen=True)
class UpstreamReply:
    """Internal reply shape (Layer 1 freedom) — the facade translates it."""

    ok: bool
    text: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    fail_kind: str | None = None  # "no_session"|"auth_expired"|"timeout"|"network"|"http"
    http_status: int | None = None
    error_code: str | None = None
    retry_after_ms: int | None = None


def set_default_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Test seam: override HTTP transport with MockTransport for hermetic testing."""
    global _default_transport
    _default_transport = transport


def _get_accounts_data() -> dict[str, Any]:
    """Load session credentials from accounts_runpod.json."""
    accounts_file = Path(__file__).resolve().parent / "accounts_runpod.json"
    if accounts_file.exists():
        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"accounts": []}


# ── Capsule Function 1: register(...) ────────────────────────────────────────
def register(email: str, password: str, captcha_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Attempt registration against Clerk endpoint.
    Requires Turnstile CAPTCHA token for instant activation.
    """
    sign_up_url = f"{CLERK_BASE}/sign_ups?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"
    headers = {
        "origin": "https://console.runpod.io",
        "referer": "https://console.runpod.io/",
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    data = {"email_address": email, "password": password, "locale": "en-US"}
    if captcha_token:
        data["captcha_token"] = captcha_token

    if curl_requests is not None and _default_transport is None:
        resp = curl_requests.post(sign_up_url, headers=headers, data=data, impersonate="chrome")
        return {"status_code": resp.status_code, "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}
    else:
        with httpx.Client(transport=_default_transport if not isinstance(_default_transport, httpx.AsyncBaseTransport) else None) as client:
            resp = client.post(sign_up_url, headers=headers, data=data)
            return {"status_code": resp.status_code, "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}


# ── Capsule Function 2: refresh(...) ─────────────────────────────────────────
async def refresh(account: Optional[dict[str, Any]] = None, force: bool = False, timeout_s: float = 10.0) -> str | None:
    """
    Autonomous refresh function: exchanges Clerk session cookies for a fresh JWT.
    Updates in-memory cache and returns the active token.
    """
    global _cached_jwt, _jwt_expires_at

    now = int(time.time())
    if not force and _cached_jwt and (_jwt_expires_at - now > 15):
        return _cached_jwt

    if account is None:
        accounts = _get_accounts_data().get("accounts", [])
        if not accounts:
            return None
        account = accounts[0]

    session_id = account.get("session_id", "")
    cookies = account.get("cookies", {})
    if not session_id or not cookies:
        return None

    url = CLERK_REFRESH_URL_TEMPLATE.format(session_id=session_id)
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    headers = {
        "origin": "https://console.runpod.io",
        "referer": "https://console.runpod.io/",
        "cookie": cookie_str,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }

    if _default_transport is not None:
        async with httpx.AsyncClient(transport=_default_transport, timeout=timeout_s) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                _cached_jwt = data.get("jwt")
                _jwt_expires_at = now + 50
                return _cached_jwt
            return None

    if curl_requests is not None:
        resp = curl_requests.post(url, headers=headers, impersonate="chrome", timeout=timeout_s)
        if resp.status_code == 200:
            _cached_jwt = resp.json().get("jwt")
            _jwt_expires_at = now + 50
            return _cached_jwt
    else:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 200:
                _cached_jwt = resp.json().get("jwt")
                _jwt_expires_at = now + 50
                return _cached_jwt
    return None


# ── Capsule Function 3: ask(...) / call_runpod_assistant ─────────────────────
async def call_runpod_assistant(
    messages: list[dict[str, Any]],
    files: Optional[list[dict[str, Any]]] = None,
    timeout_ms: int = 30000,
    transport: httpx.AsyncBaseTransport | None = None,
) -> UpstreamReply:
    """Execute a completion query against RunPod Console Assistant with multimodal support."""
    global _cached_jwt, _jwt_expires_at

    active_transport = transport if transport is not None else _default_transport
    accounts = _get_accounts_data().get("accounts", [])
    if not accounts:
        return UpstreamReply(ok=False, fail_kind="no_session", error_code="NO_ACTIVE_ACCOUNTS")

    account = accounts[0]
    user_id = account.get("user_id", "user_runpod_default")

    jwt = await refresh(account=account, force=False, timeout_s=min(10.0, timeout_ms / 1000.0))
    if not jwt:
        return UpstreamReply(ok=False, fail_kind="auth_expired", error_code="CLERK_REFRESH_FAILED")

    # Build prompt parts and multi-turn message sequence (Ground truth: entry 1122 in HAR)
    runpod_messages = []
    for idx, m in enumerate(messages):
        role = m.get("role", "user")
        content = m.get("content", "")
        parts = []

        if role == "assistant":
            parts.append({"type": "step-start"})

        # Attach files to the last user message
        is_last_user = (role == "user" and idx == len(messages) - 1) or (
            role == "user" and not any(other.get("role") == "user" for other in messages[idx + 1:])
        )
        if is_last_user and files:
            for f in files:
                parts.append({
                    "type": "file",
                    "filename": f.get("filename", "file.bin"),
                    "mediaType": f.get("mediaType", "text/plain"),
                    "url": f.get("url", ""),
                })

        if isinstance(content, list):
            for c in content:
                if isinstance(c, dict):
                    if c.get("type") == "text":
                        parts.append({"type": "text", "text": c.get("text", "")})
                    elif c.get("type") == "image_url":
                        img_url = c.get("image_url", {}).get("url", "")
                        parts.append({
                            "type": "file",
                            "filename": "image.png",
                            "mediaType": "image/png" if "image/png" in img_url else "image/jpeg",
                            "url": img_url,
                        })
        else:
            parts.append({"type": "text", "text": str(content)})

        runpod_messages.append({
            "id": f"msg_{uuid.uuid4().hex[:16]}",
            "role": role if role in ["user", "assistant", "system"] else "user",
            "parts": parts,
        })

    thread_id = str(uuid.uuid4())
    headers = {
        "content-type": "application/json",
        "origin": "https://console.runpod.io",
        "referer": "https://console.runpod.io/",
        "x-clerk-token": _cached_jwt,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    }
    payload = {
        "messages": runpod_messages,
        "threadId": thread_id,
        "resourceId": user_id,
        "source": "console",
    }

    timeout_s = timeout_ms / 1000.0

    try:
        if active_transport is not None:
            async with httpx.AsyncClient(transport=active_transport, timeout=timeout_s) as client:
                resp = await client.post(STREAM_URL, headers=headers, json=payload)
                status = resp.status_code
                resp_text = resp.text
        else:
            if curl_requests is not None:
                resp = curl_requests.post(STREAM_URL, headers=headers, json=payload, impersonate="chrome", timeout=timeout_s)
                status = resp.status_code
                resp_text = resp.text
            else:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    resp = await client.post(STREAM_URL, headers=headers, json=payload)
                    status = resp.status_code
                    resp_text = resp.text

    except httpx.TimeoutException:
        return UpstreamReply(ok=False, fail_kind="timeout")
    except Exception as exc:
        err_msg = str(exc).lower()
        if "timeout" in err_msg:
            return UpstreamReply(ok=False, fail_kind="timeout")
        return UpstreamReply(ok=False, fail_kind="network", error_code=type(exc).__name__)

    if status != 200:
        if status in (401, 403):
            _cached_jwt = None
            return UpstreamReply(ok=False, fail_kind="auth_expired", http_status=status)
        return UpstreamReply(ok=False, fail_kind="http", http_status=status)

    # Parse SSE stream deltas
    deltas: list[str] = []
    for line in resp_text.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            d_str = line[6:].strip()
            if d_str == "[DONE]":
                break
            try:
                event = json.loads(d_str)
                if event.get("type") == "text-delta":
                    deltas.append(event.get("delta", ""))
            except Exception:
                pass

    full_output = "".join(deltas).strip()
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    file_overhead = (len(files) * 50) if files else 0
    prompt_tokens = max(1, (total_chars + file_overhead) // 4)
    completion_tokens = max(1, len(full_output) // 4)

    return UpstreamReply(
        ok=True,
        text=full_output,
        finish_reason="stop",
        usage={
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


async def ask(prompt: str, files: Optional[list[dict[str, Any]]] = None, timeout_ms: int = 30000) -> UpstreamReply:
    """Convenience async ask helper matching capsule contract."""
    messages = [{"role": "user", "content": prompt}]
    return await call_runpod_assistant(messages=messages, files=files, timeout_ms=timeout_ms)
