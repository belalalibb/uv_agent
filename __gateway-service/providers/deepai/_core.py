"""DeepAI Internal Provider Implementation — Layer 1.

Autonomous guest/platform-mode engine:
- Dynamic IslandKey calculation (reverse-engineered MD5 hashing).
- Chat execution via hacking_is_a_serious_crime with direct text + async thinking polling.
- File and image attachments upload via chat_attachments/upload.
- Speech-to-text transcription via speech_to_text.
- Zero credential leakage, isolated exception taxonomy.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
import uuid
from typing import Any

import requests

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)

DEEPAI_BASE_URL = "https://api.deepai.org"
SALT = "hackers_become_a_little_stinkier_every_time_they_hack"


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


def _md5_reversed(s: str) -> str:
    """MD5 hash of utf-8 bytes reversed (replicates deepai client JS)."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()[::-1]


def generate_island_key(user_agent: str = DEFAULT_USER_AGENT) -> str:
    """Generate dynamic valid tryit- API key replicating generateIslandKey()."""
    myrandomstr = str(round(random.random() * 100_000_000_000))
    h1 = _md5_reversed(user_agent + myrandomstr + SALT)
    h2 = _md5_reversed(user_agent + h1)
    h3 = _md5_reversed(user_agent + h2)
    return f"tryit-{myrandomstr}-{h3}"


