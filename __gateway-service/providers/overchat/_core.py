"""Overchat AI Internal Provider Implementation — Layer 1.

Autonomous platform-mode engine:
- Zero-Browser HTTP requests with Android OkHttp 4.12.0 mobile emulation.
- Multi-Model Free Suite:
    * gpt-6-luna (Flagship reasoning & multimodal)
    * gpt-5.6-luna (Deep reasoning & intelligence)
    * gemini-3.8-flash (Google Gemini 3.8 Flash high-speed multimodal)
    * claude-4.5-haiku (Anthropic Claude 4.5 Haiku intelligence)
    * deepseek-v3.2 (DeepSeek v3.2 Non-Thinking coding model)
    * gpt-5-mini (OpenAI GPT-5 Mini high efficiency)
    * gpt-5-nano (Overchat instant chat engine)
    * gpt-4.1-nano (OpenAI GPT-4.1 Nano text generator)
- Anonymous User Auth via /v1/auth/me and ephemeral device identity rotation.
- Universal SSE Streaming Buffer resistant to UTF-8 multi-byte chunk splitting.
- Built-in live web search capability support.
- Multimodal Vision Analysis (Amazon S3 upload via /v1/chat/upload).
- Audio Transcription Speech-to-Text via /v1/transcript.
- Hermetic test transport support for isolated unit testing.
- Strict isolation: zero credential or token leakage.
"""

from __future__ import annotations

import json
import random
import string
import time
import uuid
from typing import Any

import httpx

MODEL_REGISTRY: dict[str, dict[str, str]] = {
    "gpt-6-luna": {
        "persona_id": "gpt-5-6-luna",
        "upstream_model": "gpt-6-luna",
        "fallback": "gpt-5.6-luna",
    },
    "gpt-5.6-luna": {
        "persona_id": "gpt-5-6-luna",
        "upstream_model": "gpt-5.6-luna",
        "fallback": "gpt-6-luna",
    },
    "gemini-3.8-flash": {
        "persona_id": "gemini-3-5-flash",
        "upstream_model": "google/gemini-3.8-flash",
        "fallback": "gpt-6-luna",
    },
    "claude-4.5-haiku": {
        "persona_id": "claude-haiku-4-5-landing",
        "upstream_model": "claude-haiku-4-5-20251001",
        "fallback": "gpt-6-luna",
    },
    "deepseek-v3.2": {
        "persona_id": "deepseek-v-3-2-landing",
        "upstream_model": "deepseek/deepseek-non-thinking-v3.2-exp",
        "fallback": "gpt-6-luna",
    },
    "gpt-5-mini": {
        "persona_id": "code-detector-landing",
        "upstream_model": "gpt-5-mini",
        "fallback": "gpt-5-nano",
    },
    "gpt-5-nano": {
        "persona_id": "auto-model",
        "upstream_model": "gpt-5-nano",
        "fallback": "gpt-4.1-nano",
    },
    "gpt-4.1-nano": {
        "persona_id": "ai-text-generator",
        "upstream_model": "openai/gpt-4.1-nano",
        "fallback": "gpt-5-nano",
    },
}

MODEL_ALIASES: dict[str, str] = {
    "google/gemini-3.8-flash": "gemini-3.8-flash",
    "gemini-3-5-flash": "gemini-3.8-flash",
    "claude-haiku-4-5-20251001": "claude-4.5-haiku",
    "claude-haiku-4-5": "claude-4.5-haiku",
    "deepseek/deepseek-non-thinking-v3.2-exp": "deepseek-v3.2",
    "deepseek-v-3-2": "deepseek-v3.2",
    "openai/gpt-4.1-nano": "gpt-4.1-nano",
}

ALLOWED_MODELS = set(MODEL_REGISTRY.keys()) | set(MODEL_ALIASES.keys())
DEFAULT_MODEL = "gpt-6-luna"
FALLBACK_MODEL = "gpt-5.6-luna"
BASE_URL = "https://api.overchat.ai"

_default_transport: httpx.BaseTransport | None = None


