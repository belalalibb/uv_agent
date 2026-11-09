#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HAR TO PROVIDER AUTONOMOUS SCAFFOLDER (v2.0 Universal Core)
===========================================================
Ingests a captured HAR file of a web AI provider and scaffolds a production
Python provider package: multi-engine auth, SSE streaming, schema auto-healing,
FileLock/TokenPool resilience, and an O(n) text-only vision guard.

Pipeline:
    HarAnalyzer     single-pass evidence collection (scored, redacted)
    AnalysisResult  typed, serializable analysis summary
    ProviderScaffolder  token-based codegen with compile() validation

Redaction guarantees: endpoint URLs are stripped of query/fragments, credential
headers are never emitted, secret-looking static body fields are excluded, and
the ingestion report contains no captured secrets.

Usage:
    py -3.13 tools/har_to_provider_v2.py path/to/traffic.har --slug <slug> \
        [--out providers/<slug>] [--dry-run] [-v]

Exit codes: 0 success, 2 analysis/generation error, 130 interrupted.
"""

from __future__ import annotations

import argparse
import base64
import json
import keyword
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

BANNER = r"""
==============================================================================
  HAR -> PROVIDER AUTONOMOUS SCAFFOLDER (v2.0 Universal Edition)
  Standard: Universal Provider Blueprint v4.0
  Target SLA: raw HAR in -> production provider out in one sitting.