def upload_attachment(
    file_bytes: bytes,
    filename: str = "upload.bin",
    content_type: str = "application/octet-stream",
    timeout: int = 60,
) -> dict[str, Any]:
    """Upload a file or image attachment to DeepAI.
    
    Accepts any file extension (.py, .md, .txt, .json, .png, .jpg, .webp, .pdf, etc.).
    Returns attachment dict containing 'uuid', 'download_url', etc.
    """
    headers = {
        "origin": "https://deepai.org",
        "referer": "https://deepai.org/",
        "user-agent": DEFAULT_USER_AGENT,
        "accept": "*/*",
    }
    files = {
        "file": (filename, file_bytes, content_type)
    }

    try:
        resp = requests.post(
            f"{DEEPAI_BASE_URL}/chat_attachments/upload",
            headers=headers,
            files=files,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise UpstreamFailure("timeout", "DeepAI attachment upload timed out") from exc
    except requests.RequestException as exc:
        raise UpstreamFailure("provider_unavailable", f"DeepAI connection failed: {exc}") from exc

    if resp.status_code != 200:
        cat = "retryable_server_error" if resp.status_code >= 500 else "non_retryable_error"
        raise UpstreamFailure(cat, f"Attachment upload failed with HTTP {resp.status_code}", provider_code=str(resp.status_code))

    try:
        data = resp.json()
    except Exception as exc:
        raise UpstreamFailure("non_retryable_error", "DeepAI returned non-JSON attachment response") from exc

    if not data.get("success") or not data.get("attachment"):
        err_msg = data.get("error", "Unknown attachment upload failure")
        raise UpstreamFailure("non_retryable_error", f"DeepAI attachment error: {err_msg}")

    return data["attachment"]


def transcribe_audio(
    audio_bytes: bytes,
    audio_format: str = "wav",
    timeout: int = 60,
) -> dict[str, Any]:
    """Transcribe audio bytes using DeepAI speech-to-text."""
    key = generate_island_key()
    headers = {
        "api-key": key,
        "origin": "https://deepai.org",
        "user-agent": DEFAULT_USER_AGENT,
        "accept": "*/*",
    }
    mime_type = f"audio/{audio_format}"
    files = {
        "voiceRecording": (f"audio.{audio_format}", audio_bytes, mime_type)
    }

    try:
        resp = requests.post(
            f"{DEEPAI_BASE_URL}/speech_to_text",
            headers=headers,
            files=files,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise UpstreamFailure("timeout", "DeepAI audio transcription timed out") from exc
    except requests.RequestException as exc:
        raise UpstreamFailure("provider_unavailable", f"DeepAI connection failed: {exc}") from exc

    if resp.status_code == 429:
        raise UpstreamFailure("rate_limited", "DeepAI audio transcription rate limited", provider_code="429")
    if resp.status_code in (401, 403):
        raise UpstreamFailure("invalid_credential", "DeepAI authentication rejected", provider_code=str(resp.status_code))
    if resp.status_code != 200:
        cat = "retryable_server_error" if resp.status_code >= 500 else "non_retryable_error"
        raise UpstreamFailure(cat, f"Audio transcription failed with HTTP {resp.status_code}", provider_code=str(resp.status_code))

    try:
        data = resp.json()
        text = data.get("text", "")
        return {"text": text, "language": None}
    except Exception as exc:
        raise UpstreamFailure("non_retryable_error", "DeepAI returned invalid JSON for speech_to_text") from exc


def ask(
    model: str,
    prompt: str | None = None,
    messages: list[dict[str, str]] | None = None,
    session_id: str | None = None,
    attachment_uuids: list[str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Send chat request to DeepAI.
    
    Handles both direct plaintext responses and async thinking tasks with polling.
    """
    if messages:
        history = messages
    elif prompt:
        history = [{"role": "user", "content": prompt}]
    else:
        history = [{"role": "user", "content": ""}]

    session_uuid = session_id or str(uuid.uuid4())
    key = generate_island_key()

    headers = {
        "api-key": key,
        "origin": "https://deepai.org",
        "user-agent": DEFAULT_USER_AGENT,
        "accept": "*/*",
    }

    files: dict[str, tuple[None, str]] = {
        "chat_style": (None, "chat"),
        "chatHistory": (None, json.dumps(history, ensure_ascii=False)),
        "model": (None, model),
        "session_uuid": (None, session_uuid),
        "hacker_is_stinky": (None, "very_stinky"),
        "enabled_tools": (None, "[]"),
    }

    if attachment_uuids:
        files["attachment_uuids"] = (None, json.dumps(attachment_uuids))

    start_time = time.time()
    try:
        resp = requests.post(
            f"{DEEPAI_BASE_URL}/hacking_is_a_serious_crime",
            headers=headers,
            files=files,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise UpstreamFailure("timeout", "DeepAI chat request timed out") from exc
    except requests.RequestException as exc:
        raise UpstreamFailure("provider_unavailable", f"DeepAI connection failed: {exc}") from exc

    if resp.status_code == 429:
        raise UpstreamFailure("rate_limited", "DeepAI rate limited", provider_code="429")
    if resp.status_code in (401, 403):
        raise UpstreamFailure("invalid_credential", "DeepAI key rejected", provider_code=str(resp.status_code))
    if resp.status_code != 200:
        cat = "retryable_server_error" if resp.status_code >= 500 else "non_retryable_error"
        raise UpstreamFailure(cat, f"DeepAI HTTP {resp.status_code}: {resp.text[:200]}", provider_code=str(resp.status_code))

    resp_text = resp.text.strip()

    # Check for async thinking task (e.g. glm-5.3-flash)
    if resp_text.startswith("{") and "task_id" in resp_text:
        try:
            task_info = json.loads(resp_text)
            task_id = task_info.get("task_id")
            if task_id:
                # Poll task status
                poll_deadline = start_time + timeout
                while time.time() < poll_deadline:
                    time.sleep(1.0)
                    poll_resp = requests.get(
                        f"{DEEPAI_BASE_URL}/check_chat_task_status",
                        params={"type": "thinking-task", "task_id": task_id},
                        headers=headers,
                        timeout=10,
                    )
                    if poll_resp.status_code == 200:
                        poll_data = poll_resp.json()
                        if poll_data.get("status") == "COMPLETED":
                            answer = poll_data.get("answer_text", "")
                            return {
                                "text": answer,
                                "session_id": session_uuid,
                                "thinking_time": poll_data.get("thinking_time"),
                            }
                        if poll_data.get("status") == "FAILED":
                            raise UpstreamFailure("non_retryable_error", "DeepAI thinking task failed")
                raise UpstreamFailure("timeout", "DeepAI thinking task timed out during polling")
        except UpstreamFailure:
            raise
        except Exception as exc:
            raise UpstreamFailure("non_retryable_error", f"Error parsing DeepAI thinking task: {exc}") from exc

    return {
        "text": resp_text,
        "session_id": session_uuid,
    }