class UpstreamFailure(Exception):
    """Normalized internal failure for Layer 1 operations."""

    def __init__(
        self,
        category: str,
        message: str,
        provider_code: str | None = None,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.provider_code = provider_code
        self.retry_after_ms = retry_after_ms


def set_default_transport(transport: httpx.BaseTransport | None) -> None:
    """Testing hook for injecting mock HTTP transports hermetically."""
    global _default_transport
    _default_transport = transport


def _generate_fake_ip() -> str:
    """Generate spoofed IP address for mobile headers."""
    return f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"


def _build_mobile_headers() -> dict[str, str]:
    """Construct Android OkHttp 4.12.0 headers matching official app fingerprint."""
    fake_ip = _generate_fake_ip()
    random_device_uuid = "".join(random.choices(string.ascii_lowercase + string.digits, k=16))

    return {
        "User-Agent": "okhttp/4.12.0",
        "Accept": "application/json, text/plain, */*",
        "X-Forwarded-For": fake_ip,
        "X-Real-IP": fake_ip,
        "Client-IP": fake_ip,
        "x-device-platform": "android",
        "x-device-version": "12",
        "x-device-brand": "samsung",
        "x-device-id": "exynos9611",
        "x-device-uuid": random_device_uuid,
        "x-app-build-number": "80",
        "x-app-version": "1.0",
        "x-app-default-lang": "ar",
    }


def _parse_sse_delta(data_json: dict[str, Any]) -> str:
    """Extract streaming delta from Overchat event format or OpenAI delta format."""
    if "data" in data_json and isinstance(data_json["data"], dict):
        d = data_json["data"]
        return d.get("delta", "") or d.get("text", "") or d.get("content", "") or ""

    if "choices" in data_json and len(data_json["choices"]) > 0:
        c = data_json["choices"][0]
        if "delta" in c and isinstance(c["delta"], dict):
            return c["delta"].get("content", "") or c["delta"].get("reasoning_content", "") or ""
        if "text" in c:
            return str(c.get("text", ""))

    return ""


def ask(
    model: str,
    messages: list[dict[str, str]],
    session_id: str | None = None,
    timeout_ms: int | None = None,
    web_search: bool = True,
    client: httpx.Client | None = None,
) -> tuple[str, str, dict[str, int], int]:
    """Execute text generation request against Overchat API across all supported free models.

    Returns:
        (text, finish_reason, usage_dict, latency_ms)
    """
    canonical_model = MODEL_ALIASES.get(model, model)
    if canonical_model not in MODEL_REGISTRY:
        raise UpstreamFailure(
            "model_unavailable",
            f"Overchat model '{model}' is not supported. Supported: {sorted(MODEL_REGISTRY.keys())}",
            provider_code="INVALID_MODEL",
        )

    t_start = time.perf_counter()
    timeout_sec = (timeout_ms / 1000.0) if timeout_ms else 90.0

    headers = _build_mobile_headers()
    headers["Content-Type"] = "application/json"

    close_client = False
    if client is None:
        client = httpx.Client(
            transport=_default_transport,
            timeout=httpx.Timeout(timeout_sec, connect=15.0),
        )
        close_client = True

    try:
        # 1. Anonymous auth to obtain fresh guest identity
        try:
            r_auth = client.get(f"{BASE_URL}/v1/auth/me", headers=headers)
        except httpx.TimeoutException as exc:
            raise UpstreamFailure("timeout", "Overchat auth endpoint timed out") from exc
        except httpx.RequestError as exc:
            raise UpstreamFailure("provider_unavailable", f"Overchat auth connection failed: {exc}") from exc

        if r_auth.status_code in (401, 403):
            raise UpstreamFailure("auth_expired", "Overchat authentication rejected", provider_code=str(r_auth.status_code))
        if r_auth.status_code == 429:
            raise UpstreamFailure("rate_limited", "Overchat auth rate limited", provider_code="429", retry_after_ms=10000)
        if r_auth.status_code not in (200, 201):
            raise UpstreamFailure("provider_unavailable", f"Overchat auth returned HTTP {r_auth.status_code}", provider_code=str(r_auth.status_code))

        try:
            user_data = r_auth.json()
            user_id = user_data.get("id")
        except Exception as exc:
            raise UpstreamFailure("provider_unavailable", "Invalid auth JSON response") from exc

        if not user_id:
            raise UpstreamFailure("provider_unavailable", "Missing user ID in auth response")

        # 2. Init chat session (chatId must strictly be a valid UUID)
        chat_uuid = None
        if session_id:
            try:
                uuid.UUID(str(session_id))
                chat_uuid = str(session_id)
            except ValueError:
                chat_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(session_id)))
        if not chat_uuid:
            chat_uuid = str(uuid.uuid4())

        cfg = MODEL_REGISTRY[canonical_model]
        primary_persona = cfg["persona_id"]

        try:
            client.post(
                f"{BASE_URL}/v1/chat/{user_id}",
                headers=headers,
                json={
                    "personaId": primary_persona,
                    "firstBotMessageHidden": True,
                    "chatUuid": chat_uuid,
                },
            )
        except Exception:
            pass  # Non-fatal initialization

        # 3. Format messages payload
        api_messages = []
        for msg in messages:
            api_messages.append({
                "id": str(uuid.uuid4()),
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # 4. Stream chat response with primary model, fallback on failure
        models_to_try = [canonical_model]
        fallback_target = cfg.get("fallback")
        if fallback_target and fallback_target in MODEL_REGISTRY and fallback_target != canonical_model:
            models_to_try.append(fallback_target)

        full_text = ""
        success = False

        for target_key in models_to_try:
            target_cfg = MODEL_REGISTRY[target_key]
            target_persona = target_cfg["persona_id"]
            target_upstream = target_cfg["upstream_model"]

            req_body = {
                "chatId": chat_uuid,
                "model": target_upstream,
                "personaId": target_persona,
                "messages": api_messages,
                "webSearch": web_search,
                "stream": True,
                "temperature": 0.5,
                "top_p": 0.95,
                "max_tokens": 4000,
                "frequency_penalty": 0,
                "presence_penalty": 0,
            }

            try:
                with client.stream("POST", f"{BASE_URL}/v2/chat/responses", headers=headers, json=req_body) as response:
                    if response.status_code in (200, 201):
                        collected_chunks = []
                        buf = ""
                        for chunk in response.iter_bytes():
                            if not chunk:
                                continue
                            buf += chunk.decode("utf-8", errors="replace")
                            lines = buf.split("\n")
                            buf = lines.pop()
                            for line in lines:
                                line = line.strip()
                                if not line or not line.startswith("data: "):
                                    continue
                                raw_data = line[6:].strip()
                                if raw_data == "[DONE]":
                                    break
                                try:
                                    chunk_json = json.loads(raw_data)
                                    delta = _parse_sse_delta(chunk_json)
                                    if delta:
                                        collected_chunks.append(delta)
                                except Exception:
                                    pass
                        full_text = "".join(collected_chunks).strip()
                        if full_text:
                            success = True
                            break
                    elif response.status_code == 429:
                        raise UpstreamFailure("rate_limited", "Overchat rate limited", provider_code="429", retry_after_ms=15000)
                    elif response.status_code in (401, 403):
                        raise UpstreamFailure("auth_expired", "Overchat session expired or forbidden", provider_code=str(response.status_code))
            except UpstreamFailure:
                raise
            except httpx.TimeoutException as exc:
                if target_key == models_to_try[-1]:
                    raise UpstreamFailure("timeout", "Overchat request timed out") from exc
            except httpx.RequestError as exc:
                if target_key == models_to_try[-1]:
                    raise UpstreamFailure("provider_unavailable", f"Overchat connection failed: {exc}") from exc

        if not success or not full_text:
            raise UpstreamFailure("provider_unavailable", "Overchat returned empty response or all model fallbacks failed")

        t_elapsed = time.perf_counter() - t_start
        latency_ms = int(t_elapsed * 1000)

        # Estimate usage
        approx_in = sum(len(m.get("content", "")) for m in messages) // 4
        approx_out = len(full_text) // 4
        usage = {
            "input_tokens": max(approx_in, 1),
            "output_tokens": max(approx_out, 1),
            "units": 1,
        }

        return full_text, "stop", usage, latency_ms

    finally:
        if close_client:
            client.close()


def upload_attachment(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    timeout_sec: float = 30.0,
    client: httpx.Client | None = None,
) -> str:
    """Upload media file to Overchat S3 storage via /v1/chat/upload.

    Returns:
        S3 public link URL
    """
    headers = _build_mobile_headers()
    close_client = False
    if client is None:
        client = httpx.Client(
            transport=_default_transport,
            timeout=httpx.Timeout(timeout_sec, connect=15.0),
        )
        close_client = True

    try:
        files = {"file": (filename, file_bytes, mime_type)}
        try:
            r = client.post(f"{BASE_URL}/v1/chat/upload", headers=headers, files=files)
        except httpx.TimeoutException as exc:
            raise UpstreamFailure("timeout", "Attachment upload timed out") from exc
        except httpx.RequestError as exc:
            raise UpstreamFailure("provider_unavailable", f"Attachment upload failed: {exc}") from exc

        if r.status_code in (401, 403):
            raise UpstreamFailure("auth_expired", "Attachment upload unauthorized", provider_code=str(r.status_code))
        if r.status_code == 429:
            raise UpstreamFailure("rate_limited", "Attachment upload rate limited", provider_code="429", retry_after_ms=10000)
        if r.status_code not in (200, 201):
            raise UpstreamFailure("provider_unavailable", f"Attachment upload HTTP {r.status_code}", provider_code=str(r.status_code))

        try:
            data = r.json()
            link = data.get("link")
        except Exception as exc:
            raise UpstreamFailure("provider_unavailable", "Invalid upload JSON response") from exc

        if not link:
            raise UpstreamFailure("provider_unavailable", "Missing link in upload response")

        return link
    finally:
        if close_client:
            client.close()


def analyze_vision(
    model: str,
    image_bytes: bytes,
    image_format: str,
    instruction: str,
    session_id: str | None = None,
    timeout_ms: int | None = None,
    client: httpx.Client | None = None,
) -> tuple[str, dict[str, int], int]:
    """Execute vision analysis on image bytes with instructions.

    Returns:
        (text, usage_dict, latency_ms)
    """
    t_start = time.perf_counter()
    timeout_sec = (timeout_ms / 1000.0) if timeout_ms else 90.0

    close_client = False
    if client is None:
        client = httpx.Client(
            transport=_default_transport,
            timeout=httpx.Timeout(timeout_sec, connect=15.0),
        )
        close_client = True

    try:
        # 1. Upload image to S3
        filename = f"image.{image_format}"
        mime = f"image/{image_format}"
        image_url = upload_attachment(image_bytes, filename, mime, timeout_sec=30.0, client=client)

        # 2. Call ask with image attachment metadata and links
        canonical_model = MODEL_ALIASES.get(model, model)
        if canonical_model not in MODEL_REGISTRY:
            canonical_model = DEFAULT_MODEL
        cfg = MODEL_REGISTRY[canonical_model]
        persona_id = cfg["persona_id"]
        upstream_model = cfg["upstream_model"]

        headers = _build_mobile_headers()
        headers["Content-Type"] = "application/json"

        # Auth
        r_auth = client.get(f"{BASE_URL}/v1/auth/me", headers=headers)
        if r_auth.status_code not in (200, 201):
            raise UpstreamFailure("provider_unavailable", "Auth failed during vision call")
        user_id = r_auth.json().get("id")

        chat_uuid = None
        if session_id:
            try:
                uuid.UUID(str(session_id))
                chat_uuid = str(session_id)
            except ValueError:
                chat_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(session_id)))
        if not chat_uuid:
            chat_uuid = str(uuid.uuid4())

        try:
            client.post(
                f"{BASE_URL}/v1/chat/{user_id}",
                headers=headers,
                json={"personaId": persona_id, "firstBotMessageHidden": True, "chatUuid": chat_uuid},
            )
        except Exception:
            pass

        req_body = {
            "chatId": chat_uuid,
            "model": upstream_model,
            "personaId": persona_id,
            "messages": [
                {
                    "id": str(uuid.uuid4()),
                    "role": "user",
                    "content": instruction,
                    "metadata": {
                        "files": [{"link": image_url, "path": filename}]
                    },
                }
            ],
            "links": [image_url],
            "webSearch": False,
            "stream": True,
            "temperature": 0.5,
            "max_tokens": 4000,
        }

        full_text = ""
        with client.stream("POST", f"{BASE_URL}/v2/chat/responses", headers=headers, json=req_body) as response:
            if response.status_code in (200, 201):
                collected = []
                buf = ""
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    buf += chunk.decode("utf-8", errors="replace")
                    lines = buf.split("\n")
                    buf = lines.pop()
                    for line in lines:
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            cj = json.loads(raw)
                            delta = _parse_sse_delta(cj)
                            if delta:
                                collected.append(delta)
                        except Exception:
                            pass
                full_text = "".join(collected).strip()
            elif response.status_code == 429:
                raise UpstreamFailure("rate_limited", "Vision rate limited", provider_code="429")
            else:
                raise UpstreamFailure("provider_unavailable", f"Vision chat HTTP {response.status_code}")

        if not full_text:
            raise UpstreamFailure("provider_unavailable", "Empty vision analysis response")

        t_elapsed = time.perf_counter() - t_start
        latency_ms = int(t_elapsed * 1000)
        usage = {
            "input_tokens": max(len(instruction) // 4 + 800, 1),
            "output_tokens": max(len(full_text) // 4, 1),
            "units": 1,
        }
        return full_text, usage, latency_ms

    finally:
        if close_client:
            client.close()


def transcribe_audio(
    audio_bytes: bytes,
    audio_format: str = "wav",
    timeout_ms: int | None = None,
    client: httpx.Client | None = None,
) -> tuple[str, str | None, dict[str, int], int]:
    """Execute speech-to-text audio transcription via Whisper endpoint.

    Returns:
        (text, language, usage_dict, latency_ms)
    """
    t_start = time.perf_counter()
    timeout_sec = (timeout_ms / 1000.0) if timeout_ms else 60.0
    headers = _build_mobile_headers()

    close_client = False
    if client is None:
        client = httpx.Client(
            transport=_default_transport,
            timeout=httpx.Timeout(timeout_sec, connect=15.0),
        )
        close_client = True

    try:
        mime = f"audio/{audio_format}" if audio_format else "audio/ogg"
        files = {"file": (f"audio.{audio_format}", audio_bytes, mime)}
        try:
            r = client.post(f"{BASE_URL}/v1/transcript", headers=headers, files=files)
        except httpx.TimeoutException as exc:
            raise UpstreamFailure("timeout", "Audio transcription timed out") from exc
        except httpx.RequestError as exc:
            raise UpstreamFailure("provider_unavailable", f"Audio transcription failed: {exc}") from exc

        if r.status_code in (401, 403):
            raise UpstreamFailure("auth_expired", "Audio transcription unauthorized", provider_code=str(r.status_code))
        if r.status_code == 429:
            raise UpstreamFailure("rate_limited", "Audio transcription rate limited", provider_code="429", retry_after_ms=10000)
        if r.status_code not in (200, 201):
            raise UpstreamFailure("provider_unavailable", f"Audio transcription HTTP {r.status_code}", provider_code=str(r.status_code))

        try:
            data = r.json()
            text = (data.get("text") or "").strip()
            lang = data.get("language")
        except Exception as exc:
            raise UpstreamFailure("provider_unavailable", "Invalid transcription JSON response") from exc

        if not text:
            raise UpstreamFailure("provider_unavailable", "Empty audio transcription output")

        t_elapsed = time.perf_counter() - t_start
        latency_ms = int(t_elapsed * 1000)
        usage = {"units": 1}
        return text, lang, usage, latency_ms

    finally:
        if close_client:
            client.close()
