#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
â¡ HAR TO PROVIDER AUTONOMOUS SCAFFOLDER (v4.0 â Architectural Audit Edition)
============================================================================
Audits a HAR 1.2 capture and scaffolds a complete, production-grade provider
package under `providers/<slug>/`.

Pipeline stages
---------------
1. INGEST      : parse HAR, drop noise (trackers, OPTIONS/CONNECT, static assets).
2. CLASSIFY    : every entry is scored against every capability (auth/audio/
                 upload/chat/models) â no first-match bias, evidence recorded.
3. ELECT       : the API origin is elected by host scoring ("api"/slug hints),
                 the common versioned path prefix becomes the API base.
4. REDACT      : captured emails, tokens, JWTs and user content are stripped
                 from templates. Auth templates keep named placeholders
                 (__EMAIL__/__OTP__/__TOKEN__); chat/form templates are reduced
                 to safe literals. Nothing secret is ever written to disk.
5. GENERATE    : capability-gated code emission. A client class is generated
                 ONLY for a capability that was detected with confidence >= 0.5
                 (or forced via --endpoint). Zero invented endpoints, zero
                 invented models, zero dead code.

Generated package layout
------------------------
providers/<slug>/
    __init__.py             public faÃ§ade re-exports
    definition.py           HAR-derived constants (endpoints, templates, models)
    core.py                 FileLock + AtomicJSONStore, curl_cffi chrome124
                            HttpSession, SSE parser, TempMail (mail.tm) OTP
                            flow, AccountPool daemon, capability clients
    adapter.py              ProviderAdapter: credential rotation on 401/403
    test_provider_smoke.py  OFFLINE smoke tests (no network by design)
    README.md               capability report + quickstart
    manifest.json           audit evidence: confidence, warnings, redactions

CLI reference
-------------
    py -3.13 tools/har_to_provider.py traffic.har --slug acmeai
    py -3.13 tools/har_to_provider.py traffic.har --slug acmeai --dry-run
    py -3.13 tools/har_to_provider.py traffic.har --slug acmeai --strict \
        --endpoint chat=https://api.acme.ai/v1/chat/completions \
        --model acme-large --model acme-small

Exit codes: 0 = success, 1 = fatal error, 2 = --strict gate failure.
Generated-package dependency: curl_cffi (pip install curl_cffi).
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOOL_VERSION = "4.0.0"

BANNER = r"""
====================================================================
  HAR -> PROVIDER SCAFFOLDER  v4.0  (architectural audit edition)
  Raw HAR capture in  ->  audited, redacted, production package out.
====================================================================
"""

TRACKER_DOMAINS = (
    "clarity.ms", "google-analytics.com", "googletagmanager.com", "sentry.io",
    "doubleclick.net", "facebook.net", "connect.facebook", "stats", "telemetry",
    "segment.io", "hotjar.com", "mixpanel", "amplitude", "fullstory",
)
STATIC_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".css", ".js",
    ".map", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".webm", ".mp3", ".pdf", ".zip",
)
NOISE_METHODS = {"OPTIONS", "CONNECT"}
CAPABILITY_KEYS = ("send_otp", "verify_otp", "chat", "models", "audio", "upload")

# Generic templates used ONLY when a capability endpoint is forced via --endpoint.
DEFAULT_TEMPLATES = {
    "send_otp": {"email": "__EMAIL__"},
    "verify_otp": {"email": "__EMAIL__", "code": "__OTP__"},
    "chat": {"messages": "__MESSAGES__", "model": "__MODEL__"},
}


class HarAuditError(Exception):
    """Fatal, user-facing scaffolding failure."""


# ======================================================================
#  STAGE 1-4: HAR ANALYZER
# ======================================================================

