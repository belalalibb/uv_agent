"""LlamaCoder Together AI Layer 1 Core Implementation.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- 100% Pure HTTP Requests (zero browser, zero cookies, zero tokens, zero API keys).
- Endpoints:
    * POST /api/create-chat -> session creation
    * POST /api/get-next-completion-stream-promise -> NDJSON streaming
    * POST /api/generate-chat-title -> smart conversation naming
    * POST /api/s3-upload -> presigned S3 URL generation
    * PUT S3 -> binary upload
    * POST /api/s3-upload/complete -> screenshot token generation
- Strict upstream failure translation to Gateway ErrorCategory strings.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return a pooled requests.Session with HTTP Keep-Alive and retry policy."""
    global _session
    if _session is None:
        s = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=retries,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session

BASE_URL = "https://llamacoder.together.ai"

COMMON_HEADERS = {
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

# Canonical model aliases mapping to official Together AI identifiers
MODEL_ALIASES: dict[str, str] = {
    # DeepSeek family
    "deepseek-v4.1": "deepseek-ai/DeepSeek-V4.1-Flash",
    "deepseek-v4.1-flash": "deepseek-ai/DeepSeek-V4.1-Flash",
    "deepseek-v4-pro": "deepseek-ai/DeepSeek-V4-Pro-0813",
    "deepseek-v4-flash": "deepseek-ai/DeepSeek-V4-Flash-0731",
    # GLM family
    "glm-5.3-flash": "zai-org/GLM-5.3-Flash",
    "glm-5.3": "zai-org/GLM-5.3",
    "glm-5.2": "zai-org/GLM-5.2",
    # Kimi / Moonshot
    "kimi-k3": "moonshotai/Kimi-K3",
    # Qwen family
    "qwen-3.8-flash": "Qwen/Qwen3.8-Flash",
    "qwen-3.7-max": "Qwen/Qwen3.7-Max",
    "qwen-3.7-plus": "Qwen/Qwen3.7-Plus",
    "qwen-3.6-plus": "Qwen/Qwen3.6-Plus",
    "qwen-3.5-9b": "Qwen/Qwen3.5-9B",
    "qwen-2.5-coder": "Qwen/Qwen2.5-Coder-32B-Instruct",
    # Meta / OpenAI / Minimax
    "llama-3.3-70b": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "gpt-oss-120b": "openai/gpt-oss-120b",
    "minimax-m3": "MiniMaxAI/MiniMax-M3",
}

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"


class UpstreamFailure(Exception):
    """Encapsulates all Layer 1 upstream failures for Gateway mapping."""

    def __init__(
        self,
        category: str,
        message: str,
        status_code: int | None = None,
        retry_after_ms: int | None = None,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code


def resolve_model_name(model: str) -> str:
    """Normalize model slug or return unchanged if already fully qualified."""
    cleaned = model.strip().lower()
    if cleaned in MODEL_ALIASES:
        return MODEL_ALIASES[cleaned]
    # Check if direct match in values (case-insensitive)
    for alias_target in MODEL_ALIASES.values():
        if alias_target.lower() == cleaned:
            return alias_target
    return model


def upload_image_bytes(
    img_bytes: bytes,
    filename: str = "image.png",
    content_type: str = "image/png",
    timeout: int = 30,
) -> str:
    """Upload image bytes to S3 via LlamaCoder presigned pipeline and return screenshotToken.

    Strict validation: Only PNG, JPEG, and WebP are allowed by upstream.
    Audio/PDF/Text files will be rejected with BAD_REQUEST (HTTP 415).
    """
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if content_type.lower() not in allowed_types:
        raise UpstreamFailure(
            category="bad_request",
            message=f"Unsupported media type {content_type!r}. Upstream accepts only image/png, image/jpeg, and image/webp",
            status_code=415,
        )

    size = len(img_bytes)
    sha256_hash = hashlib.sha256(img_bytes).digest()
    checksum = base64.b64encode(sha256_hash).decode("utf-8")

    headers_json = dict(COMMON_HEADERS)
    headers_json["Content-Type"] = "application/json"

    # 1. Request presigned S3 upload URL
    s3_payload = {
        "filename": filename,
        "contentType": content_type,
        "size": size,
        "checksum": checksum,
    }
    try:
        r1 = requests.post(
            f"{BASE_URL}/api/s3-upload",
            json=s3_payload,
            headers=headers_json,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        raise UpstreamFailure("timeout", "Upstream S3 upload request timed out")
    except requests.exceptions.RequestException as err:
        raise UpstreamFailure("provider_unavailable", f"Network error during S3 upload: {err}")

    if r1.status_code == 415:
        raise UpstreamFailure(
            category="bad_request",
            message="Only PNG, JPEG, and WebP images are allowed by upstream",
            status_code=415,
        )
    if r1.status_code == 429:
        raise UpstreamFailure("rate_limited", "Upstream S3 upload rate limit reached", status_code=429)
    if r1.status_code >= 500:
        raise UpstreamFailure("retryable_server_error", f"Upstream S3 server error ({r1.status_code})", status_code=r1.status_code)
    if r1.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"S3 upload request failed ({r1.status_code}): {r1.text[:200]}", status_code=r1.status_code)

    s3_data = r1.json()
    upload_url = s3_data.get("url")
    upload_headers = s3_data.get("headers", {})
    key = s3_data.get("key")
    if not upload_url or not key:
        raise UpstreamFailure("non_retryable_error", "Invalid presigned URL response from upstream")

    # 2. Upload raw bytes to S3
    try:
        r2 = requests.put(upload_url, data=img_bytes, headers=upload_headers, timeout=timeout)
    except requests.exceptions.Timeout:
        raise UpstreamFailure("timeout", "S3 binary PUT timed out")
    except requests.exceptions.RequestException as err:
        raise UpstreamFailure("provider_unavailable", f"Network error during S3 binary PUT: {err}")

    if r2.status_code not in (200, 204):
        raise UpstreamFailure("retryable_server_error", f"S3 binary PUT failed ({r2.status_code})", status_code=r2.status_code)

    # 3. Complete upload and get screenshotToken
    try:
        r3 = requests.post(
            f"{BASE_URL}/api/s3-upload/complete",
            json={"key": key},
            headers=headers_json,
            timeout=timeout,
        )
    except requests.exceptions.Timeout:
        raise UpstreamFailure("timeout", "S3 complete request timed out")
    except requests.exceptions.RequestException as err:
        raise UpstreamFailure("provider_unavailable", f"Network error during S3 complete: {err}")

    if r3.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"S3 upload completion failed ({r3.status_code})", status_code=r3.status_code)

    token = r3.json().get("token")
    if not token:
        raise UpstreamFailure("non_retryable_error", "Missing screenshotToken from upstream complete response")


    return token


def create_chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    screenshot_token: str | None = None,
    timeout: int = 30,
) -> tuple[str, str]:
    """Create a new chat conversation on LlamaCoder with auto-retry and return (chatId, lastMessageId)."""
    resolved_model = resolve_model_name(model)
    url = f"{BASE_URL}/api/create-chat"
    headers = dict(COMMON_HEADERS)
    headers["Content-Type"] = "application/json"
    headers["Connection"] = "keep-alive"

    payload: dict[str, Any] = {
        "prompt": prompt,
        "model": resolved_model,
    }
    if screenshot_token:
        payload["screenshotToken"] = screenshot_token

    session = get_session()
    last_err = None

    for attempt in range(1, 4):
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=(15.0, float(timeout)))
            if resp.status_code == 429:
                raise UpstreamFailure("rate_limited", "Upstream rate limit reached", status_code=429)
            if resp.status_code == 404:
                raise UpstreamFailure("model_unavailable", f"Model {resolved_model!r} not found on upstream", status_code=404)
            if resp.status_code == 400:
                raise UpstreamFailure("bad_request", f"Upstream rejected payload: {resp.text[:200]}", status_code=400)
            if resp.status_code in (500, 502, 503, 504) and attempt < 3:
                time.sleep(1.0 * attempt)
                continue
            if resp.status_code >= 500:
                raise UpstreamFailure("retryable_server_error", f"Upstream server error ({resp.status_code})", status_code=resp.status_code)
            if resp.status_code != 200:
                raise UpstreamFailure("non_retryable_error", f"create-chat failed with status {resp.status_code}", status_code=resp.status_code)

            data = resp.json()
            chat_id = data.get("chatId")
            message_id = data.get("lastMessageId")
            if not chat_id or not message_id:
                raise UpstreamFailure("non_retryable_error", f"Missing chatId or lastMessageId: {data}")

            return chat_id, message_id

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as err:
            last_err = err
            if attempt < 3:
                time.sleep(1.0 * attempt)
                continue
            raise UpstreamFailure("provider_unavailable", f"Network failure calling create-chat: {err}")
        except UpstreamFailure:
            raise
        except Exception as err:
            raise UpstreamFailure("non_retryable_error", f"Unexpected error in create-chat: {err}")

    raise UpstreamFailure("provider_unavailable", f"create-chat failed after 3 attempts: {last_err}")