==============================================================================
"""

# ---------------------------------------------------------------------------
# Heuristic constants
# ---------------------------------------------------------------------------

TRACKER_DOMAINS = (
    "clarity.ms", "google-analytics.com", "googletagmanager.com", "sentry.io",
    "doubleclick.net", "facebook.net", "connect.facebook", "stats", "telemetry",
    "segment.io", "hotjar.com", "datadoghq.com", "intercom.io", "mixpanel.com",
    "amplitude.com", "posthog.com", "fullstory.com",
)

CHAT_HINTS_STRONG = ("chat/completions", "completions", "/chat", "conversation", "inference")
CHAT_HINTS_WEAK = ("generate", "ask", "message", "prompt")

OTP_SEND_HINTS = (
    "send-otp", "send_otp", "otp/send", "send-code", "send_code",
    "request-otp", "otp-request", "request-code", "send-verification",
    "verification/send", "send-verification-code",
)
OTP_VERIFY_HINTS = (
    "verify-otp", "verify_otp", "otp/verify", "verify-code", "verify_code",
    "check-otp", "otp-check", "verify/email", "verify-email-code", "check-code",
)
AUTH_PATH_HINTS = ("otp", "verify", "signup", "register", "login", "signin", "auth", "token", "session")

MODELS_HINTS = ("models", "model-list", "model_list", "model-catalog", "model_catalog", "catalog")
AUDIO_HINTS_STRONG = ("transcribe", "transcription", "speech-to-text", "speechtotext")
AUDIO_HINTS_WEAK = ("/stt", "/audio", "/speech")
UPLOAD_HINTS = ("upload", "/files", "/media", "attachment", "file-upload")

# Secrets / redaction
_BEARER_RE = re.compile(r"^Bearer\s+\S+", re.IGNORECASE)
SECRET_KEY_HINT = re.compile(r"(?i)(token|secret|password|passwd|credential|api[_-]?key|auth|session|csrf|cookie)")
JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{5,}$")
_TOKEN_KEY_RE = re.compile(r"(?i)(access[_-]?token|api[_-]?token|auth[_-]?token|id[_-]?token|jwt|bearer|api[_-]?key|session[_-]?key|token)")

BROWSER_HEADER_WHITELIST = {
    "user-agent": "User-Agent",
    "accept-language": "Accept-Language",
    "origin": "Origin",
    "referer": "Referer",
}

RESERVED_MODULE_NAMES = {
    "requests", "json", "os", "sys", "re", "time", "types", "typing", "uuid",
    "pathlib", "dataclasses", "datetime", "base64", "threading", "random",
    "html", "urllib", "http", "email", "logging", "argparse", "io", "abc",
    "enum", "string", "copy", "math", "statistics", "collections", "itertools",
    "functools", "contextlib", "traceback", "tempfile", "shutil", "glob",
    "pickle", "secrets", "hashlib", "hmac", "ssl", "socket", "asyncio",
    "subprocess", "multiprocessing", "queue", "select", "selectors",
    "mimetypes", "zipfile", "tarfile", "csv", "sqlite3", "struct", "binascii",
    "codecs", "warnings", "unittest", "configparser", "platform", "importlib",
    "signal", "weakref", "locale", "gettext", "decimal", "fractions",
}


# ---------------------------------------------------------------------------
# Analysis data model
# ---------------------------------------------------------------------------

@dataclass
class ChatSchema:
    """Dynamic wire slots inferred from the captured chat request bodies."""

    model_key: Optional[str] = None
    messages_key: Optional[str] = None
    prompt_key: Optional[str] = None
    content_key: Optional[str] = None
    role_key: Optional[str] = None
    stream_key: Optional[str] = None
    has_thinking: bool = False
    has_web_search: bool = False


@dataclass
class AnalysisResult:
    """Everything the scaffolder needs, fully redacted and serializable."""

    slug: str
    har_path: str
    base_origin: str = ""
    chat_url: str = ""
    models_url: str = ""
    audio_url: str = ""
    upload_url: str = ""
    send_otp_url: str = ""
    verify_otp_url: str = ""
    auth_mode: str = "none"                 # bearer | api_key | tempmail_otp | cookie | none
    auth_evidence: List[str] = field(default_factory=list)
    api_key_header: str = ""
    verify_email_key: str = "email"
    verify_code_key: str = "code"
    token_json_keys: List[str] = field(default_factory=list)
    discovered_models: List[str] = field(default_factory=list)
    schema: ChatSchema = field(default_factory=ChatSchema)
    static_fields: Dict[str, Any] = field(default_factory=dict)
    supports_streaming: bool = False
    delta_mode: str = "raw_text"            # openai_delta | anthropic_delta | raw_text
    response_shape: str = "unknown"
    sample_headers: Dict[str, str] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_report(self) -> Dict[str, Any]:
        return {
            "slug": self.slug,
            "har_file": Path(self.har_path).name,
            "base_origin": self.base_origin,
            "endpoints": {
                "chat": self.chat_url,
                "models": self.models_url,
                "audio": self.audio_url,
                "upload": self.upload_url,
                "otp_send": self.send_otp_url,
                "otp_verify": self.verify_otp_url,
            },
            "auth": {
                "mode": self.auth_mode,
                "evidence": self.auth_evidence,
                "api_key_header": self.api_key_header,
                "verify_email_key": self.verify_email_key,
                "verify_code_key": self.verify_code_key,
                "token_json_keys": self.token_json_keys,
            },
            "schema": dict(vars(self.schema)),
            "streaming": {
                "supported": self.supports_streaming,
                "delta_mode": self.delta_mode,
                "blocking_shape": self.response_shape,
            },
            "static_fields": self.static_fields,
            "discovered_models": self.discovered_models,
            "browser_headers": self.sample_headers,
            "counts": self.counts,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# HAR analyzer
# ---------------------------------------------------------------------------

class HarAnalyzer:
    """Single-pass HAR evidence collector with scored endpoint selection."""

    def __init__(self, har_path: str, slug: str):
        self.har_path = Path(har_path)
        self.slug = slug
        self.entries: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.counts: Dict[str, int] = {
            "entries_total": 0, "trackers_skipped": 0, "chat": 0,
            "models": 0, "audio": 0, "upload": 0,
        }
        self._origin_scores: Dict[str, int] = {}
        self._origin_posts: Dict[str, int] = {}
        self._chat_candidates: List[Dict[str, Any]] = []
        self._chat_bodies: List[Dict[str, Any]] = []
        self._models_candidates: List[Dict[str, Any]] = []
        self._audio_candidates: List[Dict[str, Any]] = []
        self._upload_candidates: List[Dict[str, Any]] = []
        self._otp_send_candidates: List[Dict[str, Any]] = []
        self._otp_verify_candidates: List[Dict[str, Any]] = []
        self._auth_response_bodies: List[Any] = []
        self._discovered_models: Set[str] = set()
        self._sample_headers: Dict[str, str] = {}
        self._bearer_sample = False
        self._apikey_header = ""
        self._cookie_sample = False

    # -- public API ---------------------------------------------------------

    def analyze(self) -> AnalysisResult:
        if not self.har_path.is_file():
            raise FileNotFoundError(f"HAR file not found: {self.har_path}")
        try:
            with self.har_path.open("r", encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid HAR JSON in {self.har_path}: {exc}") from exc
        self.entries = data.get("log", {}).get("entries", []) or []
        self.counts["entries_total"] = len(self.entries)
        if not self.entries:
            raise ValueError("HAR file contains no entries under log.entries")
        for entry in self.entries:
            self._process_entry(entry)
        return self._resolve()

    # -- per-entry processing ------------------------------------------------

    def _process_entry(self, entry: Dict[str, Any]) -> None:
        request = entry.get("request") or {}
        response = entry.get("response") or {}
        url = request.get("url") or ""
        if not url.startswith("http"):
            return
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return
        if self._is_tracker(host):
            self.counts["trackers_skipped"] += 1
            return

        method = (request.get("method") or "GET").upper()
        path = parsed.path.lower()
        headers = self._header_map(request.get("headers") or [])
        response_headers = self._header_map(response.get("headers") or [])
        content_type = response_headers.get("content-type", "").lower()
        body_obj, body_is_json = self._request_json(request)
        response_obj, response_is_json = self._response_json(response, content_type)

        self._score_origin(parsed, method, body_is_json)
        self._capture_browser_headers(request)
        self._capture_auth_evidence(headers, response_headers)

        chat_score = self._score_chat(method, path, body_is_json, content_type)
        if chat_score:
            self.counts["chat"] += 1
            self._chat_candidates.append({
                "score": chat_score, "url": url, "host": host,
                "request": request, "response": response, "body": body_obj,
            })
            if isinstance(body_obj, dict):
                self._chat_bodies.append(body_obj)

        if self._looks_like_models(path):
            self.counts["models"] += 1
            self._models_candidates.append({
                "url": url, "host": host, "response_is_json": response_is_json,
            })
            if response_is_json and response_obj is not None:
                self._harvest_catalog(response_obj)

        if self._score_audio(method, path, request):
            self.counts["audio"] += 1
            self._audio_candidates.append({"url": url, "host": host})

        if self._score_upload(method, path, request):
            self.counts["upload"] += 1
            self._upload_candidates.append({"url": url, "host": host})

        if method == "POST":
            if any(hint in path for hint in OTP_SEND_HINTS):
                self._otp_send_candidates.append({"url": url, "host": host, "body": body_obj})
            if any(hint in path for hint in OTP_VERIFY_HINTS):
                self._otp_verify_candidates.append({"url": url, "host": host, "body": body_obj})
            if any(hint in path for hint in AUTH_PATH_HINTS):
                if response_is_json and isinstance(response_obj, (dict, list)):
                    self._auth_response_bodies.append(response_obj)

        if isinstance(body_obj, dict):
            self._harvest_models(body_obj)

    # -- classification heuristics -------------------------------------------

    @staticmethod
    def _is_tracker(host: str) -> bool:
        return any(marker in host for marker in TRACKER_DOMAINS)

    def _score_origin(self, parsed: Any, method: str, body_is_json: bool) -> None:
        host = parsed.netloc.lower()
        compact = re.sub(r"[^a-z0-9]", "", host)
        compact_slug = re.sub(r"[^a-z0-9]", "", self.slug)
        score = 1 if parsed.scheme == "https" else 0
        if compact_slug and compact_slug in compact:
            score += 3
        else:
            tokens = [t for t in self.slug.split("_") if len(t) >= 4]
            score += min(2, sum(1 for t in tokens if t in compact))
        if compact.startswith("api"):
            score += 2
        elif "api" in compact:
            score += 1
        if method == "POST" and body_is_json:
            score += 1
            self._origin_posts[host] = self._origin_posts.get(host, 0) + 1
        self._origin_scores[host] = self._origin_scores.get(host, 0) + score

    @staticmethod
    def _score_chat(method: str, path: str, body_is_json: bool, content_type: str) -> int:
        if method != "POST":
            return 0
        score = sum(4 for hint in CHAT_HINTS_STRONG if hint in path)
        score += sum(1 for hint in CHAT_HINTS_WEAK if hint in path)
        if body_is_json:
            score += 2
        if "json" in content_type:
            score += 1
        if "event-stream" in content_type:
            score += 2
        return score

    @staticmethod
    def _looks_like_models(path: str) -> bool:
        return any(hint in path for hint in MODELS_HINTS)

    def _score_audio(self, method: str, path: str, request: Dict[str, Any]) -> int:
        if method != "POST":
            return 0
        score = sum(4 for hint in AUDIO_HINTS_STRONG if hint in path)
        score += sum(2 for hint in AUDIO_HINTS_WEAK if hint in path)
        if score and self._is_multipart(request):
            score += 2
        return score if score >= 4 else 0

    def _score_upload(self, method: str, path: str, request: Dict[str, Any]) -> int:
        if method != "POST":
            return 0
        score = 2 if any(hint in path for hint in UPLOAD_HINTS) else 0
        if score and self._is_multipart(request):
            score += 2
        return score if score >= 4 else 0

    @staticmethod
    def _is_multipart(request: Dict[str, Any]) -> bool:
        post_data = request.get("postData") or {}
        mime = (post_data.get("mimeType") or "").lower()
        if "multipart" in mime:
            return True
        return bool(post_data.get("params"))

    # -- evidence capture ------------------------------------------------------

    def _capture_auth_evidence(self, headers: Dict[str, str], response_headers: Dict[str, str]) -> None:
        if _BEARER_RE.match(headers.get("authorization", "")):
            self._bearer_sample = True
        if not self._apikey_header:
            for name in ("x-api-key", "api-key", "x-auth-token", "x-goog-api-key", "x-api-token"):
                if headers.get(name):
                    self._apikey_header = name
                    break
        if headers.get("cookie") or response_headers.get("set-cookie"):
            self._cookie_sample = True

    def _capture_browser_headers(self, request: Dict[str, Any]) -> None:
        if self._sample_headers:
            return
        for header in request.get("headers") or []:
            name = (header.get("name") or "").lower()
            if name in BROWSER_HEADER_WHITELIST:
                value = (header.get("value") or "").strip()
                if name == "referer":
                    value = self._clean_url(value)
                self._sample_headers[BROWSER_HEADER_WHITELIST[name]] = value

    # -- decoding helpers -------------------------------------------------------

    @staticmethod
    def _header_map(headers: List[Dict[str, str]]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for header in headers or []:
            name = (header.get("name") or "").strip().lower()
            if name:
                result[name] = header.get("value") or ""
        return result

    @staticmethod
    def _decode_content(content: Dict[str, Any]) -> str:
        text = content.get("text") or ""
        if not isinstance(text, str):
            return ""
        if content.get("encoding") == "base64":
            try:
                return base64.b64decode(text).decode("utf-8", "replace")
            except Exception:
                return ""
        return text

    def _request_json(self, request: Dict[str, Any]) -> Tuple[Optional[Any], bool]:
        text = self._decode_content(request.get("postData") or {})
        if not text or not text.lstrip().startswith(("{", "[")):
            return None, False
        try:
            return json.loads(text), True
        except ValueError:
            return None, False

    def _response_json(self, response: Dict[str, Any], content_type: str) -> Tuple[Optional[Any], bool]:
        text = self._decode_content(response.get("content") or {})
        if not text:
            return None, False
        if not ("json" in content_type or text.lstrip().startswith(("{", "["))):
            return None, False
        try:
            return json.loads(text), True
        except ValueError:
            return None, False

    @staticmethod
    def _clean_url(url: str) -> str:
        """Strip query string and fragment: captured URLs may embed apikeys."""
        parsed = urlparse(url)
        if not parsed.scheme:
            return url.split("?", 1)[0].split("#", 1)[0]
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    # -- model discovery ---------------------------------------------------------

    def _harvest_models(self, obj: Any, depth: int = 0) -> None:
        if depth > 3 or len(self._discovered_models) >= 64:
            return
        if isinstance(obj, dict):
            for key in ("model", "model_id", "modelId", "model_name", "ai_name", "engine", "model_slug"):
                value = obj.get(key)
                if isinstance(value, str) and 1 <= len(value) <= 120:
                    self._discovered_models.add(value)
            for value in obj.values():
                self._harvest_models(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                self._harvest_models(item, depth + 1)

    def _harvest_catalog(self, obj: Any, depth: int = 0) -> None:
        if depth > 4 or len(self._discovered_models) >= 64:
            return
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and key in ("id", "name", "model", "slug", "model_name"):
                    if 1 <= len(value) <= 120:
                        self._discovered_models.add(value)
                elif isinstance(value, (dict, list)):
                    self._harvest_catalog(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str):
                    if 1 <= len(item) <= 120:
                        self._discovered_models.add(item)
                else:
                    self._harvest_catalog(item, depth + 1)

    # -- schema introspection ------------------------------------------------------

    def _introspect_schema(self, body: Optional[Dict[str, Any]]) -> ChatSchema:
        schema = ChatSchema()
        if not isinstance(body, dict):
            return schema
        for key in ("model", "model_id", "modelId", "model_name", "ai_name", "engine", "model_slug"):
            if isinstance(body.get(key), str):
                schema.model_key = key
                break
        for key in ("messages", "conversation", "history", "chat_history", "context"):
            value = body.get(key)
            if isinstance(value, list) and all(isinstance(m, (dict, str)) for m in value[:5]):
                schema.messages_key = key
                break
        for key in ("prompt", "input", "question", "query", "message", "text"):
            if isinstance(body.get(key), str):
                schema.prompt_key = key
                break
        first_message: Optional[Dict[str, Any]] = None
        if schema.messages_key:
            for message in body[schema.messages_key]:
                if isinstance(message, dict):
                    first_message = message
                    break
        if isinstance(first_message, dict):
            for key in ("content", "text", "message", "value", "parts"):
                if key in first_message:
                    schema.content_key = key
                    break
            for key in ("role", "author", "sender"):
                if key in first_message:
                    schema.role_key = key
                    break
        for key in ("stream", "is_stream", "streaming"):
            if isinstance(body.get(key), bool):
                schema.stream_key = key
                break
        schema.has_thinking = any(re.search(r"(?i)think|reasoning", k) for k in body)
        schema.has_web_search = any(re.search(r"(?i)web[_-]?search|search[_-]?web|browsing", k) for k in body)
        return schema

    def _contains_secret(self, value: Any, depth: int = 0) -> bool:
        if depth > 4:
            return False
        if isinstance(value, str):
            return bool(JWT_RE.match(value))
        if isinstance(value, dict):
            for key, nested in value.items():
                if SECRET_KEY_HINT.search(str(key)) and isinstance(nested, str) and len(nested) >= 12:
                    return True
                if self._contains_secret(nested, depth + 1):
                    return True
        elif isinstance(value, list):
            return any(self._contains_secret(item, depth + 1) for item in value)
        return False

    def _build_static_fields(self, body: Optional[Dict[str, Any]], schema: ChatSchema) -> Dict[str, Any]:
        if not isinstance(body, dict):
            return {}
        reserved = {k for k in (schema.model_key, schema.messages_key, schema.prompt_key, schema.stream_key) if k}
        static: Dict[str, Any] = {}
        for key, value in body.items():
            if key in reserved:
                continue
            if SECRET_KEY_HINT.search(key) or self._contains_secret(value):
                self.warnings.append(f"static body key '{key}' excluded (credential-bearing)")
                continue
            if isinstance(value, str) and len(value) >= 512:
                self.warnings.append(f"static body key '{key}' excluded (oversized value)")
                continue
            try:
                encoded = json.dumps(value, ensure_ascii=True, allow_nan=False)
            except (TypeError, ValueError):
                self.warnings.append(f"static body key '{key}' excluded (non-JSON value)")
                continue
            if len(encoded) > 4096:
                self.warnings.append(f"static body key '{key}' excluded (value too large: {len(encoded)} chars)")
                continue
            static[key] = value
        return static

    def _introspect_response(self, response: Dict[str, Any]) -> Tuple[bool, str, str]:
        headers = self._header_map(response.get("headers") or [])
        content_type = (headers.get("content-type") or "").lower()
        text = self._decode_content(response.get("content") or {})
        supports_streaming = "text/event-stream" in content_type
        if not supports_streaming and text:
            data_lines = re.findall(r"(?m)^data:\s", text)
            if len(data_lines) >= 2 or "data: [DONE]" in text:
                supports_streaming = True
        delta_mode, shape = "raw_text", "unknown"
        if supports_streaming and text:
            first_chunk: Optional[Dict[str, Any]] = None
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("data:"):
                    payload = stripped[5:].strip()
                    if payload and payload != "[DONE]":
                        try:
                            loaded = json.loads(payload)
                        except ValueError:
                            loaded = None
                        if isinstance(loaded, dict):
                            first_chunk = loaded
                            break
            delta_mode = self._classify_delta(first_chunk)
            shape = "sse"
        elif text:
            try:
                body = json.loads(text)
            except ValueError:
                body = None
            if isinstance(body, dict):
                shape = self._classify_blocking(body)
        return supports_streaming, delta_mode, shape

    @staticmethod
    def _classify_delta(chunk: Optional[Dict[str, Any]]) -> str:
        if not isinstance(chunk, dict):
            return "raw_text"
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta")
            if isinstance(delta, dict) and "content" in delta:
                return "openai_delta"
        delta = chunk.get("delta")
        if isinstance(delta, dict) and "text" in delta:
            return "anthropic_delta"
        return "raw_text"

    @staticmethod
    def _classify_blocking(body: Dict[str, Any]) -> str:
        choices = body.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict) and "content" in message:
                return "openai_message"
        content = body.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict) and "text" in content[0]:
            return "anthropic_message"
        return "generic"

    def _harvest_token_keys(self) -> List[str]:
        keys: List[str] = []

        def walk(node: Any, depth: int) -> None:
            if depth > 4 or len(keys) >= 8:
                return
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = key.lower()
                    if (
                        isinstance(value, str)
                        and len(value) >= 16
                        and not any(ch.isspace() for ch in value)
                        and _TOKEN_KEY_RE.search(lowered)
                        and "csrf" not in lowered
                        and key not in keys
                    ):
                        keys.append(key)
                    else:
                        walk(value, depth + 1)
            elif isinstance(node, list):
                for item in node:
                    walk(item, depth + 1)

        for body in self._auth_response_bodies:
            walk(body, 0)
        return keys[:8]

    # -- resolution -----------------------------------------------------------------

    def _pick_origin(self) -> str:
        if not self._origin_scores:
            return ""
        best = max(self._origin_scores.items(), key=lambda kv: (kv[1], self._origin_posts.get(kv[0], 0)))
        return best[0]

    def _pick_chat(self, origin_host: str) -> Optional[Dict[str, Any]]:
        candidates = [c for c in self._chat_candidates if c["score"] >= 4]
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c["host"] == origin_host, c["score"]), reverse=True)
        return candidates[0]

    def _pick_models_url(self, origin_host: str) -> str:
        if not self._models_candidates:
            return ""
        candidates = [c for c in self._models_candidates if c["response_is_json"]] or self._models_candidates
        candidates.sort(key=lambda c: (c["host"] == origin_host, c["response_is_json"]), reverse=True)
        return self._clean_url(candidates[0]["url"])

    @staticmethod
    def _pick_scoped(candidates: List[Dict[str, Any]], origin_host: str) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        ordered = sorted(candidates, key=lambda c: c["host"] == origin_host, reverse=True)
        return ordered[0]

    def _pick_scoped_url(self, candidates: List[Dict[str, Any]], origin_host: str) -> str:
        chosen = self._pick_scoped(candidates, origin_host)
        return self._clean_url(chosen["url"]) if chosen else ""

    def _resolve_auth(self, has_otp_pair: bool) -> Tuple[str, str, List[str]]:
        evidence: List[str] = []
        if self._bearer_sample:
            evidence.append("Authorization: Bearer header observed on API traffic (value redacted)")
            return "bearer", "", evidence
        if self._apikey_header:
            evidence.append(f"API-key header '{self._apikey_header}' observed (value redacted)")
            return "api_key", self._apikey_header, evidence
        if has_otp_pair:
            evidence.append("paired OTP send/verify endpoints observed on the captured origin")
            return "tempmail_otp", "", evidence
        if self._cookie_sample:
            evidence.append("session Cookie observed on API traffic (value redacted)")
            return "cookie", "", evidence
        self.warnings.append("no authentication evidence found; assuming a public endpoint (auth_mode=none)")
        return "none", "", evidence

    def _verify_body_keys(self, verify: Optional[Dict[str, Any]]) -> Tuple[str, str]:
        email_key, code_key = "email", "code"
        body = (verify or {}).get("body")
        if isinstance(body, dict):
            for key in body:
                if re.search(r"(?i)mail", key):
                    email_key = key
                    break
            for key in body:
                if re.search(r"(?i)code|otp|pin", key):
                    code_key = key
                    break
        else:
            self.warnings.append("verify-OTP request body not captured; defaulting to 'email'/'code' keys")
        return email_key, code_key

    @staticmethod
    def _dedupe(items: List[str]) -> List[str]:
        seen: Set[str] = set()
        ordered: List[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return ordered

    def _resolve(self) -> AnalysisResult:
        origin_host = self._pick_origin()
        base_origin = f"https://{origin_host}" if origin_host else ""
        if not origin_host:
            self.warnings.append("could not determine a primary API origin; endpoints may span hosts")

        chat = self._pick_chat(origin_host)
        chat_url = self._clean_url(chat["url"]) if chat else ""
        if chat:
            latest_body = self._chat_bodies[-1] if self._chat_bodies else None
            schema = self._introspect_schema(latest_body)
            static_fields = self._build_static_fields(latest_body, schema)
            supports_streaming, delta_mode, shape = self._introspect_response(chat["response"])
        else:
            self.warnings.append("no chat/inference endpoint identified; generated client raises UnsupportedOperation")
            schema, static_fields = ChatSchema(), {}
            supports_streaming, delta_mode, shape = False, "raw_text", "unknown"

        send = self._pick_scoped(self._otp_send_candidates, origin_host)
        verify = self._pick_scoped(self._otp_verify_candidates, origin_host)
        auth_mode, api_key_header, evidence = self._resolve_auth(bool(send and verify))
        email_key, code_key = self._verify_body_keys(verify)

        result = AnalysisResult(
            slug=self.slug,
            har_path=str(self.har_path),
            base_origin=base_origin,
            chat_url=chat_url,
            models_url=self._pick_models_url(origin_host),
            audio_url=self._pick_scoped_url(self._audio_candidates, origin_host),
            upload_url=self._pick_scoped_url(self._upload_candidates, origin_host),
            send_otp_url=self._clean_url(send["url"]) if send else "",
            verify_otp_url=self._clean_url(verify["url"]) if verify else "",
            auth_mode=auth_mode,
            auth_evidence=evidence,
            api_key_header=api_key_header,
            verify_email_key=email_key,
            verify_code_key=code_key,
            token_json_keys=self._harvest_token_keys(),
            discovered_models=sorted(self._discovered_models),
            schema=schema,
            static_fields=static_fields,
            supports_streaming=supports_streaming,
            delta_mode=delta_mode,
            response_shape=shape,
            sample_headers=dict(self._sample_headers),
            counts=dict(self.counts),
            warnings=self._dedupe(self.warnings),
        )
        if chat_url and not schema.messages_key and not schema.prompt_key:
            result.warnings.append(
                "chat body schema unrecognized; generated build_payload() raises UnsupportedOperation until wired manually"
            )
        return result


# ---------------------------------------------------------------------------
# Generated provider template
# ---------------------------------------------------------------------------

PROVIDER_TEMPLATE = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@@PROVIDER_NAME@@ - auto-generated provider module (Universal Provider Blueprint v4.0).

Generated by tools/har_to_provider_v2.py on @@GENERATED_AT@@.
Auth mode: @@AUTH_MODE@@. Streaming: @@STREAMING_DOC@@.

Environment configuration (all optional unless noted):
@@ENV_DOC@@

Regenerate with: @@REGEN_CMD@@
"""