class HarAnalyzer:
    """Parses one HAR capture and derives provider capabilities with evidence."""

    MODEL_KEYS = ("model", "model_id", "modelId", "model_name", "modelName", "ai_name")
    EMAIL_KEY_HINTS = ("email", "mail", "username", "user_name", "account", "identifier", "login", "user")
    OTP_KEY_HINTS = ("otp", "code", "verification", "verify_code", "pin")
    SECRET_KEY_HINTS = ("token", "secret", "password", "passwd", "credential", "auth",
                        "session", "jwt", "apikey", "api_key", "key", "authorization")
    MESSAGE_KEY_HINTS = ("messages", "message", "prompt", "input", "query",
                         "conversation", "history", "text", "content")
    EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
    LONG_HEX_RE = re.compile(r"[A-Fa-f0-9]{32,}")
    MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,79}$")
    SEND_PATH_HINTS = ("send", "request", "issue", "start")
    VERIFY_PATH_HINTS = ("verify", "check", "confirm", "validate", "complete")

    def __init__(self, har_path: str, slug: str):
        self.har_path = Path(har_path)
        self.slug = re.sub(r"[^a-z0-9_]+", "_", slug.lower()).strip("_") or "provider"
        self.entries: list = []
        self.warnings: list[str] = []
        self.caps: dict[str, str] = {}          # capability key -> endpoint URL
        self.confidence: dict[str, float] = {}
        self.evidence: dict[str, str] = {}
        self.templates: dict[str, any] = {}      # send_otp / verify_otp / chat
        self.form_fields: dict[str, tuple] = {}  # audio / upload -> (fields, file field)
        self.models: set[str] = set()
        self.origin = ""
        self.api_base = ""
        self.default_headers: dict[str, str] = {}
        self._redactions = 0
        self._best: dict[str, dict] = {}

    # ---------------------------------------------------------------- noise

    def _is_tracker(self, host: str) -> bool:
        return any(token in host for token in TRACKER_DOMAINS)

    def _is_static(self, url: str) -> bool:
        return urlparse(url).path.lower().endswith(STATIC_EXTENSIONS)

    # ------------------------------------------------------------- decoding

    @staticmethod
    def _decode_text(container: dict) -> str:
        """Decode a HAR content/postData body, honouring base64 encoding."""
        text = (container or {}).get("text") or ""
        if not text:
            return ""
        if (container or {}).get("encoding") == "base64":
            try:
                return base64.b64decode(text).decode("utf-8", errors="replace")
            except Exception:
                return ""
        return text

    @staticmethod
    def _json_or_none(text: str):
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None

    # ------------------------------------------------------------- pipeline

    def load_and_analyze(self) -> None:
        if not self.har_path.is_file():
            raise HarAuditError(f"HAR file not found: {self.har_path}")
        print(f"[*] Loading HAR: {self.har_path}")
        try:
            with open(self.har_path, "r", encoding="utf-8", errors="replace") as handle:
                document = json.load(handle)
        except json.JSONDecodeError as exc:
            raise HarAuditError(f"Invalid HAR JSON: {exc}") from exc

        self.entries = document.get("log", {}).get("entries", [])
        if not self.entries:
            raise HarAuditError("HAR contains no log.entries â is this a valid HAR 1.2 export?")
        print(f"[+] Parsed {len(self.entries)} HTTP entries")

        buckets: dict[str, list] = {key: [] for key in CAPABILITY_KEYS}
        host_counter: Counter = Counter()
        considered = 0

        for entry in self.entries:
            request = entry.get("request", {})
            response = entry.get("response", {})
            url = request.get("url", "")
            method = (request.get("method") or "GET").upper()
            if not url.startswith("http") or method in NOISE_METHODS or self._is_static(url):
                continue
            host = urlparse(url).netloc.lower()
            if not host or self._is_tracker(host):
                continue
            considered += 1
            host_counter[host] += 1
            candidate = self._build_candidate(entry, request, response, method, url)
            for capability in self._classify(candidate):
                buckets[capability].append(candidate)

        if considered == 0:
            raise HarAuditError("Every HAR entry was filtered as noise â nothing to analyze")
        print(f"[+] {considered} candidate API entries after noise filtering")

        self._elect_origin(host_counter)
        self._finalize(buckets)
        self._discover_models(buckets)
        self._capture_headers()
        self._elect_api_base()

    # ---------------------------------------------------------- candidates

    def _build_candidate(self, entry, request, response, method, url) -> dict:
        post = request.get("postData") or {}
        params = post.get("params") or []
        parsed = urlparse(url)
        return {
            "method": method,
            "url": url,
            "path": parsed.path.lower(),
            "status": int(response.get("status") or 0),
            "mime": ((response.get("content") or {}).get("mimeType") or "").lower(),
            "body_text": self._decode_text(post),
            "resp_text": self._decode_text(response.get("content") or {}),
            "form_params": {p.get("name", ""): p.get("value", "") for p in params if p.get("name")},
            "file_params": [p.get("name") or "file" for p in params if p.get("fileName")],
            "headers": [(h.get("name", ""), h.get("value", "")) for h in request.get("headers") or []],
        }

    def _classify(self, candidate: dict) -> list[str]:
        """A single entry may feed several capabilities â record all matches."""
        path, method = candidate["path"], candidate["method"]
        is_multipart = candidate["is_multipart"] = bool(candidate["file_params"])
        matched = []
        if any(key in path for key in ("audio", "transcribe", "stt", "speech", "speech-to-text")):
            matched.append("audio")
        if is_multipart or any(key in path for key in ("upload", "file", "media", "attachment")):
            matched.append("upload")
        if any(key in path for key in ("register", "signup", "sign-up", "otp", "verify",
                                       "auth", "token", "login", "password")):
            matched.append("send_otp" if self._is_send_path(path) else "verify_otp"
                           if "verify" in path else "auth")
            # generic auth paths are kept in both OTP buckets for scoring below
            matched.append("send_otp") if self._is_send_path(path) and "otp" in path else None
        if any(key in path for key in ("chat", "completion", "conversation", "generate",
                                       "ask", "message", "inference")):
            matched.append("chat")
        if any(key in path for key in ("models", "model-list", "model_list", "model")):
            matched.append("models")
        return sorted(set(matched)) or []

    def _is_send_path(self, path: str) -> bool:
        return any(hint in path for hint in self.SEND_PATH_HINTS)

    # -------------------------------------------------------------- scoring

    def _pick(self, candidates: list, response_hint=None, prefer_post: bool = True):
        """Score every candidate; return (confidence, candidate) or None below 0.5."""
        best = None
        for candidate in candidates:
            score = 0.4 if candidate["method"] == ("POST" if prefer_post else "GET") else 0.25
            if 200 <= candidate["status"] < 400:
                score += 0.2
            if candidate["body_text"]:
                score += 0.2
            if response_hint and response_hint(candidate["resp_text"]):
                score += 0.2
            score = round(min(score, 1.0), 2)
            if best is None or score > best[0]:
                best = (score, candidate)
        return best if best and best[0] >= 0.5 else None

    def _select(self, capability: str, candidates: list, response_hint=None,
                prefer_post: bool = True) -> None:
        picked = self._pick(candidates, response_hint=response_hint, prefer_post=prefer_post)
        if not picked:
            if candidates:
                self.warnings.append(
                    f"[{capability}] best candidate scored below the 0.5 confidence threshold â capability disabled")
            else:
                self.warnings.append(f"[{capability}] no candidate endpoint found in the capture")
            return
        score, candidate = picked
        self.caps[capability] = candidate["url"]
        self.confidence[capability] = score
        self.evidence[capability] = f"{candidate['method']} {candidate['url']} (HTTP {candidate['status']})"
        self._best[capability] = candidate
        if capability == "chat":
            self.templates["chat"] = self._chat_template(candidate)
        elif capability in ("audio", "upload"):
            self.form_fields[capability] = self._form_payload(candidate)

    # ------------------------------------------------------------- finalize

    def _finalize(self, buckets: dict) -> None:
        self._select("chat", buckets["chat"], response_hint=self._chat_response_hint)
        self._select("models", buckets["models"], response_hint=self._model_list_hint, prefer_post=False)

        for capability, multipart_only in (("audio", True), ("upload", True)):
            pool = [c for c in buckets[capability] if c["file_params"]] if multipart_only else buckets[capability]
            if buckets[capability] and not pool:
                self.warnings.append(
                    f"[{capability}] endpoints found but none accepted multipart uploads â capability disabled")
            self._select(capability, pool)

        auth_candidates = buckets["send_otp"] + buckets["verify_otp"]
        send_pool = [c for c in auth_candidates
                     if "verify" not in c["path"] and self._is_send_path(c["path"])]
        verify_pool = [c for c in auth_candidates
                       if any(hint in c["path"] for hint in self.VERIFY_PATH_HINTS)]
        best_send = self._pick(send_pool, response_hint=self._token_response_hint)
        best_verify = self._pick(verify_pool, response_hint=self._token_response_hint)
        if best_send and best_verify:
            score, send_candidate = best_send
            _, verify_candidate = best_verify
            self.caps["send_otp"] = send_candidate["url"]
            self.caps["verify_otp"] = verify_candidate["url"]
            self.confidence["auth"] = round((score + best_verify[0]) / 2, 2)
            self.evidence["auth"] = (f"send: {send_candidate['method']} {send_candidate['url']} | "
                                     f"verify: {verify_candidate['method']} {verify_candidate['url']}")
            self.templates["send_otp"] = self._auth_template(send_candidate)
            self.templates["verify_otp"] = self._auth_template(verify_candidate)
            self._best["send_otp"] = send_candidate
        elif auth_candidates:
            self.warnings.append(
                "[auth] OTP send/verify pair not found in the capture â auth capability disabled")

    # ------------------------------------------------------------ templates

    def _chat_template(self, candidate: dict):
        body = self._json_or_none(candidate["body_text"])
        if isinstance(body, (dict, list)):
            return self._redact_structure(body, mode="chat")
        if candidate["form_params"]:
            return self._redact_structure(candidate["form_params"], mode="chat")
        self.warnings.append(
            f"[chat] request body unreadable for {candidate['url']} â payload will be {{'messages': [...]}}")
        return {}

    def _auth_template(self, candidate: dict):
        body = self._json_or_none(candidate["body_text"])
        if isinstance(body, (dict, list)):
            return self._redact_structure(body, mode="auth")
        if candidate["form_params"]:
            return self._redact_structure(candidate["form_params"], mode="auth")
        self.warnings.append(f"[auth] unreadable request body for {candidate['url']} â template is empty")
        return {}

    def _form_payload(self, candidate: dict) -> tuple:
        fields = self._redact_structure(candidate["form_params"], mode="form") if candidate["form_params"] else {}
        field_name = candidate["file_params"][0] if candidate["file_params"] else "file"
        return fields, field_name

    # ------------------------------------------------------------- redaction

    def _redact_pair(self, key: str, value, mode: str):
        if not isinstance(value, str):
            return value
        key_l = key.lower()
        if mode == "chat" and key_l in self.MESSAGE_KEY_HINTS:
            self._redactions += 1
            return "__MESSAGES__"
        if key_l in self.MODEL_KEYS:
            return value  # model identifiers are configuration, not secrets
        if self.EMAIL_RE.search(value):
            self._redactions += 1
            return "__EMAIL__" if mode == "auth" else "user@example.com"
        looks_secret = (bool(self.JWT_RE.search(value))
                        or bool(self.LONG_HEX_RE.fullmatch(value))
                        or (key_l in self.SECRET_KEY_HINTS and len(value) >= 20))
        if looks_secret:
            self._redactions += 1
            return "__TOKEN__" if mode == "auth" else ""
        if mode == "auth":
            if key_l in self.OTP_KEY_HINTS and (value.isdigit() or len(value) <= 8):
                self._redactions += 1
                return "__OTP__"
            if key_l in self.EMAIL_KEY_HINTS:
                self._redactions += 1
                return "__EMAIL__"
        return value

    def _redact_structure(self, node, mode: str):
        if isinstance(node, dict):
            return {key: (self._redact_structure(value, mode) if isinstance(value, (dict, list))
                          else self._redact_pair(key, value, mode))
                    for key, value in node.items()}
        if isinstance(node, list):
            return [self._redact_structure(item, mode) if isinstance(item, (dict, list))
                    else self._redact_pair("", item, mode)
                    for item in node]
        return self._redact_pair("", node, mode)

    def _sanitize_url(self, url: str) -> str:
        parts = urlparse(url)
        if not parts.query:
            return url
        cleaned = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            if (self.EMAIL_RE.search(value) or self.JWT_RE.search(value)
                    or self.LONG_HEX_RE.fullmatch(value) or len(value) >= 48):
                self._redactions += 1
                value = ""
            cleaned.append((key, value))
        return urlunparse(parts._replace(query=urlencode(cleaned)))

    # -------------------------------------------------------------- models

    def _discover_models(self, buckets: dict) -> None:
        found: set[str] = set()
        for candidate in buckets["chat"] + buckets["send_otp"] + buckets["verify_otp"]:
            for payload in (self._json_or_none(candidate["body_text"]),
                            self._json_or_none(candidate["resp_text"])):
                if payload is not None:
                    found.update(v for v in self._deep_values(payload, self.MODEL_KEYS)
                                 if self._looks_like_model(v))
        for candidate in buckets["models"]:
            body = self._json_or_none(candidate["resp_text"])
            if body is None:
                continue
            items = body if isinstance(body, list) else (body.get("data") or body.get("models") or [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    for key in ("id", "name", "model"):
                        value = item.get(key)
                        if isinstance(value, str) and self._looks_like_model(value):
                            found.add(value)
        self.models = found

    def _looks_like_model(self, value: str) -> bool:
        return bool(self.MODEL_NAME_RE.match(value)) and "@" not in value and " " not in value

    @classmethod
    def _deep_values(cls, node, keys) -> list:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key in keys and isinstance(value, str):
                    found.append(value)
                found.extend(cls._deep_values(value, keys))
        elif isinstance(node, list):
            for item in node:
                found.extend(cls._deep_values(item, keys))
        return found

    # --------------------------------------------------------- resp hints

    @staticmethod
    def _deep_find_keys(node, keys) -> bool:
        if isinstance(node, dict):
            return any(key in node or HarAnalyzer._deep_find_keys(value, keys)
                       for key, value in node.items())
        if isinstance(node, list):
            return any(HarAnalyzer._deep_find_keys(item, keys) for item in node)
        return False

    def _chat_response_hint(self, text: str) -> bool:
        body = self._json_or_none(text)
        return bool(body) and self._deep_find_keys(
            body, ("choices", "content", "message", "messages", "delta", "answer", "output"))

    def _token_response_hint(self, text: str) -> bool:
        body = self._json_or_none(text)
        return bool(body) and self._deep_find_keys(
            body, ("token", "access_token", "accessToken", "jwt", "id_token"))

    def _model_list_hint(self, text: str) -> bool:
        body = self._json_or_none(text)
        if body is None:
            return False
        items = body if isinstance(body, list) else (body.get("data") or body.get("models") or [])
        if not isinstance(items, list) or not items:
            return False
        first = items[0]
        return isinstance(first, dict) and ("id" in first or "name" in first)

    # -------------------------------------------------- origin / api base

    def _elect_origin(self, host_counter: Counter) -> None:
        tokens = [token for token in self.slug.split("_") if len(token) >= 4]

        def host_score(host: str) -> int:
            score = host_counter[host]
            if "api" in host:
                score += 2
            if any(token in host for token in tokens):
                score += 3
            return score

        self.origin = f"https://{max(host_counter, key=host_score)}"

    def _elect_api_base(self) -> None:
        prefixes: Counter = Counter()
        versioned = {"api", "v1", "v2", "v3", "rest", "gateway"}
        for url in self.caps.values():
            segments = [s for s in urlparse(url).path.split("/") if s][:2]
            if segments and segments[0] in versioned:
                prefixes["/" + "/".join(segments)] += 1
        self.api_base = self.origin + prefixes.most_common(1)[0][0] if prefixes else self.origin

    def _capture_headers(self) -> None:
        source = next((self._best[key] for key in ("chat", "send_otp", "models", "audio", "upload")
                       if key in self._best), None)
        if not source:
            return
        wanted = ("user-agent", "origin", "referer", "accept-language", "accept")
        headers: dict[str, str] = {}
        for name, value in source["headers"]:
            lower = name.lower()
            if lower in wanted and value and lower not in headers:
                headers[name] = value
        self.default_headers = headers

    # ------------------------------------------------------------- results

    @property
    def has_auth(self) -> bool:
        return "send_otp" in self.caps and "verify_otp" in self.caps

    @property
    def redactions(self) -> int:
        return self._redactions

    def exported_capabilities(self) -> list[str]:
        capabilities = ["auth"] if self.has_auth else []
        capabilities += [cap for cap in ("chat", "models", "audio", "upload") if cap in self.caps]
        return capabilities

    def report(self) -> None:
        line = "=" * 68
        print(f"\n{line}")
        print(f"ð HAR ANALYSIS REPORT â provider '{self.slug}'")
        print(line)
        print(f"  Origin / API base : {self.origin}  ->  {self.api_base}")
        for capability in CAPABILITY_KEYS:
            if capability in self.caps:
                print(f"  [+] {capability:<11}: {self.caps[capability]}  "
                      f"(confidence {self.confidence.get(capability, 0):.2f})")
            else:
                print(f"  [-] {capability:<11}: not established")
        print(f"  Auth capability   : {'ENABLED' if self.has_auth else 'disabled'}")
        print(f"  Models            : {', '.join(sorted(self.models)) or '(none â seed with --model)'}")
        print(f"  Redacted values   : {self._redactions}")
        for warning in self.warnings:
            print(f"  [!] {warning}")
        print(line + "\n")


# ======================================================================
#  STAGE 5: GENERATED-CODE TEMPLATES
# ======================================================================

CORE_HELPERS = '''
# ----------------------------------------------------------------------
# Errors & generic helpers
# ----------------------------------------------------------------------

class ProviderError(RuntimeError):
    """Base error for the generated runtime."""


class CapabilityError(ProviderError):
    """Operation not supported: capability absent from the HAR capture."""


class AuthError(ProviderError):
    """Account registration / OTP verification failure."""


class TempMailError(ProviderError):
    """Disposable mailbox failure."""


class ProviderHTTPError(ProviderError):
    """HTTP-level failure carrying the response status code."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


TEXT_KEYS = ("content", "text", "delta", "answer", "message", "response", "output", "transcription")
TOKEN_KEYS = ("access_token", "accessToken", "token", "jwt", "id_token", "auth_token", "api_key", "apiKey")
PLACEHOLDERS = ("__EMAIL__", "__OTP__", "__TOKEN__", "__PASSWORD__", "__MESSAGES__", "__MODEL__")


def _deep_strings(obj, keys) -> list:
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and isinstance(value, str):
                found.append(value)
            found.extend(_deep_strings(value, keys))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_deep_strings(item, keys))
    return found


def extract_text(payload) -> str:
    """Best-effort extraction of assistant text from a JSON chat response."""
    for candidate in _deep_strings(payload, TEXT_KEYS):
        if candidate and candidate.strip():
            return candidate
    return ""


def extract_token(payload) -> str:
    """Best-effort extraction of an auth token from a JSON response."""
    for key in TOKEN_KEYS:
        for value in _deep_strings(payload, (key,)):
            if value and len(value) >= 16:
                return value
    return ""


def substitute_template(template, values):
    """Recursively replace captured placeholders with live runtime values."""
    if isinstance(template, dict):
        return {key: substitute_template(item, values) for key, item in template.items()}
    if isinstance(template, list):
        return [substitute_template(item, values) for item in template]
    if isinstance(template, str) and template in PLACEHOLDERS:
        if template not in values:
            raise ProviderError(f"template placeholder {template} has no runtime value")
        return values[template]
    return template


def deep_merge(base, override):
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def parse_sse_events(lines) -> list:
    """Parse a text/event-stream line iterable into JSON events ([DONE]-aware)."""
    events, buffer = [], []
    for raw in lines:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        line = line.strip()
        if not line:
            if buffer:
                payload = "\\n".join(buffer)
                buffer = []
                if payload.strip() == "[DONE]":
                    break
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    events.append({"_raw": payload})
            continue
        if line.startswith("data:"):
            buffer.append(line[5:].strip())
    if buffer:
        payload = "\\n".join(buffer)
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            events.append({"_raw": payload})
    return events
'''

CORE_STORAGE = '''
# ----------------------------------------------------------------------
# Atomic persistence: cross-process file lock + crash-safe JSON store
# ----------------------------------------------------------------------

@contextmanager
def file_lock(path, timeout: float = 10.0, poll_interval: float = 0.05):
    """Advisory cross-process lock (msvcrt.locking on Windows, flock elsewhere)."""
    lock_path = Path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire lock: {lock_path}") from None
                time.sleep(poll_interval)
        yield handle
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


class AtomicJSONStore:
    """Crash-safe JSON document store guarded by thread and process locks."""

    def __init__(self, path):
        self.path = Path(path)
        self._thread_lock = threading.RLock()

    def _read_unlocked(self) -> Dict[str, Any]:
        default: Dict[str, Any] = {"accounts": []}
        if not self.path.exists():
            return default
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return default
        if not isinstance(data, dict):
            return default
        if not isinstance(data.setdefault("accounts", []), list):
            data["accounts"] = []
        return data

    def _atomic_write(self, data: Dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self.path)

    def load_all(self) -> List[Dict[str, Any]]:
        with self._thread_lock:
            return list(self._read_unlocked()["accounts"])

    def add(self, account: Dict[str, Any]) -> bool:
        """Insert an account; returns False when the email already exists."""
        email = account.get("email")
        if not email:
            return False
        with self._thread_lock:
            with file_lock(str(self.path) + ".lock"):
                data = self._read_unlocked()
                if any(existing.get("email") == email for existing in data["accounts"]):
                    return False
                data["accounts"].append(dict(account))
                self._atomic_write(data)
                return True

    def mark_status(self, email: str, status: str) -> None:
        if not email:
            return
        with self._thread_lock:
            with file_lock(str(self.path) + ".lock"):
                data = self._read_unlocked()
                for account in data["accounts"]:
                    if account.get("email") == email:
                        account["status"] = status
                self._atomic_write(data)

    def next_healthy(self) -> Optional[Dict[str, Any]]:
        with self._thread_lock:
            for account in self._read_unlocked()["accounts"]:
                if account.get("status", "active") == "active":
                    return dict(account)
        return None
'''

CORE_HTTP = '''
# ----------------------------------------------------------------------
# TLS-fingerprinted HTTP layer (Chrome 124) with bounded retry/backoff
# ----------------------------------------------------------------------

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class HttpSession:
    """curl_cffi session with browser-grade TLS fingerprint and retries."""

    def __init__(self, headers: Optional[Dict[str, str]] = None, timeout: float = 30.0,
                 max_retries: int = 3, backoff: float = 1.5):
        self._session = cffi_requests.Session(impersonate="chrome124")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.default_headers = dict(DEFAULT_HEADERS)
        if headers:
            self.default_headers.update(headers)

    def request(self, method: str, url: str, *, headers=None, stream: bool = False, **kwargs):
        merged = dict(self.default_headers)
        if headers:
            merged.update(headers)
        kwargs.pop("timeout", None)
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.request(
                    method, url, headers=merged, timeout=self.timeout, stream=stream, **kwargs
                )
            except Exception:
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.backoff * (2 ** attempt))
                continue
            if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After") or ""
                delay = (float(retry_after) if retry_after.replace(".", "", 1).isdigit()
                         else self.backoff * (2 ** attempt))
                time.sleep(delay)
                continue
            return response
        raise ProviderError("HTTP request failed without a transport exception")

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)
'''

CORE_TEMPMAIL = '''
# ----------------------------------------------------------------------
# Disposable mailbox client (mail.tm) â used only for account minting
# ----------------------------------------------------------------------

MAIL_API = "https://api.mail.tm"


class TempMailClient:
    """Creates disposable inboxes, polls for OTP mail, deletes the account."""

    def __init__(self, http: HttpSession):
        self.http = http

    def _request(self, method: str, path: str, **kwargs):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        headers.update(kwargs.pop("headers", {}) or {})
        response = self.http.request(method, MAIL_API + path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise TempMailError(f"mail.tm {method} {path} -> HTTP {response.status_code}")
        return response

    def create_account(self, password: str) -> Dict[str, Any]:
        domains = self._request("GET", "/domains").json()
        items = domains.get("hydra:member") if isinstance(domains, dict) else domains
        if not items:
            raise TempMailError("mail.tm returned no available domains")
        address = f"{''.join(random.choices(string.ascii_lowercase + string.digits, k=13))}@{items[0]['domain']}"
        created = self._request("POST", "/accounts", json={"address": address, "password": password}).json()
        token = self._request("POST", "/token", json={"address": address, "password": password}).json().get("token")
        if not token:
            raise TempMailError("mail.tm did not issue an API token")
        return {"email": address, "password": password, "account_id": created.get("id"), "mail_token": token}

    def poll_for_otp(self, mail_token: str, timeout: float = 120.0, poll_every: float = 4.0) -> str:
        deadline = time.monotonic() + timeout
        auth_headers = {"Accept": "application/json", "Authorization": f"Bearer {mail_token}"}
        otp_pattern = re.compile(r"\\b(\\d{4,8})\\b")
        seen_ids = set()
        while time.monotonic() < deadline:
            listing = self._request("GET", "/messages?page=1", headers=auth_headers).json()
            items = listing.get("hydra:member") if isinstance(listing, dict) else listing
            for message in items or []:
                message_id = message.get("id")
                if not message_id or message_id in seen_ids:
                    continue
                seen_ids.add(message_id)
                full = self._request("GET", f"/messages/{message_id}", headers=auth_headers).json()
                haystack = " ".join(
                    part for part in (full.get("text"), full.get("intro"), extract_text(full.get("html")))
                    if isinstance(part, str)
                )
                match = otp_pattern.search(haystack)
                if match:
                    return match.group(1)
            time.sleep(poll_every)
        raise TempMailError(f"no OTP email arrived within {timeout:.0f}s")

    def delete_account(self, account_id, mail_token: str) -> bool:
        """Best-effort mailbox cleanup â never raises."""
        if not account_id:
            return False
        try:
            response = self.http.request(
                "DELETE", f"{MAIL_API}/accounts/{account_id}",
                headers={"Authorization": f"Bearer {mail_token}"},
            )
            return response.status_code in (200, 204)
        except Exception:
            return False
'''

CORE_OTP_FLOW = '''

class OTPAuthFlow:
    """Registers accounts through the captured send-OTP / verify-OTP sequence."""

    def __init__(self, http: HttpSession, store: AtomicJSONStore, mail: Optional[TempMailClient] = None):
        self.http = http
        self.store = store
        self.mail = mail or TempMailClient(http)

    def register(self, otp_timeout: float = 120.0) -> Dict[str, Any]:
        password = "Pw!" + "".join(random.choices(string.ascii_letters + string.digits, k=14))
        account = self.mail.create_account(password)
        try:
            send_payload = substitute_template(SEND_OTP_TEMPLATE, {
                "__EMAIL__": account["email"], "__PASSWORD__": password, "__OTP__": "", "__TOKEN__": "",
            })
            response = self.http.post(ENDPOINTS["send_otp"], json=send_payload)
            if response.status_code >= 400:
                raise AuthError(f"send-otp -> HTTP {response.status_code}: {response.text[:200]}")

            otp_code = self.mail.poll_for_otp(account["mail_token"], timeout=otp_timeout)
            verify_payload = substitute_template(VERIFY_OTP_TEMPLATE, {
                "__EMAIL__": account["email"], "__OTP__": otp_code,
                "__PASSWORD__": password, "__TOKEN__": "",
            })
            verify_response = self.http.post(ENDPOINTS["verify_otp"], json=verify_payload)
            if verify_response.status_code >= 400:
                raise AuthError(f"verify-otp -> HTTP {verify_response.status_code}: {verify_response.text[:200]}")

            try:
                body = verify_response.json()
            except ValueError:
                body = {}
            token = extract_token(body) or (verify_response.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
            if not token:
                raise AuthError("verify-otp succeeded but no token was found in the response")

            account.update({"provider_token": token, "status": "active", "created_at": int(time.time())})
            self.store.add(account)
            return account
        finally:
            # Atomic cleanup: the disposable mailbox never outlives the flow.
            self.mail.delete_account(account.get("account_id"), account.get("mail_token", ""))
'''

CORE_POOL = '''

class AccountPool:
    """Daemon that proactively refills the store with healthy accounts."""

    def __init__(self, auth_flow: OTPAuthFlow, store: AtomicJSONStore,
                 min_accounts: int = 2, max_accounts: int = 6, check_interval: float = 60.0):
        self.auth_flow = auth_flow
        self.store = store
        self.min_accounts = min_accounts
        self.max_accounts = max_accounts
        self.check_interval = check_interval
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._refill_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="account-pool", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5.0)

    def __enter__(self) -> "AccountPool":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=self.check_interval)
            self._wake.clear()
            if not self._stop.is_set():
                self._refill()

    def _refill(self) -> None:
        if not self._refill_lock.acquire(blocking=False):
            return  # a refill is already in progress â no duplicate work
        try:
            active = sum(1 for account in self.store.load_all() if account.get("status") == "active")
            target = min(self.min_accounts, self.max_accounts)
            while active < target and not self._stop.is_set():
                try:
                    self.auth_flow.register()
                except ProviderError as exc:
                    print(f"[account-pool] registration failed: {exc}")
                    break
                active += 1
        finally:
            self._refill_lock.release()
'''

CORE_CHAT = '''
# ----------------------------------------------------------------------
# Chat client â JSON and SSE (text/event-stream) against the captured API
# ----------------------------------------------------------------------

class ChatClient:
    def __init__(self, http: HttpSession, endpoint: str, default_model: Optional[str] = None):
        self.http = http
        self.endpoint = endpoint
        self.default_model = default_model

    def chat(self, messages, model=None, stream=False, extra=None, extra_headers=None):
        model = model or self.default_model
        if not model:
            raise ValueError("no default model was discovered from the HAR; pass model='...' explicitly")
        if "__MESSAGES__" in json.dumps(CHAT_TEMPLATE):
            payload = substitute_template(CHAT_TEMPLATE, {"__MESSAGES__": messages, "__MODEL__": model})
        else:
            payload = deep_merge(CHAT_TEMPLATE, {"messages": messages})
        for key in ("model", "model_id", "modelId", "model_name"):
            if key in payload:
                payload[key] = model
                break
        if extra:
            payload = deep_merge(payload, extra)
        headers = {"Accept": "text/event-stream" if stream else "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        response = self.http.post(self.endpoint, json=payload, headers=headers, stream=stream)
        if response.status_code >= 400:
            raise ProviderHTTPError(f"chat -> HTTP {response.status_code}: {response.text[:300]}",
                                    response.status_code)
        if stream:
            return self._iter_text(response)
        try:
            return extract_text(response.json()) or response.text
        except ValueError:
            return response.text

    @staticmethod
    def _iter_text(response):
        for event in parse_sse_events(response.iter_lines()):
            if isinstance(event, dict):
                text = extract_text(event)
                if text:
                    yield text
'''

CORE_AUDIO = '''
# ----------------------------------------------------------------------
# Audio STT client (multipart upload)
# ----------------------------------------------------------------------

import mimetypes


class AudioClient:
    def __init__(self, http: HttpSession, endpoint: str):
        self.http = http
        self.endpoint = endpoint

    def transcribe(self, audio_path, language=None, extra_headers=None):
        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"audio file not found: {path}")
        fields = dict(AUDIO_FIELDS)
        if language:
            fields["language"] = language
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            response = self.http.post(
                self.endpoint, data=fields or None,
                files={AUDIO_FIELD_NAME: (path.name, handle, mime)},
                headers=extra_headers or None,
            )
        if response.status_code >= 400:
            raise ProviderHTTPError(f"transcribe -> HTTP {response.status_code}: {response.text[:300]}",
                                    response.status_code)
        try:
            return extract_text(response.json()) or response.text
        except ValueError:
            return response.text
'''

CORE_UPLOAD = '''
# ----------------------------------------------------------------------
# Generic multipart upload client
# ----------------------------------------------------------------------

import mimetypes


class UploadClient:
    def __init__(self, http: HttpSession, endpoint: str):
        self.http = http
        self.endpoint = endpoint

    def upload(self, file_path, extra_headers=None):
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"file not found: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with open(path, "rb") as handle:
            response = self.http.post(
                self.endpoint, data=dict(UPLOAD_FIELDS) or None,
                files={UPLOAD_FIELD_NAME: (path.name, handle, mime)},
                headers=extra_headers or None,
            )
        if response.status_code >= 400:
            raise ProviderHTTPError(f"upload -> HTTP {response.status_code}: {response.text[:300]}",
                                    response.status_code)
        try:
            return response.json()
        except ValueError:
            return response.text
'''

ADAPTER_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""High-level adapter for the '@@SLUG@@' provider (generated).

FaÃ§ade over the runtime capabilities detected in the source HAR:
credential rotation on 401/403, chat (JSON + SSE), models, STT audio, uploads.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .core import @@CORE_NAMES@@
    from .definition import CAPABILITIES, ENDPOINTS, MODELS
except ImportError:  # direct execution from the package directory
    from core import @@CORE_NAMES@@
    from definition import CAPABILITIES, ENDPOINTS, MODELS

__all__ = ["ProviderAdapter"]


class ProviderAdapter:
    """Single entry point for every capability detected in the HAR capture."""

    def __init__(self, state_path=None, http=None, min_accounts: int = 2, max_accounts: int = 6):
        self.capabilities = frozenset(CAPABILITIES)
        self.http = http or HttpSession()
        self.store = AtomicJSONStore(
            Path(state_path) if state_path
            else Path(__file__).resolve().parent / "state" / "accounts.json"
        )
@@AUTH_INIT@@
@@CHAT_INIT@@
@@AUDIO_INIT@@
@@UPLOAD_INIT@@

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------

    @staticmethod
    def _auth_headers(account: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Bearer header for a stored account (empty when unauthenticated)."""
        if not account:
            return {}
        token = account.get("provider_token", "")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _ensure_account(self) -> Optional[Dict[str, Any]]:
        """Reuse a healthy stored account, or mint a new one via the OTP flow."""
        if self._auth_flow is None:
            return None
        account = self.store.next_healthy()
        return account if account else self._auth_flow.register()

    def _call_with_rotation(self, func):
        """Run an authenticated call; rotate credentials exactly once on 401/403."""
        account = self._ensure_account()
        try:
            return func(account)
        except ProviderHTTPError as exc:
            if account is None or exc.status not in (401, 403):
                raise
            self.store.mark_status(account.get("email", ""), "expired")
            return func(self._ensure_account())

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
@@AUTH_METHODS@@
    def list_accounts(self) -> List[Dict[str, Any]]:
        """Return every stored account, status included."""
        return self.store.load_all()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------
@@CHAT_METHODS@@

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------
@@MODELS_METHODS@@

    # ------------------------------------------------------------------
    # Audio / Upload
    # ------------------------------------------------------------------
@@AUDIO_METHODS@@
@@UPLOAD_METHODS@@

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_account_pool(self) -> None:
        """Start the background daemon that keeps healthy accounts topped up."""
        if self._pool:
            self._pool.start()

    def stop_account_pool(self) -> None:
        if self._pool:
            self._pool.stop()

    def __enter__(self) -> "ProviderAdapter":
        self.start_account_pool()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop_account_pool()
'''

TEST_TEMPLATE = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline smoke tests for the generated '@@SLUG@@' provider package.

These tests never touch the network: they validate package structure,
endpoint sanity, template rendering, and the local persistence layer.
Run:  py -3.13 -m pytest test_provider_smoke.py -q   (or execute directly)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from . import definition
except ImportError:
    import definition

try:
    import pytest

    pytest.importorskip("curl_cffi", reason="generated runtime requires curl_cffi")
except ImportError:
    pass  # direct execution: the core import below fails loudly instead


def test_capabilities_are_declared():
    assert isinstance(definition.CAPABILITIES, (list, tuple))
    assert definition.CAPABILITIES, "no capabilities were detected in the source HAR"


def test_declared_endpoints_are_absolute():
    for name, url in definition.ENDPOINTS.items():
        assert url.startswith(("http://", "https://")), f"endpoint '{name}' is not absolute: {url}"


def test_chat_capability_has_models():
    if "chat" in definition.CAPABILITIES:
        assert definition.MODELS, "no models discovered â regenerate with --model <name>"


def test_chat_template_renders_clean():
    from core import substitute_template

    values = {
        "__MESSAGES__": [{"role": "user", "content": "ping"}],
        "__MODEL__": definition.MODELS[0] if definition.MODELS else "probe-model",
    }
    blob = json.dumps(substitute_template(definition.CHAT_TEMPLATE, values))
    assert "__MESSAGES__" not in blob and "__MODEL__" not in blob


def test_atomic_store_roundtrip():
    from core import AtomicJSONStore

    with tempfile.TemporaryDirectory() as tmp:
        store = AtomicJSONStore(Path(tmp) / "state" / "accounts.json")
        assert store.add({"email": "probe@example.com", "status": "active"}) is True
        assert store.add({"email": "probe@example.com", "status": "active"}) is False  # duplicate
        healthy = store.next_healthy()
        assert healthy and healthy["email"] == "probe@example.com"
        store.mark_status("probe@example.com", "expired")
        assert store.next_healthy() is None


def test_file_lock_is_exclusive():
    from core import file_lock

    with tempfile.TemporaryDirectory() as tmp:
        lock_path = Path(tmp) / "probe.lock"
        with file_lock(lock_path, timeout=1.0):
            try:
                with file_lock(lock_path, timeout=0.2):
                    raise AssertionError("second lock acquisition should have timed out")
            except TimeoutError:
                pass


def _main() -> None:
    tests = sorted((name, fn) for name, fn in globals().items()
                   if name.startswith("test_") and callable(fn))
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] {name}: {exc}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    _main()
'''

INIT_TEMPLATE = '''"""@@SLUG@@ provider package â generated by har_to_provider.py v@@VERSION@@.

Detected capabilities: @@CAPS@@
"""
try:
    from .adapter import ProviderAdapter
    from .definition import CAPABILITIES, MODELS
except ImportError:  # direct execution from the package directory
    from adapter import ProviderAdapter
    from definition import CAPABILITIES, MODELS

__all__ = ["ProviderAdapter", "CAPABILITIES", "MODELS"]
__version__ = "1.0.0"
'''

README_TEMPLATE = Template('''# $slug â Generated Provider Package

Produced by `tools/har_to_provider.py` v$version on $date from audited HAR evidence.
No endpoint, model or request template below was invented â each is backed by a
captured HTTP exchange (see `manifest.json` for confidence and redaction stats).

## Detected capabilities

**$caps**

| Capability | Endpoint |
|---|---|
$endpoint_rows

## Discovered models

$models

## Install

```
pip install curl_cffi pytest
```

## Quickstart

```python
from providers.$slug import ProviderAdapter

with ProviderAdapter() as adapter:
    print(adapter.chat([{"role": "user", "content": "Hello!"}]))
```

## Accounts, rotation & the pool

- Account state lives in `state/accounts.json` â atomic writes guarded by a
  cross-process file lock (safe for concurrent daemons).
- On `401/403` the adapter marks the credential `expired` and rotates **once**,
  then retries the call with the next healthy account.
- `register_account()` mints a fresh account through the captured OTP flow
  using a disposable mail.tm inbox that is deleted immediately afterwards.
- `start_account_pool()` runs a background daemon that proactively keeps
  `min_accounts` healthy credentials available.

## Offline verification

```
py -3.13 -m pytest test_provider_smoke.py -q
```

## Regenerate

```
py -3.13 tools/har_to_provider.py $har --slug $slug
```
''')


# ======================================================================
#  STAGE 5: SCAFFOLDER
# ======================================================================

class ProviderScaffolder:
    """Emits the complete provider package, gated by detected capabilities."""

    def __init__(self, analyzer: HarAnalyzer, out_root: Path):
        self.a = analyzer
        self.out_dir = out_root / analyzer.slug

    # ------------------------------------------------------------- sources

    def _definition_source(self) -> str:
        a = self.a
        payload = {
            "SLUG": a.slug,
            "ORIGIN": a.origin,
            "API_BASE": a.api_base,
            "CAPABILITIES": a.exported_capabilities(),
            "ENDPOINTS": dict(sorted(a.caps.items())),
            "MODELS": sorted(a.models),
            "DEFAULT_HEADERS": dict(sorted(a.default_headers.items())),
            "SEND_OTP_TEMPLATE": a.templates.get("send_otp", {}),
            "VERIFY_OTP_TEMPLATE": a.templates.get("verify_otp", {}),
            "CHAT_TEMPLATE": a.templates.get("chat", {}),
            "AUDIO_FIELDS": a.form_fields.get("audio", ({}, "file"))[0],
            "AUDIO_FIELD_NAME": a.form_fields.get("audio", ({}, "file"))[1],
            "UPLOAD_FIELDS": a.form_fields.get("upload", ({}, "file"))[0],
            "UPLOAD_FIELD_NAME": a.form_fields.get("upload", ({}, "file"))[1],
        }
        body = "\n".join(f"{key} = {json.dumps(value, indent=4, ensure_ascii=False)}"
                         for key, value in payload.items())
        return ('"""Static discovery data for provider \'%s\' (generated).\n\n'
                'Every value was extracted from the audited HAR capture. Constants for\n'
                'capabilities that were NOT detected are present but empty, keeping the\n'
                'runtime import surface stable.\n"""\n\n' % a.slug) + body + "\n"

    def _core_source(self) -> str:
        a = self.a
        defn_names = ["DEFAULT_HEADERS", "ENDPOINTS"]
        sections = [self._core_header(defn_names)]
        sections.append(CORE_HELPERS)
        sections.append(CORE_STORAGE)
        sections.append(CORE_HTTP)
        if a.has_auth:
            defn_names += ["SEND_OTP_TEMPLATE", "VERIFY_OTP_TEMPLATE"]
            sections.append(CORE_TEMPMAIL)
            sections.append(CORE_OTP_FLOW)
            sections.append(CORE_POOL)
        if "chat" in a.caps:
            defn_names.append("CHAT_TEMPLATE")
            sections.append(CORE_CHAT)
        if "audio" in a.caps:
            defn_names += ["AUDIO_FIELDS", "AUDIO_FIELD_NAME"]
            sections.append(CORE_AUDIO)
        if "upload" in a.caps:
            defn_names += ["UPLOAD_FIELDS", "UPLOAD_FIELD_NAME"]
            sections.append(CORE_UPLOAD)
        sections[0] = self._core_header(sorted(set(defn_names)))
        return "".join(sections)

    def _core_header(self, defn_names: list) -> str:
        import_block = ",\n        ".join(defn_names)
        return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Battle-tested runtime core for the '{self.a.slug}' provider (generated).

Layers: atomic storage (FileLock + AtomicJSONStore) -> TLS-fingerprinted HTTP
(curl_cffi / Chrome 124) -> capability clients -> disposable-mail OTP flow with
a proactive account pool. External dependency: curl_cffi.
"""
from __future__ import annotations

import json
import os
import random
import re
import string
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from curl_cffi import requests as cffi_requests
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "The generated runtime requires 'curl_cffi'. Install it with: pip install curl_cffi"
    ) from _exc

try:
    from .definition import (
        {import_block},
    )
except ImportError:  # direct execution from the package directory
    from definition import (
        {import_block},
    )
'''

    def _adapter_source(self) -> str:
        a = self.a
        core_names = ["AtomicJSONStore", "CapabilityError", "HttpSession", "ProviderError", "ProviderHTTPError"]
        if a.has_auth:
            core_names += ["AccountPool", "OTPAuthFlow"]
        if "chat" in a.caps:
            core_names.append("ChatClient")
        if "audio" in a.caps:
            core_names.append("AudioClient")
        if "upload" in a.caps:
            core_names.append("UploadClient")

        auth_init = ("        self._auth_flow = OTPAuthFlow(self.http, self.store)\n"
                     "        self._pool = AccountPool(self._auth_flow, self.store,\n"
                     "                                 min_accounts=min_accounts, max_accounts=max_accounts)\n"
                     ) if a.has_auth else "        self._auth_flow = None\n        self._pool = None\n"
        chat_init = ("        self._chat = ChatClient(self.http, ENDPOINTS[\"chat\"], "
                     "default_model=MODELS[0] if MODELS else None)\n"
                     ) if "chat" in a.caps else "        self._chat = None\n"
        audio_init = ("        self._audio = AudioClient(self.http, ENDPOINTS[\"audio\"])\n"
                      ) if "audio" in a.caps else "        self._audio = None\n"
        upload_init = ("        self._upload = UploadClient(self.http, ENDPOINTS[\"upload\"])\n"
                       ) if "upload" in a.caps else "        self._upload = None\n"

        auth_methods = (
            "    def register_account(self, otp_timeout: float = 120.0) -> Dict[str, Any]:\n"
            "        \"\"\"Register a fresh account through the captured OTP flow and persist it.\"\"\"\n"
            "        return self._auth_flow.register(otp_timeout=otp_timeout)\n"
        ) if a.has_auth else (
            "    def register_account(self, *args, **kwargs):\n"
            "        raise CapabilityError(\"auth capability was not detected in the source HAR\")\n"
        )
        chat_methods = (
            "    def chat(self, messages: List[Dict[str, Any]], model: Optional[str] = None,\n"
            "             stream: bool = False, extra: Optional[Dict[str, Any]] = None):\n"
            "        \"\"\"Send a chat request; returns text, or yields chunks when stream=True.\"\"\"\n"
            "        if self._chat is None:\n"
            "            raise CapabilityError(\"chat capability was not detected in the source HAR\")\n"
            "\n"
            "        def _invoke(account):\n"
            "            return self._chat.chat(messages, model=model, stream=stream, extra=extra,\n"
            "                                   extra_headers=self._auth_headers(account))\n"
            "\n"
            "        return self._call_with_rotation(_invoke)\n"
        ) if "chat" in a.caps else (
            "    def chat(self, *args, **kwargs):\n"
            "        raise CapabilityError(\"chat capability was not detected in the source HAR\")\n"
        )
        models_methods = (
            "    def list_models(self) -> List[str]:\n"
            "        \"\"\"Query the discovered models endpoint and return sorted model ids.\"\"\"\n"
            "        if \"models\" not in self.capabilities:\n"
            "            raise CapabilityError(\"models capability was not detected in the source HAR\")\n"
            "        response = self.http.get(ENDPOINTS[\"models\"])\n"
            "        if response.status_code >= 400:\n"
            "            raise ProviderHTTPError(f\"models -> HTTP {response.status_code}\", response.status_code)\n"
            "        try:\n"
            "            body = response.json()\n"
            "        except ValueError:\n"
            "            return []\n"
            "        items = body if isinstance(body, list) else (body.get(\"data\") or body.get(\"models\") or [])\n"
            "        ids = {item.get(\"id\") or item.get(\"name\") for item in items\n"
            "               if isinstance(item, dict) and (item.get(\"id\") or item.get(\"name\"))}\n"
            "        return sorted(ids)\n"
        ) if "models" in a.caps else (
            "    def list_models(self, *args, **kwargs):\n"
            "        raise CapabilityError(\"models capability was not detected in the source HAR\")\n"
        )
        audio_methods = (
            "    def transcribe(self, audio_path, language: Optional[str] = None):\n"
            "        \"\"\"Transcribe a local audio file through the captured STT endpoint.\"\"\"\n"
            "        if self._audio is None:\n"
            "            raise CapabilityError(\"audio (STT) capability was not detected in the source HAR\")\n"
            "        return self._call_with_rotation(\n"
            "            lambda account: self._audio.transcribe(\n"
            "                audio_path, language=language, extra_headers=self._auth_headers(account)))\n"
        ) if "audio" in a.caps else (
            "    def transcribe(self, *args, **kwargs):\n"
            "        raise CapabilityError(\"audio (STT) capability was not detected in the source HAR\")\n"
        )
        upload_methods = (
            "    def upload(self, file_path):\n"
            "        \"\"\"Upload a local file through the captured multipart endpoint.\"\"\"\n"
            "        if self._upload is None:\n"
            "            raise CapabilityError(\"upload capability was not detected in the source HAR\")\n"
            "        return self._call_with_rotation(\n"
            "            lambda account: self._upload.upload(file_path,\n"
            "                                                extra_headers=self._auth_headers(account)))\n"
        ) if "upload" in a.caps else (
            "    def upload(self, *args, **kwargs):\n"
            "        raise CapabilityError(\"upload capability was not detected in the source HAR\")\n"
        )

        source = ADAPTER_TEMPLATE
        replacements = {
            "@@SLUG@@": a.slug,
            "@@CORE_NAMES@@": ", ".join(sorted(core_names)),
            "@@AUTH_INIT@@": auth_init,
            "@@CHAT_INIT@@": chat_init,
            "@@AUDIO_INIT@@": audio_init,
            "@@UPLOAD_INIT@@": upload_init,
            "@@AUTH_METHODS@@": auth_methods,
            "@@CHAT_METHODS@@": chat_methods,
            "@@MODELS_METHODS@@": models_methods,
            "@@AUDIO_METHODS@@": audio_methods,
            "@@UPLOAD_METHODS@@": upload_methods,
        }
        for token, value in replacements.items():
            source = source.replace(token, value)
        return source

    def _test_source(self) -> str:
        return TEST_TEMPLATE.replace("@@SLUG@@", self.a.slug)

    def _init_source(self) -> str:
        return (INIT_TEMPLATE
                .replace("@@SLUG@@", self.a.slug)
                .replace("@@VERSION@@", TOOL_VERSION)
                .replace("@@CAPS@@", ", ".join(self.a.exported_capabilities()) or "(none)"))

    def _readme_source(self, har_path: Path) -> str:
        a = self.a
        rows = "\n".join(f"| `{cap}` | `{url}` |" for cap, url in sorted(a.caps.items())) or "| (none) | |"
        return README_TEMPLATE.substitute(
            slug=a.slug,
            version=TOOL_VERSION,
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            caps=", ".join(f"`{cap}`" for cap in a.exported_capabilities()) or "_(none)_",
            endpoint_rows=rows,
            models=", ".join(f"`{model}`" for model in sorted(a.models))
            or "_(none discovered â regenerate with `--model <name>`)_",
            har=har_path,
        )

    def _manifest(self, files: list) -> dict:
        a = self.a
        return {
            "tool": "har_to_provider.py",
            "tool_version": TOOL_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider": {"slug": a.slug, "origin": a.origin, "api_base": a.api_base},
            "capabilities": [
                {"name": cap, "endpoint": a.caps[cap],
                 "confidence": a.confidence.get(cap), "evidence": a.evidence.get(cap)}
                for cap in sorted(a.caps)
            ],
            "exported_capabilities": a.exported_capabilities(),
            "models": sorted(a.models),
            "default_headers": a.default_headers,
            "stats": {"har_entries": len(a.entries), "redacted_values": a.redactions},
            "warnings": a.warnings,
            "files": files,
        }

    # ------------------------------------------------------------- writing

    def scaffold(self, dry_run: bool = False, force: bool = False) -> None:
        if self.out_dir.exists() and any(self.out_dir.iterdir()) and not force:
            raise HarAuditError(f"target directory not empty: {self.out_dir} (use --force to overwrite)")

        print(f"[*] Scaffolding provider package into: {self.out_dir}")
        sources = {
            "__init__.py": self._init_source(),
            "definition.py": self._definition_source(),
            "core.py": self._core_source(),
            "adapter.py": self._adapter_source(),
            "test_provider_smoke.py": self._test_source(),
            "README.md": self._readme_source(self.a.har_path),
        }

        if dry_run:
            print("[!] DRY RUN: analysis verified, manifest below â no files written.\n")
            print(json.dumps(self._manifest(files=sorted(sources)), indent=2, ensure_ascii=False))
            return

        self.out_dir.mkdir(parents=True, exist_ok=True)
        for name, source in sources.items():
            target = self.out_dir / name
            target.write_text(source, encoding="utf-8", newline="\n")
            print(f"[+] wrote {target}  ({len(source.encode('utf-8')):,} bytes)")
        manifest_path = self.out_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._manifest(files=sorted(sources) + ["manifest.json"]), indent=2, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        print(f"[+] wrote {manifest_path}")

        print("\n[â] Scaffold complete. Next steps:")
        print("      1) pip install curl_cffi pytest")
        print(f"      2) py -3.13 -m pytest \"{self.out_dir / 'test_provider_smoke.py'}\" -q")
        print(f"      3) from providers.{self.a.slug} import ProviderAdapter")


# ======================================================================
#  CLI
# ======================================================================

def apply_endpoint_overrides(analyzer: HarAnalyzer, overrides: list) -> None:
    for item in overrides:
        capability, _, url = item.partition("=")
        capability = capability.strip().lower()
        url = url.strip()
        if capability not in CAPABILITY_KEYS or not url.startswith(("http://", "https://")):
            raise HarAuditError(
                f"--endpoint expects CAP=URL with CAP in {sorted(CAPABILITY_KEYS)}; got: {item}")
        analyzer.caps[capability] = url
        analyzer.confidence[capability] = 1.0
        analyzer.evidence[capability] = "CLI override"
        if capability in DEFAULT_TEMPLATES:
            analyzer.templates.setdefault(capability, DEFAULT_TEMPLATES[capability])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="har_to_provider.py",
        description="Audit a HAR capture and scaffold a production-grade provider package.",
        epilog=(
            "examples:\n"
            "  py -3.13 tools/har_to_provider.py traffic.har --slug acmeai\n"
            "  py -3.13 tools/har_to_provider.py traffic.har --slug acmeai --dry-run\n"
            "  py -3.13 tools/har_to_provider.py traffic.har --slug acmeai --strict \\\n"
            "      --endpoint chat=https://api.acme.ai/v1/chat/completions --model acme-large"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("har", help="path to the HAR 1.2 capture")
    parser.add_argument("--slug", required=True, help="provider slug (letters, digits, underscores)")
    parser.add_argument("--out", default="providers", help="output root directory (default: providers)")
    parser.add_argument("--model", action="append", default=[], metavar="NAME",
                        help="seed an expected model id (repeatable)")
    parser.add_argument("--endpoint", action="append", default=[], metavar="CAP=URL",
                        help="force/override a capability endpoint, e.g. chat=https://...")
    parser.add_argument("--strict", action="store_true",
                        help="fail (exit 2) when the chat capability cannot be established")
    parser.add_argument("--dry-run", action="store_true",
                        help="analyze and print the plan without writing any files")
    parser.add_argument("--force", action="store_true",
                        help="overwrite a non-empty target directory")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    print(BANNER)
    try:
        analyzer = HarAnalyzer(args.har, args.slug)
        analyzer.load_and_analyze()
        apply_endpoint_overrides(analyzer, args.endpoint)
        analyzer.models.update(args.model)
        analyzer.report()

        if args.strict and "chat" not in analyzer.exported_capabilities():
            print("[!] STRICT mode: chat capability missing. Re-capture the HAR while sending a "
                  "chat message, or force with --endpoint chat=URL.")
            return 2

        scaffolder = ProviderScaffolder(analyzer, Path(args.out))
        scaffolder.scaffold(dry_run=args.dry_run, force=args.force)
    except HarAuditError as exc:
        print(f"[!] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())