def stream_completion(
    message_id: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 600,
) -> Generator[str, None, None]:
    """Stream NDJSON completion chunks with 10-minute zero-drop connection resilience."""
    resolved_model = resolve_model_name(model)
    url = f"{BASE_URL}/api/get-next-completion-stream-promise"
    headers = dict(COMMON_HEADERS)
    headers["Content-Type"] = "text/plain;charset=UTF-8"
    headers["Connection"] = "keep-alive"

    payload = {
        "messageId": message_id,
        "model": resolved_model,
    }

    session = get_session()
    resp = None
    read_timeout = max(60.0, float(timeout))

    # Handshake resilience: up to 3 connection attempts against transient serverless 500/502/503
    for attempt in range(1, 4):
        try:
            resp = session.post(
                url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=(20.0, read_timeout),
            )
            if resp.status_code in (500, 502, 503, 504) and attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as err:
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise UpstreamFailure("provider_unavailable", f"Network failure connecting stream: {err}")

    if resp is None:
        raise UpstreamFailure("provider_unavailable", "Failed to connect to completion stream")

    if resp.status_code == 429:
        raise UpstreamFailure("rate_limited", "Stream rate limited", status_code=429)
    if resp.status_code >= 500:
        raise UpstreamFailure("retryable_server_error", f"Stream server error ({resp.status_code})", status_code=resp.status_code)
    if resp.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"Stream failed with status {resp.status_code}", status_code=resp.status_code)

    has_yielded = False
    try:
        for line in resp.iter_lines(chunk_size=1024):
            if line:
                try:
                    line_str = line.decode("utf-8")
                    chunk = json.loads(line_str)
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        reasoning = delta.get("reasoning_content", "")
                        if content:
                            has_yielded = True
                            yield content
                        elif reasoning:
                            has_yielded = True
                            yield reasoning
                        if choices[0].get("finish_reason") in ("stop", "length", "eos"):
                            break
                except Exception:
                    # Non-fatal chunk skip (e.g. keep-alive or malformed buffer chunk)
                    continue
    except Exception:
        # Zero-drop rule: if tokens were already yielded, preserve content without crashing
        if not has_yielded:
            raise UpstreamFailure("provider_unavailable", "Stream connection broke before receiving content")