from __future__ import annotations

import html
import json
import os
import random
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

import requests

__all__ = [
    "ProviderClient",
    "ProviderError",
    "AuthError",
    "VisionRejected",
    "UnsupportedOperation",
    "PoolEmptyError",
]

SLUG = @@SLUG_LIT@@
_ENV_PREFIX = SLUG.upper()
BASE_URL = @@BASE_URL_LIT@@
CHAT_URL = @@CHAT_URL_LIT@@
MODELS_URL = @@MODELS_URL_LIT@@
AUDIO_URL = @@AUDIO_URL_LIT@@
UPLOAD_URL = @@UPLOAD_URL_LIT@@
AUTH_MODE = @@AUTH_MODE_LIT@@
API_KEY_HEADER = @@API_KEY_HEADER_LIT@@
SEND_OTP_URL = @@SEND_OTP_URL_LIT@@
VERIFY_OTP_URL = @@VERIFY_OTP_URL_LIT@@
VERIFY_EMAIL_KEY = @@VERIFY_EMAIL_KEY_LIT@@
VERIFY_CODE_KEY = @@VERIFY_CODE_KEY_LIT@@
TOKEN_JSON_KEYS = @@TOKEN_JSON_KEYS_LIT@@
DISCOVERED_MODELS = @@DISCOVERED_MODELS_LIT@@
STATIC_FIELDS = json.loads(@@STATIC_FIELDS_JSON@@)
SAMPLE_HEADERS = json.loads(@@SAMPLE_HEADERS_JSON@@)
SCHEMA = {
    "model_key": @@MODEL_KEY_LIT@@,
    "messages_key": @@MESSAGES_KEY_LIT@@,
    "prompt_key": @@PROMPT_KEY_LIT@@,
    "content_key": @@CONTENT_KEY_LIT@@,
    "role_key": @@ROLE_KEY_LIT@@,
    "stream_key": @@STREAM_KEY_LIT@@,
}
SUPPORTS_STREAMING = @@SUPPORTS_STREAMING@@
DELTA_MODE = @@DELTA_MODE_LIT@@
DEFAULT_TIMEOUT = float(os.environ.get(_ENV_PREFIX + "_TIMEOUT", "120"))
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_STATIC_ENV_NAMES = {"bearer": "TOKEN", "api_key": "API_KEY", "cookie": "COOKIE"}


class ProviderError(Exception):
    """Base error for @@SLUG@@ provider failures."""


class AuthError(ProviderError):
    """Credential acquisition, refresh, or validation failed."""


class PoolEmptyError(AuthError):
    """Credential pool exhausted and no bootstrap factory succeeded."""


class VisionRejected(ProviderError):
    """Multimodal payload rejected: the scaffolded model is text-only."""


class UnsupportedOperation(ProviderError):
    """Operation has no supporting evidence in the source HAR capture."""


class FileLock:
    """Cross-process advisory lock via O_CREAT|O_EXCL with owner metadata."""

    def __init__(self, path, timeout: float = 30.0, stale_after: float = 300.0):
        self.path = Path(path)
        self.timeout = float(timeout)
        self.stale_after = float(stale_after)
        self._owner_token = ""

    def acquire(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        self._owner_token = uuid.uuid4().hex
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            except FileExistsError:
                if self._lock_is_stale():
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire lock: {self.path}")
                time.sleep(0.05)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"owner": self._owner_token, "pid": os.getpid(), "ts": time.time()}, handle)
            return self

    def _lock_is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return (time.time() - float(data.get("ts", 0.0))) > self.stale_after
        except (OSError, ValueError):
            return False  # unreadable lock: assume live (conservative)

    def release(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if data.get("owner") == self._owner_token:
            try:
                self.path.unlink()
            except OSError:
                pass

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, *exc: Any) -> bool:
        self.release()
        return False