def generate_chat_title(chat_id: str, timeout: int = 5) -> str:
    """Generate smart conversation title (fast non-blocking step)."""
    url = f"{BASE_URL}/api/generate-chat-title"
    headers = dict(COMMON_HEADERS)
    headers["Content-Type"] = "application/json"
    session = get_session()
    try:
        resp = session.post(url, json={"chatId": chat_id}, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.json().get("title", "")
    except Exception:
        pass
    return ""


def ask(
    model: str,
    messages: list[dict[str, str]],
    files: list[dict[str, Any]] | None = None,
    screenshot_token: str | None = None,
    timeout: int = 600,
) -> dict[str, Any]:
    """Execute complete generation call for generate_text (up to 10 minutes)."""
    # 1. Handle file attachments
    image_token = screenshot_token
    file_context_parts = []

    if files:
        for f in files:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name", "file"))
            raw = f.get("content", "")
            is_b64 = f.get("is_base64", False)

            # Detect content bytes
            if is_b64 and isinstance(raw, str):
                try:
                    f_bytes = base64.b64decode(raw)
                except Exception:
                    f_bytes = raw.encode("utf-8")
            elif isinstance(raw, bytes):
                f_bytes = raw
            else:
                f_bytes = str(raw).encode("utf-8")

            ext = os.path.splitext(name)[1].lower()

            # Image attachment -> upload to S3 if we don't have a token yet
            if ext in (".png", ".jpg", ".jpeg", ".webp"):
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
                if not image_token:
                    image_token = upload_image_bytes(
                        img_bytes=f_bytes,
                        filename=name,
                        content_type=mime_map.get(ext, "image/png"),
                        timeout=min(30, timeout),
                    )
            elif ext in (".mp3", ".wav", ".m4a", ".ogg"):
                # Audio rejection with clear message
                raise UpstreamFailure(
                    category="bad_request",
                    message="LlamaCoder serverless backend does not support audio files. Only PNG, JPEG, and WebP images are allowed.",
                    status_code=415,
                )

            else:
                # Text/code file attachment -> inject into context prompt
                try:
                    text = f_bytes.decode("utf-8", errors="replace")
                    file_context_parts.append(f"[Attached File: {name}]\n```\n{text}\n```")
                except Exception:
                    pass

    # 2. Build synthesized prompt
    conversation_parts = []
    if file_context_parts:
        conversation_parts.append("\n\n".join(file_context_parts))

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            conversation_parts.append(f"[System Instruction]\n{content}")
        elif role == "assistant":
            conversation_parts.append(f"[Assistant]\n{content}")
        else:
            conversation_parts.append(f"[User]\n{content}")

    final_prompt = "\n\n".join(conversation_parts)

    # 3. Create chat
    resolved_model = resolve_model_name(model)
    chat_id, message_id = create_chat(
        prompt=final_prompt,
        model=resolved_model,
        screenshot_token=image_token,
        timeout=min(30, timeout),
    )

    # 4. Stream completion
    chunks = []
    for chunk in stream_completion(message_id=message_id, model=resolved_model, timeout=timeout):
        chunks.append(chunk)

    full_text = "".join(chunks)
    title = generate_chat_title(chat_id)

    return {
        "text": full_text,
        "chat_id": chat_id,
        "title": title,
    }


def analyze_vision(
    model: str,
    image_bytes: bytes,
    image_format: str = "png",
    instruction: str = "Analyze this image and describe its UI structure and code components in detail.",
    timeout: int = 60,
) -> dict[str, Any]:
    """Execute vision analysis using LlamaCoder's S3 screenshot pipeline."""
    fmt = image_format.lower().replace(".", "")
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    content_type = mime_map.get(fmt, "image/png")

    token = upload_image_bytes(
        img_bytes=image_bytes,
        filename=f"input.{fmt}",
        content_type=content_type,
        timeout=min(30, timeout),
    )

    resolved_model = resolve_model_name(model)
    chat_id, message_id = create_chat(
        prompt=instruction,
        model=resolved_model,
        screenshot_token=token,
        timeout=min(30, timeout),
    )

    chunks = []
    for chunk in stream_completion(message_id=message_id, model=resolved_model, timeout=timeout):
        chunks.append(chunk)

    full_text = "".join(chunks)
    return {
        "text": full_text,
        "chat_id": chat_id,
    }


def health_check(timeout: int = 10) -> bool:
    """Verify LlamaCoder upstream service reachability."""
    try:
        r = requests.get(BASE_URL, headers=COMMON_HEADERS, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False