class TokenPool:
    """Persistent, cross-process credential pool with leases and atomic saves.

    In-process operations are serialized with a non-reentrant threading.Lock;
    cross-process consistency uses FileLock. The bootstrap factory performs
    network I/O and is therefore never invoked while holding the file lock.
    """

    def __init__(self, path, ):
        self.path = Path(path)
        self._tlock = threading.Lock()
        self._bootstrap: Optional[Any] = None

    def set_bootstrap(self, factory: Any) -> None:
        self._bootstrap = factory

    def _lock_path(self) -> Path:
        return self.path.parent / (self.path.name + ".lock")

    def _load(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tokens"), list):
                return data
        except (OSError, ValueError):
            pass
        if self.path.exists():  # corrupt file: preserve for forensics, reinit
            try:
                self.path.replace(self.path.with_name(self.path.name + ".corrupt"))
            except OSError:
                pass
        return {"tokens": [], "leases": {}, "used_at": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    @staticmethod
    def _purge_expired(data: Dict[str, Any]) -> None:
        now = time.time()
        data["leases"] = {t: exp for t, exp in data.get("leases", {}).items() if exp > now}

    def _try_lease(self, lease_seconds: float) -> Optional[str]:
        with FileLock(self._lock_path()):
            data = self._load()
            self._purge_expired(data)
            tokens = [entry["token"] for entry in data["tokens"]]
            leased = set(data.get("leases", {}))
            free = [t for t in tokens if t not in leased]
            if not free:
                self._save(data)
                return None
            used_at = data.setdefault("used_at", {})
            token = min(free, key=lambda t: used_at.get(t, 0.0))
            data.setdefault("leases", {})[token] = time.time() + lease_seconds
            used_at[token] = time.time()
            self._save(data)
            return token

    def _add_locked(self, token: str) -> None:
        if not token:
            return
        with FileLock(self._lock_path()):
            data = self._load()
            if all(entry.get("token") != token for entry in data["tokens"]):
                data["tokens"].append({"token": token, "added_at": time.time()})
                self._save(data)

    def acquire(self, lease_seconds: float = 900.0) -> str:
        with self._tlock:
            token = self._try_lease(lease_seconds)
            if token:
                return token
            if self._bootstrap is not None:
                token = self._bootstrap()  # network I/O: file lock NOT held
                if token:
                    self._add_locked(token)
                    return token
            raise PoolEmptyError(
                "credential pool is empty and no bootstrap factory succeeded; "
                f"add a token via TokenPool.add() or set {_ENV_PREFIX}_TOKEN"
            )

    def release(self, token: str) -> None:
        if not token:
            return
        with self._tlock:
            with FileLock(self._lock_path()):
                data = self._load()
                data.get("leases", {}).pop(token, None)
                data.setdefault("used_at", {})[token] = time.time()
                self._save(data)

    def discard(self, token: str) -> bool:
        if not token:
            return False
        with self._tlock:
            with FileLock(self._lock_path()):
                data = self._load()
                before = len(data["tokens"])
                data["tokens"] = [e for e in data["tokens"] if e.get("token") != token]
                data.get("leases", {}).pop(token, None)
                self._save(data)
                return len(data["tokens"]) < before

    def add(self, token: str) -> None:
        with self._tlock:
            self._add_locked(token)

    def size(self) -> int:
        with self._tlock:
            with FileLock(self._lock_path()):
                data = self._load()
                self._purge_expired(data)
                return len(data["tokens"])


class TempMailClubClient:
    """Best-effort tempmail.club mailbox client.

    Bootstraps a Livewire-style session (csrf / wire:snapshot extraction),
    generates a disposable address, scrapes the inbox page for the OTP with a
    regex ladder, and deletes the mailbox best-effort under a lock. The public
    UI wire changes over time; override via env:
      TEMPMAIL_BASE, TEMPMAIL_DOMAIN, TEMPMAIL_INBOX_URL_TEMPLATE,
      TEMPMAIL_DELETE_URL_TEMPLATE
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 30.0):
        self.base = (base_url or os.environ.get("TEMPMAIL_BASE") or "https://tempmail.club").rstrip("/")
        self.timeout = float(timeout)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA, "Accept": "text/html,*/*"})
        self._delete_lock = threading.Lock()

    def _domains(self) -> List[str]:
        override = os.environ.get("TEMPMAIL_DOMAIN", "")
        if override:
            return [override]
        domains: List[str] = []
        try:
            page = self.session.get(self.base + "/", timeout=self.timeout).text
            snapshot = re.search(r'wire:snapshot="([^"]+)"', page)
            blob = html.unescape(snapshot.group(1)) if snapshot else page
            for candidate in re.findall(r"[a-z0-9][a-z0-9.-]{2,40}\.[a-z]{2,10}", blob):
                candidate = candidate.strip(".").lower()
                if candidate and "." in candidate and candidate not in domains:
                    domains.append(candidate)
        except requests.RequestException:
            pass
        return domains or [self.base.split("//")[-1] or "tempmail.club"]

    def create_inbox(self) -> str:
        domain = random.choice(self._domains())
        address = f"pp{uuid.uuid4().hex[:12]}@{domain}"
        try:
            self.session.get(self.base + "/", timeout=self.timeout)
        except requests.RequestException:
            pass
        return address

    def _inbox_text(self, address: str) -> str:
        template = os.environ.get("TEMPMAIL_INBOX_URL_TEMPLATE", "{base}/inbox/{address}")
        url = template.format(base=self.base, address=quote(address, safe="@"))
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AuthError(f"tempmail inbox fetch failed for {url}: {exc}") from exc
        if response.status_code != 200:
            raise AuthError(f"tempmail inbox fetch returned HTTP {response.status_code} for {url}")
        return response.text

    def poll_otp(self, address: str, timeout: float = 180.0, interval: float = 4.0) -> str:
        deadline = time.monotonic() + timeout
        ladder = (
            re.compile(r"\b(\d{6})\b"),
            re.compile(r"(?:code|otp|pin|verification)[^0-9]{0,40}(\d{4,8})", re.IGNORECASE),
            re.compile(r"(\d{4,8})(?:[^0-9]{0,40}(?:code|otp|pin|verification))", re.IGNORECASE),
            re.compile(r"\b(\d{4})\b"),
        )
        while time.monotonic() < deadline:
            page = self._inbox_text(address)
            for pattern in ladder:
                match = pattern.search(page)
                if match:
                    return match.group(1)
            time.sleep(interval)
        raise AuthError(f"no OTP code arrived at {address} within {timeout:.0f}s")

    def delete_email(self, address: str) -> None:
        with self._delete_lock:
            try:
                template = os.environ.get("TEMPMAIL_DELETE_URL_TEMPLATE", "{base}/inbox/{address}")
                url = template.format(base=self.base, address=quote(address, safe="@"))
                self.session.delete(url, timeout=self.timeout)
            except requests.RequestException:
                pass  # best-effort cleanup: never masks the signup result


_CRED_KEY_RE = re.compile(
    r"(?i)(access[_-]?token|api[_-]?token|auth[_-]?token|id[_-]?token|jwt|bearer|api[_-]?key|session[_-]?key|token)"
)


def _find_credential(obj: Any, depth: int = 0) -> str:
    if depth > 4 or obj is None:
        return ""
    if isinstance(obj, dict):
        for key in TOKEN_JSON_KEYS:  # scaffold-observed keys take priority
            value = obj.get(key)
            if isinstance(value, str) and len(value) >= 16 and not value.isspace():
                return value
        for key, value in obj.items():
            if isinstance(value, str) and _CRED_KEY_RE.search(key) and len(value) >= 16:
                return value
        for value in obj.values():
            found = _find_credential(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_credential(item, depth + 1)
            if found:
                return found
    return ""


def _signup_headers() -> Dict[str, str]:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    headers.update({k: v for k, v in SAMPLE_HEADERS.items() if k in ("Origin", "Referer")})
    return headers


def signup_for_account(pool: Optional[TokenPool] = None) -> str:
    """Full tempmail OTP signup: inbox -> send OTP -> poll -> verify -> harvest."""
    if not SEND_OTP_URL or not VERIFY_OTP_URL:
        raise UnsupportedOperation("tempmail_otp mode requires SEND_OTP_URL and VERIFY_OTP_URL")
    mail = TempMailClubClient()
    address = mail.create_inbox()
    try:
        response = requests.post(
            SEND_OTP_URL, json={VERIFY_EMAIL_KEY: address}, headers=_signup_headers(), timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        code = mail.poll_otp(address, timeout=float(os.environ.get(_ENV_PREFIX + "_OTP_TIMEOUT", "180")))
        response = requests.post(
            VERIFY_OTP_URL,
            json={VERIFY_EMAIL_KEY: address, VERIFY_CODE_KEY: code},
            headers=_signup_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        token = _find_credential(response.json())
        if not token and response.cookies:
            token = "; ".join(f"{c.name}={c.value}" for c in response.cookies)
        if not token:
            raise AuthError("OTP verified but no credential found; extend TOKEN_JSON_KEYS via re-scaffolding")
        if pool is not None:
            pool.add(token)
        return token
    finally:
        mail.delete_email(address)


_MEDIA_TYPES = {
    "image_url", "input_image", "image", "audio_url", "input_audio", "audio",
    "video_url", "video", "file", "input_file",
}
_MEDIA_URI_RE = re.compile(r"data:(?:image|audio|video|application)/[a-z0-9.+-]+\s*;", re.IGNORECASE)


def assert_text_only(messages: List[Any]) -> None:
    """Reject vision/multimodal payloads in O(n) before any network I/O."""
    stack = list(messages)
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if _MEDIA_URI_RE.search(item):
                raise VisionRejected("inline base64 image/audio/video data URI detected")
        elif isinstance(item, dict):
            part_type = str(item.get("type", "")).lower()
            if part_type in _MEDIA_TYPES:
                raise VisionRejected(f"multimodal part type '{part_type}' rejected: model is text-only")
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, bytes):
            raise VisionRejected("binary payload detected: model is text-only")


_TEXT_KEYS = ("content", "text", "message", "delta", "response", "answer", "output", "result")
_SKIP_KEYS = {
    "id", "object", "model", "created", "finish_reason", "stop_reason", "type",
    "role", "index", "name", "logprobs", "usage", "service_tier",
    "system_fingerprint", "stop_sequence",
}
_NOISE_STRINGS = {
    "stop", "end_turn", "stop_sequence", "tool_use", "text", "image",
    "assistant", "user", "system", "ping", "message_start", "message_stop",
    "message_delta", "content_block_start", "content_block_stop",
    "content_block_delta", "chat",
}


def _extract_text(obj: Any) -> str:
    """Recursive text extractor: OpenAI/Anthropic blocking + delta shapes, raw JSON, plain text."""
    if isinstance(obj, str):
        return obj if obj and obj not in _NOISE_STRINGS else ""
    if isinstance(obj, dict):
        for key in _TEXT_KEYS:
            if key in obj:
                found = _extract_text(obj[key])
                if found:
                    return found
        for key, value in obj.items():
            if key in _SKIP_KEYS:
                continue
            found = _extract_text(value)
            if found:
                return found
        return ""
    if isinstance(obj, (list, tuple)):
        for item in obj:
            found = _extract_text(item)
            if found:
                return found
    return ""


def _iter_delta_text(response: Any) -> Iterator[str]:
    """Yield text deltas from an SSE (or plain JSON) streaming response."""
    buffer: List[str] = []

    def emit(raw: str) -> str:
        raw = raw.strip()
        if not raw or raw == "[DONE]":
            return ""
        try:
            payload = json.loads(raw)
        except ValueError:
            return raw  # raw-text upstream stream
        return _extract_text(payload)

    for line in response.iter_lines(decode_unicode=True):
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        if not line:
            if buffer:
                chunk = emit("\n".join(buffer))
                buffer.clear()
                if chunk:
                    yield chunk
            continue
        stripped = line.strip()
        if stripped.startswith(":"):
            continue  # SSE comment / keep-alive
        if stripped.startswith("data:"):
            buffer.append(stripped[5:].strip())
        else:
            buffer.append(stripped)
    if buffer:
        chunk = emit("\n".join(buffer))
        if chunk:
            yield chunk


def _harvest_model_names(body: Any, depth: int = 0) -> List[str]:
    if depth > 4:
        return []
    names: List[str] = []
    if isinstance(body, list):
        for item in body:
            if isinstance(item, str):
                names.append(item)
            else:
                names.extend(_harvest_model_names(item, depth + 1))
    elif isinstance(body, dict):
        for key, value in body.items():
            if isinstance(value, str) and key in ("id", "name", "model", "slug"):
                names.append(value)
            elif isinstance(value, (list, dict)):
                names.extend(_harvest_model_names(value, depth + 1))
    return sorted(set(names))


def _messages_to_prompt(messages: List[Any]) -> str:
    lines = []
    for message in messages:
        if isinstance(message, dict):
            content = message.get("content", message.get("text", ""))
            lines.append(f"{message.get('role', 'user')}: {content}")
        else:
            lines.append(str(message))
    return "\n".join(lines)


class @@CLASS_NAME@@:
    """Unified inference client for @@PROVIDER_NAME@@ (auth: @@AUTH_MODE@@).

    - generate_text(): blocking completion.
    - stream_text(): SSE generator (raises UnsupportedOperation when the
      source HAR shows no streaming evidence).
    - list_models()/transcribe_audio()/upload_file(): evidence-gated.
    - start_replenisher(): explicit background pool refill (tempmail_otp only).
    """

    def __init__(
        self,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        pool_path: Optional[str] = None,
    ):
        self.default_model = model or (DISCOVERED_MODELS[0] if DISCOVERED_MODELS else None)
        self.timeout = float(timeout if timeout is not None else DEFAULT_TIMEOUT)
        self.pool: Optional[TokenPool] = None
        self._replenisher: Optional[threading.Thread] = None
        self._replenisher_stop: Optional[threading.Event] = None
        self._replenisher_lock = threading.Lock()
        if AUTH_MODE == "tempmail_otp":
            default_path = Path.home() / ("." + SLUG) / "tokens.json"
            self.pool = TokenPool(pool_path or os.environ.get(_ENV_PREFIX + "_POOL_PATH") or default_path)
            self.pool.set_bootstrap(lambda: signup_for_account(None))

    # -- credential plumbing -------------------------------------------------

    def _static_token(self) -> str:
        suffix = _STATIC_ENV_NAMES.get(AUTH_MODE, "")
        return os.environ.get(_ENV_PREFIX + "_" + suffix, "").strip() if suffix else ""

    def _credential(self) -> Tuple[str, bool]:
        if AUTH_MODE == "none":
            return "", False
        static = self._static_token()
        if static:
            return static, False
        if self.pool is not None:
            return self.pool.acquire(), True
        raise AuthError(
            f"no credential configured; set the {_ENV_PREFIX}_* environment variable or run signup_for_account()"
        )

    def _headers(self, credential: str) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": SAMPLE_HEADERS.get("User-Agent", DEFAULT_UA),
        }
        for name in ("Origin", "Referer", "Accept-Language"):
            if name in SAMPLE_HEADERS:
                headers[name] = SAMPLE_HEADERS[name]
        if AUTH_MODE == "bearer" and credential:
            headers["Authorization"] = f"Bearer {credential}"
        elif AUTH_MODE == "api_key" and credential:
            headers[API_KEY_HEADER] = credential
        elif AUTH_MODE == "cookie" and credential:
            headers["Cookie"] = credential
        return headers

    def _audio_headers(self, credential: str) -> Dict[str, str]:
        headers = self._headers(credential)
        headers.pop("Content-Type", None)  # requests sets the multipart boundary
        return headers

    # -- request building -------------------------------------------------------

    def build_payload(
        self,
        messages: List[Any],
        model: Optional[str] = None,
        want_stream: bool = False,
        **overrides: Any,
    ) -> Dict[str, Any]:
        payload = json.loads(json.dumps(STATIC_FIELDS))  # deep copy of observed static template
        if SCHEMA["messages_key"]:
            payload[SCHEMA["messages_key"]] = [self._normalize_message(m) for m in messages]
        elif SCHEMA["prompt_key"]:
            payload[SCHEMA["prompt_key"]] = _messages_to_prompt(messages)
        else:
            raise UnsupportedOperation(
                "HAR schema exposes no messages/prompt slot; wire the payload manually or re-capture"
            )
        if SCHEMA["model_key"] and model:
            payload[SCHEMA["model_key"]] = model
        if SCHEMA["stream_key"]:
            payload[SCHEMA["stream_key"]] = bool(want_stream)
        payload.update(overrides)
        return payload

    @staticmethod
    def _normalize_message(message: Any) -> Any:
        if isinstance(message, str):
            base: Dict[str, Any] = {}
            if SCHEMA["role_key"]:
                base[SCHEMA["role_key"]] = "user"
            if SCHEMA["content_key"]:
                base[SCHEMA["content_key"]] = message
            return base or message
        if isinstance(message, dict) and SCHEMA["content_key"]:
            renamed = dict(message)
            if "content" in renamed and SCHEMA["content_key"] != "content":
                renamed[SCHEMA["content_key"]] = renamed.pop("content")
            if SCHEMA["role_key"] and "role" in renamed and SCHEMA["role_key"] != "role":
                renamed[SCHEMA["role_key"]] = renamed.pop("role")
            return renamed
        return message

    # -- inference ------------------------------------------------------------------

    def generate_text(self, messages: List[Any], model: Optional[str] = None, **overrides: Any) -> str:
        if not CHAT_URL:
            raise UnsupportedOperation("no chat endpoint was captured in the source HAR")
        assert_text_only(messages)
        payload = self.build_payload(messages, model=model or self.default_model, want_stream=False, **overrides)
        attempts = 2 if AUTH_MODE == "tempmail_otp" else 1
        last_error: Optional[Exception] = None
        for _ in range(attempts):
            credential, from_pool = self._credential()
            try:
                response = requests.post(
                    CHAT_URL, headers=self._headers(credential), json=payload, timeout=self.timeout,
                )
                if response.status_code in (401, 403):
                    if from_pool:
                        self.pool.discard(credential)
                    last_error = AuthError(f"upstream rejected credentials (HTTP {response.status_code})")
                    continue
                response.raise_for_status()
                try:
                    body = response.json()
                except ValueError:
                    return response.text.strip()
                return _extract_text(body) or response.text.strip()
            finally:
                if from_pool:
                    self.pool.release(credential)
        raise last_error or AuthError("credential rejected")

    def stream_text(self, messages: List[Any], model: Optional[str] = None, **overrides: Any) -> Iterator[str]:
        if not CHAT_URL:
            raise UnsupportedOperation("no chat endpoint was captured in the source HAR")
        if not SUPPORTS_STREAMING:
            raise UnsupportedOperation("no streaming evidence in the source HAR; use generate_text()")
        assert_text_only(messages)
        payload = self.build_payload(messages, model=model or self.default_model, want_stream=True, **overrides)
        credential, from_pool = self._credential()
        try:
            response = requests.post(
                CHAT_URL, headers=self._headers(credential), json=payload, timeout=self.timeout, stream=True,
            )
            try:
                if response.status_code in (401, 403) and from_pool:
                    self.pool.discard(credential)
                response.raise_for_status()
                for chunk in _iter_delta_text(response):
                    if chunk:
                        yield chunk
            finally:
                response.close()
        finally:
            if from_pool:
                self.pool.release(credential)

    # -- evidence-gated operations ------------------------------------------------

    def list_models(self) -> List[str]:
        if not MODELS_URL:
            raise UnsupportedOperation("no models endpoint was captured in the source HAR")
        credential, from_pool = self._credential()
        try:
            response = requests.get(MODELS_URL, headers=self._headers(credential), timeout=self.timeout)
            if response.status_code in (401, 403) and from_pool:
                self.pool.discard(credential)
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError:
                raise ProviderError("models endpoint returned a non-JSON body") from None
            return _harvest_model_names(body)
        finally:
            if from_pool:
                self.pool.release(credential)

    def transcribe_audio(
        self, file_path, model: Optional[str] = None, language: Optional[str] = None,
    ) -> str:
        if not AUDIO_URL:
            raise UnsupportedOperation("no speech-to-text endpoint was captured in the source HAR")
        path = Path(file_path)
        if not path.is_file():
            raise ProviderError(f"audio file not found: {path}")
        fields: Dict[str, Any] = {}
        chosen_model = model or self.default_model
        if chosen_model:
            fields["model"] = chosen_model
        if language:
            fields["language"] = language
        credential, from_pool = self._credential()
        try:
            with path.open("rb") as handle:
                response = requests.post(
                    AUDIO_URL,
                    headers=self._audio_headers(credential),
                    files={"file": (path.name, handle, "application/octet-stream")},
                    data=fields or None,
                    timeout=max(self.timeout, 300.0),
                )
            if response.status_code in (401, 403) and from_pool:
                self.pool.discard(credential)
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError:
                return response.text.strip()
            return _extract_text(body) or response.text.strip()
        finally:
            if from_pool:
                self.pool.release(credential)

    def upload_file(self, file_path) -> Any:
        if not UPLOAD_URL:
            raise UnsupportedOperation("no upload endpoint was captured in the source HAR")
        path = Path(file_path)
        if not path.is_file():
            raise ProviderError(f"upload file not found: {path}")
        credential, from_pool = self._credential()
        try:
            with path.open("rb") as handle:
                response = requests.post(
                    UPLOAD_URL,
                    headers=self._audio_headers(credential),
                    files={"file": (path.name, handle, "application/octet-stream")},
                    timeout=max(self.timeout, 300.0),
                )
            if response.status_code in (401, 403) and from_pool:
                self.pool.discard(credential)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {"text": response.text}
        finally:
            if from_pool:
                self.pool.release(credential)

    # -- pool replenishment (tempmail_otp only) -------------------------------------

    def start_replenisher(self, min_size: int = 1, interval: float = 300.0) -> bool:
        """Start the background pool replenisher. Idempotent; no-op for other auth modes."""
        if AUTH_MODE != "tempmail_otp" or self.pool is None:
            return False
        with self._replenisher_lock:
            if self._replenisher is not None and self._replenisher.is_alive():
                return True
            self._replenisher_stop = threading.Event()
            interval = float(os.environ.get(_ENV_PREFIX + "_REPLENISH_INTERVAL", interval))
            pool = self.pool
            stop = self._replenisher_stop

            def _run() -> None:
                failures = 0
                while not stop.wait(min(interval * (2 ** min(failures, 4)), interval * 16)):
                    try:
                        if pool.size() < min_size:
                            signup_for_account(pool)
                            failures = 0
                    except Exception:
                        failures += 1

            thread = threading.Thread(target=_run, name=SLUG + "-replenisher", daemon=True)
            thread.start()
            self._replenisher = thread
            return True

    def close(self) -> None:
        if self._replenisher_stop is not None:
            self._replenisher_stop.set()


# Friendly alias for uniform imports across generated providers.
ProviderClient = @@CLASS_NAME@@


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    _client = @@CLASS_NAME@@()
    print(_client.generate_text([{"role": "user", "content": "ping"}]))
'''

INIT_TEMPLATE = '''"""Auto-generated package facade for @@SLUG@@ (har_to_provider_v2.py).

Importing this package performs no network I/O and starts no background work.
"""

from .provider import (
    AuthError,
    PoolEmptyError,
    ProviderClient,
    ProviderError,
    UnsupportedOperation,
    VisionRejected,
)

__all__ = [
    "ProviderClient",
    "ProviderError",
    "AuthError",
    "VisionRejected",
    "UnsupportedOperation",
    "PoolEmptyError",
]
'''

README_TEMPLATE = '''# @@PROVIDER_NAME@@ Provider Package

Auto-generated by `tools/har_to_provider_v2.py` on @@GENERATED_AT@@ from a HAR capture.
Standard: Universal Provider Blueprint v4.0 - raw HAR in, production provider out.

## Files

| File | Purpose |
| --- | --- |
| `provider.py` | Full provider implementation (auth, streaming, resilience). |
| `__init__.py` | Package facade re-exporting the public API. |
| `ingestion_report.json` | Redacted evidence report produced during scaffolding. |

## Captured Endpoints (@@BASE_URL@@)

| Role | URL |
| --- | --- |
@@ENDPOINT_ROWS@@

## Inferred Wire Schema

| Aspect | Value |
| --- | --- |
@@SCHEMA_ROWS@@

Auth mode: **@@AUTH_MODE@@**

## Environment Variables

@@ENV_ROWS@@

## Quickstart

    from providers.@@SLUG@@ import ProviderClient

    client = ProviderClient()
    print(client.generate_text([{"role": "user", "content": "Hello!"}]))
    for chunk in client.stream_text([{"role": "user", "content": "Hello!"}]):
        print(chunk, end="", flush=True)

Notes:

- `stream_text()` raises `UnsupportedOperation` when the capture shows no SSE evidence.
- `list_models()`, `transcribe_audio()`, and `upload_file()` raise `UnsupportedOperation`
  unless the corresponding endpoint was captured.
- The text-only vision guard (`VisionRejected`) blocks multimodal payloads in O(n).

## Captured Models

@@MODEL_LIST@@

## Scaffolder Warnings

@@WARNING_BULLETS@@

## Regeneration

@@REGEN_CMD@@
'''


# ---------------------------------------------------------------------------
# Scaffolder
# ---------------------------------------------------------------------------

def _py(value: Any) -> str:
    """Render a safe Python literal for embedding into generated source."""
    return repr(value)


def _json_literal(value: Any) -> str:
    """Embed a JSON blob as a Python string literal: json.loads(<literal>)."""
    return repr(json.dumps(value, ensure_ascii=True, allow_nan=False))


class ProviderScaffolder:
    """Renders, validates, and atomically writes the provider package."""

    def __init__(self, result: AnalysisResult, out_dir: str):
        self.result = result
        self.out_dir = Path(out_dir)

    # -- public API ----------------------------------------------------------

    def scaffold(self) -> Dict[str, Path]:
        slug = self.result.slug
        class_name = "".join(part.capitalize() for part in slug.split("_")) + "Provider"
        tokens = self._build_tokens(class_name)
        provider_source = self._render(PROVIDER_TEMPLATE, tokens)
        init_source = self._render(INIT_TEMPLATE, tokens)
        readme_source = self._render(README_TEMPLATE, tokens)
        self._validate_python(provider_source, "provider.py")
        self._validate_python(init_source, "__init__.py")

        self.out_dir.mkdir(parents=True, exist_ok=True)
        provider_path = self.out_dir / "provider.py"
        init_path = self.out_dir / "__init__.py"
        readme_path = self.out_dir / "README.md"
        report_path = self.out_dir / "ingestion_report.json"

        self._atomic_write(provider_path, provider_source)
        self._atomic_write(init_path, init_source)
        self._atomic_write(readme_path, readme_source)
        report = self.result.to_report()
        report["generated_at"] = tokens["GENERATED_AT"]
        report["output_directory"] = str(self.out_dir)
        self._atomic_write(report_path, json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))

        return {"provider": provider_path, "package": init_path, "readme": readme_path, "report": report_path}

    # -- rendering -------------------------------------------------------------

    @staticmethod
    def _render(template: str, tokens: Dict[str, str]) -> str:
        rendered = template
        for key, value in tokens.items():
            rendered = rendered.replace(f"@@{key}@@", value)
        leftover = sorted(set(re.findall(r"@@[A-Z0-9_]+@@", rendered)))
        if leftover:
            raise ValueError(f"unresolved template tokens: {', '.join(leftover)}")
        return rendered

    @staticmethod
    def _validate_python(source: str, name: str) -> None:
        try:
            compile(source, name, "exec")
        except SyntaxError as exc:
            raise ValueError(f"generated {name} failed to compile: {exc}") from exc

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp, path)

    # -- token builders -----------------------------------------------------------

    def _build_tokens(self, class_name: str) -> Dict[str, str]:
        r = self.result
        schema = r.schema

        def fmt(value: Optional[str]) -> str:
            return f"`{value}`" if value else "_absent_"

        def endpoint_row(role: str, url: str) -> str:
            return f"| `{role}` | `{url}` |" if url else f"| `{role}` | _(not captured)_ |"

        endpoint_rows = "\n".join([
            endpoint_row("chat", r.chat_url),
            endpoint_row("models", r.models_url),
            endpoint_row("audio/stt", r.audio_url),
            endpoint_row("upload", r.upload_url),
            endpoint_row("otp send", r.send_otp_url),
            endpoint_row("otp verify", r.verify_otp_url),
        ])
        schema_rows = "\n".join([
            f"| messages key | {fmt(schema.messages_key)} |",
            f"| prompt key | {fmt(schema.prompt_key)} |",
            f"| model key | {fmt(schema.model_key)} |",
            f"| message content key | {fmt(schema.content_key)} |",
            f"| message role key | {fmt(schema.role_key)} |",
            f"| stream key | {fmt(schema.stream_key)} |",
            f"| thinking flags | {'yes' if schema.has_thinking else 'no'} |",
            f"| web-search flags | {'yes' if schema.has_web_search else 'no'} |",
        ])
        if r.discovered_models:
            model_list = "\n".join(f"- `{m}`" for m in r.discovered_models)
        else:
            model_list = "_none captured - pass any model string accepted by the upstream API._"
        warnings = "\n".join(f"- {w}" for w in r.warnings) or "_none._"
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        return {
            "SLUG": r.slug,
            "SLUG_LIT": _py(r.slug),
            "CLASS_NAME": class_name,
            "PROVIDER_NAME": r.slug.replace("_", " ").title(),
            "GENERATED_AT": generated_at,
            "STREAMING_DOC": "supported (SSE)" if r.supports_streaming else "not observed in capture",
            "BASE_URL_LIT": _py(r.base_origin),
            "CHAT_URL_LIT": _py(r.chat_url),
            "MODELS_URL_LIT": _py(r.models_url),
            "AUDIO_URL_LIT": _py(r.audio_url),
            "UPLOAD_URL_LIT": _py(r.upload_url),
            "AUTH_MODE_LIT": _py(r.auth_mode),
            "API_KEY_HEADER_LIT": _py(r.api_key_header),
            "SEND_OTP_URL_LIT": _py(r.send_otp_url),
            "VERIFY_OTP_URL_LIT": _py(r.verify_otp_url),
            "VERIFY_EMAIL_KEY_LIT": _py(r.verify_email_key),
            "VERIFY_CODE_KEY_LIT": _py(r.verify_code_key),
            "TOKEN_JSON_KEYS_LIT": _py(r.token_json_keys),
            "DISCOVERED_MODELS_LIT": _py(r.discovered_models),
            "STATIC_FIELDS_JSON": _json_literal(r.static_fields),
            "SAMPLE_HEADERS_JSON": _json_literal(r.sample_headers),
            "MODEL_KEY_LIT": _py(schema.model_key),
            "MESSAGES_KEY_LIT": _py(schema.messages_key),
            "PROMPT_KEY_LIT": _py(schema.prompt_key),
            "CONTENT_KEY_LIT": _py(schema.content_key),
            "ROLE_KEY_LIT": _py(schema.role_key),
            "STREAM_KEY_LIT": _py(schema.stream_key),
            "SUPPORTS_STREAMING": "True" if r.supports_streaming else "False",
            "DELTA_MODE_LIT": _py(r.delta_mode),
            "ENV_DOC": self._env_doc(),
            "ENDPOINT_ROWS": endpoint_rows,
            "SCHEMA_ROWS": schema_rows,
            "ENV_ROWS": self._env_rows(),
            "MODEL_LIST": model_list,
            "WARNING_BULLETS": warnings,
            "REGEN_CMD": f"`py -3.13 tools/har_to_provider_v2.py <capture.har> --slug {r.slug}`",
        }

    def _env_doc(self) -> str:
        upper = self.result.slug.upper()
        mode = self.result.auth_mode
        lines = [f"    {upper}_TIMEOUT        Per-request timeout in seconds (default: 120)."]
        if mode == "bearer":
            lines.append(f"    {upper}_TOKEN          Bearer token sent as 'Authorization: Bearer <token>'.")
        elif mode == "api_key":
            lines.append(f"    {upper}_API_KEY        Key sent in the '{self.result.api_key_header}' header.")
        elif mode == "cookie":
            lines.append(f"    {upper}_COOKIE         Raw Cookie header value for session auth.")
        elif mode == "tempmail_otp":
            lines.append("    TEMPMAIL_BASE / TEMPMAIL_DOMAIN / TEMPMAIL_INBOX_URL_TEMPLATE")
            lines.append("                    Overrides for the disposable-mail backend.")
            lines.append(f"    {upper}_POOL_PATH      TokenPool file (default: ~/.{self.result.slug}/tokens.json).")
            lines.append(f"    {upper}_OTP_TIMEOUT    Seconds to wait for an OTP email (default: 180).")
            lines.append(f"    {upper}_REPLENISH_INTERVAL  Background pool refill interval (default: 300).")
        return "\n".join(lines)

    def _env_rows(self) -> str:
        upper = self.result.slug.upper()
        mode = self.result.auth_mode
        rows = [f"- `{upper}_TIMEOUT` - per-request timeout in seconds (default 120)."]
        if mode == "bearer":
            rows.append(f"- `{upper}_TOKEN` - bearer token for the `Authorization` header (**required**).")
        elif mode == "api_key":
            rows.append(f"- `{upper}_API_KEY` - key sent in `{self.result.api_key_header}` (**required**).")
        elif mode == "cookie":
            rows.append(f"- `{upper}_COOKIE` - raw `Cookie` header value (**required**).")
        elif mode == "tempmail_otp":
            rows.append(f"- `{upper}_POOL_PATH` - token-pool file (default `~/.{self.result.slug}/tokens.json`).")
            rows.append(f"- `{upper}_OTP_TIMEOUT` - seconds to wait for the OTP email (default 180).")
            rows.append(f"- `{upper}_REPLENISH_INTERVAL` - background refill interval (default 300).")
            rows.append("- `TEMPMAIL_BASE` / `TEMPMAIL_DOMAIN` / `TEMPMAIL_INBOX_URL_TEMPLATE` - mail-backend overrides.")
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _normalize_slug(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", (raw or "").strip().lower()).strip("_")
    if not slug:
        raise ValueError("--slug must contain at least one letter or digit")
    if slug[0].isdigit():
        slug = f"p_{slug}"
    if keyword.iskeyword(slug):
        slug = f"{slug}_provider"
    if slug in RESERVED_MODULE_NAMES:
        raise ValueError(f"'{slug}' collides with a reserved module name; choose another --slug")
    return slug


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="har_to_provider_v2",
        description="Scaffold a production provider package from a captured HAR file.",
    )
    parser.add_argument("har", help="path to the captured .har file")
    parser.add_argument("--slug", required=True, help="provider slug, e.g. deepseek_chat")
    parser.add_argument("--out", default=None, help="output directory (default: providers/<slug>)")
    parser.add_argument("--dry-run", action="store_true", help="analyze and print the report without writing files")
    parser.add_argument("-v", "--verbose", action="store_true", help="print evidence details while analyzing")
    args = parser.parse_args(argv)

    print(BANNER)

    try:
        slug = _normalize_slug(args.slug)
    except ValueError as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 2

    try:
        result = HarAnalyzer(args.har, slug).analyze()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[!] analysis failed: {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"[*] origin: {result.base_origin or '(undetermined)'}")
        for name in ("chat_url", "models_url", "audio_url", "upload_url", "send_otp_url", "verify_otp_url"):
            value = getattr(result, name)
            if value:
                print(f"    {name}: {value}")
        for line in result.auth_evidence:
            print(f"    auth: {line}")

    if args.dry_run:
        for warning in result.warnings:
            print(f"    warning: {warning}")
        print(json.dumps(result.to_report(), indent=2, ensure_ascii=True, allow_nan=False))
        return 0

    out_dir = args.out or str(Path("providers") / slug)
    try:
        paths = ProviderScaffolder(result, out_dir).scaffold()
    except (OSError, ValueError) as exc:
        print(f"[!] scaffolding failed: {exc}", file=sys.stderr)
        return 2

    print("[+] provider package written:")
    for label, path in paths.items():
        print(f"    {label:<8} {path}")
    print(f"[+] auth mode: {result.auth_mode}; streaming: {'yes' if result.supports_streaming else 'no'}; "
          f"models discovered: {len(result.discovered_models)}")
    for warning in result.warnings:
        print(f"    warning: {warning}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[!] interrupted", file=sys.stderr)
        sys.exit(130)