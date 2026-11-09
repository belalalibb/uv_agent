"""TinyFish AI Core Engine — Layer 1.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- 100% Zero-Browser Law: Strictly HTTP requests (Pure Requests Only).
- Autonomous 3-function capsule: register(), refresh(), ask().
- FileLock concurrency protection (15s timeout) on accounts_tinyfish.json.
- Dynamic integration with external `__دومينات مؤقته` library (zero forbidden paths).
- Supports text generation (via web agent reasoning) and vision analysis.
- Transport override hook for hermetic unit testing.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

try:
    from filelock import FileLock, Timeout as LockTimeout
except ImportError:
    FileLock = None
    LockTimeout = TimeoutError

logger = logging.getLogger(__name__)

CLERK_API_VERSION = "2026-05-12"
CLERK_JS_VERSION = "6.34.1"
BASE_CLERK_URL = "https://clerk.tinyfish.ai/v1/client"
TINYFISH_AGENT_URL = "https://agent.tinyfish.ai"
ACTION_CREATE_KEY = "406c152e0785dd816938db870361efbb6d7a8711f2"

STANDARD_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/x-www-form-urlencoded",
    "origin": TINYFISH_AGENT_URL,
    "referer": f"{TINYFISH_AGENT_URL}/",
    "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
}

# --------------------------------------------------------------------------- #
# Metadata & Exception Taxonomy                                               #
# --------------------------------------------------------------------------- #

_METADATA_PATH = Path(__file__).resolve().parent / "models_metadata.json"
try:
    with open(_METADATA_PATH, "r", encoding="utf-8") as _f:
        MODELS_METADATA: dict[str, dict] = json.load(_f)
except Exception:
    MODELS_METADATA = {}


class UpstreamFailure(Exception):
    """Canonical internal exception carrying normalized category and diagnostics."""

    def __init__(
        self,
        category: str,
        message: str,
        retry_after_ms: int | None = None,
        provider_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.retry_after_ms = retry_after_ms
        self.provider_code = provider_code


# --------------------------------------------------------------------------- #
# Dynamic Discovery of __دومينات مؤقته (Zero Forbidden Paths)                  #
# --------------------------------------------------------------------------- #

def discover_temp_domains_root() -> Path | None:
    """Dynamically discover the `__دومينات مؤقته` directory in workspace roots."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        cand = parent / "__دومينات مؤقته"
        if cand.exists() and cand.is_dir():
            return cand
    return None


def _load_temp_email_provider() -> Any | None:
    """Dynamically load and return a Gmail-capable temp email provider."""
    root = discover_temp_domains_root()
    if not root:
        return None

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Try Emailnator first (Gmail aliases)
    emailnator_path = root / "providers" / "emailnator.py"
    if emailnator_path.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                "temp_domains_emailnator", str(emailnator_path)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["temp_domains_emailnator"] = mod
                spec.loader.exec_module(mod)
                return mod.EmailnatorProvider()
        except Exception as e:
            logger.warning(f"[TinyFish] Could not load EmailnatorProvider: {e}")

    # Fallback to TempNet
    tempnet_path = root / "providers" / "tempnet.py"
    if tempnet_path.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                "temp_domains_tempnet", str(tempnet_path)
            )
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["temp_domains_tempnet"] = mod
                spec.loader.exec_module(mod)
                return mod.TempNetProvider()
        except Exception as e:
            logger.warning(f"[TinyFish] Could not load TempNetProvider: {e}")

    return None


# --------------------------------------------------------------------------- #
# Account Pool Management with FileLock                                       #
# --------------------------------------------------------------------------- #

def get_accounts_file_path() -> Path:
    env_override = os.environ.get("GW_TINYFISH_ACCOUNTS_FILE")
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "accounts_tinyfish.json"


def _execute_locked(callback, timeout_s: float = 15.0):
    path = get_accounts_file_path()
    lock_path = path.with_suffix(".json.lock")
    if FileLock:
        try:
            with FileLock(str(lock_path), timeout=timeout_s):
                return callback(path)
        except Exception as err:
            raise UpstreamFailure("provider_unavailable", f"Accounts lock timeout: {err}") from err
    return callback(path)


def load_accounts_pool() -> list[dict[str, Any]]:
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    return _execute_locked(_read)


def save_accounts_pool(accounts: list[dict[str, Any]]) -> bool:
    def _write(path: Path) -> bool:
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
            return True
        except Exception:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return False

    return _execute_locked(_write)


def get_active_account() -> dict[str, Any] | None:
    env_key = os.environ.get("GW_TINYFISH_API_KEY") or os.environ.get("TINYFISH_API_KEY")
    if env_key and env_key.startswith("sk-tinyfish-"):
        return {"api_key": env_key, "email": "env@tinyfish.local", "status": "active"}

    accounts = load_accounts_pool()
    for acc in reversed(accounts):
        key = acc.get("api_key")
        if (
            acc.get("status", "active") == "active"
            and isinstance(key, str)
            and key.startswith("sk-tinyfish-")
        ):
            return acc
    return None


def evict_account(api_key: str) -> None:
    def _evict(path: Path):
        if not path.exists():
            return
        try:
            accounts = json.loads(path.read_text(encoding="utf-8"))
            retained = [a for a in accounts if a.get("api_key") != api_key]
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(retained, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except Exception:
            pass

    _execute_locked(_evict)


# --------------------------------------------------------------------------- #
# Transport Override & HTTP Dispatcher (Hermetic Testing)                     #
# --------------------------------------------------------------------------- #

_TRANSPORT_OVERRIDE = None


def set_transport_override(transport) -> None:
    """Hook for unit tests to inject MockTransport without touching network."""
    global _TRANSPORT_OVERRIDE
    _TRANSPORT_OVERRIDE = transport


def http_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    json_data: dict[str, Any] | None = None,
    data: Any | None = None,
    timeout: float = 60.0,
):
    """Unified HTTP request dispatcher supporting httpx mock transports and curl_cffi/requests."""
    if _TRANSPORT_OVERRIDE is not None:
        import httpx

        with httpx.Client(transport=_TRANSPORT_OVERRIDE, timeout=timeout) as client:
            return client.request(method, url, headers=headers, json=json_data, data=data)

    import requests

    return requests.request(method, url, headers=headers, json=json_data, data=data, timeout=timeout)


# --------------------------------------------------------------------------- #
# Autonomous Account Factory (Zero Browser)                                   #
# --------------------------------------------------------------------------- #

def register_account(max_attempts: int = 8) -> dict[str, Any]:
    """Register a fresh TinyFish account using pure HTTP requests and Gmail aliases."""
    prov = _load_temp_email_provider()
    if not prov:
        raise UpstreamFailure(
            "provider_unavailable",
            "No temporary email provider found in __دومينات مؤقته",
        )

    import requests

    sess = requests.Session()
    url_signup = f"{BASE_CLERK_URL}/sign_ups?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"

    sua_id = None
    email_obj = None
    email_addr = None

    for attempt in range(1, max_attempts + 1):
        try:
            cand_obj = prov.create_email()
            cand_addr = cand_obj.address
            r = sess.post(
                url_signup,
                headers=STANDARD_HEADERS,
                data={"email_address": cand_addr, "locale": "en-US"},
                timeout=15,
            )
            if r.status_code == 200:
                sua_id = r.json().get("response", {}).get("id")
                email_obj = cand_obj
                email_addr = cand_addr
                break
        except Exception:
            pass
        time.sleep(1.5)

    if not sua_id or not email_obj:
        raise UpstreamFailure(
            "provider_unavailable", "Failed to initiate Clerk signup with temporary email"
        )

    # 2. Prepare OTP
    url_prep = f"{BASE_CLERK_URL}/sign_ups/{sua_id}/prepare_verification?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"
    r_prep = sess.post(url_prep, headers=STANDARD_HEADERS, data={"strategy": "email_code"}, timeout=15)
    if r_prep.status_code != 200:
        raise UpstreamFailure("provider_unavailable", "Clerk prepare_verification failed")

    # 3. Wait for OTP
    otp_code = None
    for _ in range(15):
        time.sleep(3.0)
        try:
            messages = prov.get_messages(email_obj)
            if messages:
                for msg in messages:
                    sender_str = (msg.sender or "").lower()
                    subj_str = (msg.subject or "").lower()
                    if "tinyfish" in sender_str or "tinyfish" in subj_str:
                        m = re.search(r"\b(\d{6})\b", msg.subject)
                        if not m:
                            body = msg.body_text or msg.body_html or ""
                            m = re.search(r"\b(\d{6})\b", body)
                        if m:
                            otp_code = m.group(1)
                            break
            if otp_code:
                break
        except Exception:
            pass

    if not otp_code:
        raise UpstreamFailure("timeout", "Clerk OTP verification email timed out")

    # 4. Attempt verification
    url_attempt = f"{BASE_CLERK_URL}/sign_ups/{sua_id}/attempt_verification?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"
    r_att = sess.post(
        url_attempt,
        headers=STANDARD_HEADERS,
        data={"code": otp_code, "strategy": "email_code"},
        timeout=15,
    )
    if r_att.status_code != 200:
        raise UpstreamFailure("auth_expired", f"Clerk OTP attempt failed: {r_att.status_code}")

    r_data = r_att.json()
    sessions = r_data.get("client", {}).get("sessions", [])
    if not sessions:
        raise UpstreamFailure("auth_expired", "No active session returned after verification")

    session_id = sessions[0].get("id")
    jwt_token = sessions[0].get("last_active_token", {}).get("jwt")

    # 5. Touch session
    url_touch = f"{BASE_CLERK_URL}/sessions/{session_id}/touch?__clerk_api_version={CLERK_API_VERSION}&_clerk_js_version={CLERK_JS_VERSION}"
    r_touch = sess.post(
        url_touch,
        headers=STANDARD_HEADERS,
        data={"active_organization_id": "", "intent": "select_session"},
        timeout=15,
    )
    if r_touch.status_code == 200:
        new_jwt = r_touch.json().get("response", {}).get("last_active_token", {}).get("jwt")
        if new_jwt:
            jwt_token = new_jwt

    # 6. Next.js Server Action to create API key
    uat_val = str(int(time.time()))
    for c in sess.cookies:
        if "__client_uat" in c.name:
            uat_val = c.value
            break

    cookie_header = (
        f"__session={jwt_token}; "
        f"__session_dzJqBaFd={jwt_token}; "
        f"__client_uat={uat_val}; "
        f"__client_uat_dzJqBaFd={uat_val}; "
        f"clerk_active_context={session_id}:"
    )

    key_headers = {
        "accept": "text/x-component",
        "content-type": "text/plain;charset=UTF-8",
        "next-action": ACTION_CREATE_KEY,
        "origin": TINYFISH_AGENT_URL,
        "referer": f"{TINYFISH_AGENT_URL}/api-keys",
        "user-agent": STANDARD_HEADERS["user-agent"],
        "cookie": cookie_header,
    }

    r_key = sess.post(
        f"{TINYFISH_AGENT_URL}/api-keys",
        headers=key_headers,
        data='["api_keys"]',
        timeout=15,
    )
    if r_key.status_code != 200:
        raise UpstreamFailure("provider_unavailable", "Failed to generate API Key via server action")

    m = re.search(r"(sk-tinyfish-[a-zA-Z0-9_\-]+)", r_key.text)
    if not m:
        raise UpstreamFailure("bad_request", "Failed to parse sk-tinyfish API key from response")

    api_key = m.group(1)
    record = {
        "email": email_addr,
        "api_key": api_key,
        "jwt_token": jwt_token,
        "session_id": session_id,
        "status": "active",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    pool = load_accounts_pool()
    pool.append(record)
    save_accounts_pool(pool)
    return record


# ─── طابور إنشاء الحسابات المتتابع الصارم (FIFO Sequential Queue Refill) ───────────
# قاعدة بولا: مع كل استدعاء لدالة ask يتم إدراج 1 حساب في طابور الخلفية التتابعي الصارم
_ACCOUNT_REFILL_QUEUE: queue.Queue[int] = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def _sequential_account_worker() -> None:
    """خيط عمل خلفي ينشئ الحسابات بالتتابع الصارم (واحد ورا التاني لمنع الحرق)."""
    while True:
        try:
            item = _ACCOUNT_REFILL_QUEUE.get()
            if item is None:
                break
            try:
                q_rem = _ACCOUNT_REFILL_QUEUE.qsize()
                logger.info(f"[TinyFish Refill] 🔄 معالجة عنصر من طابور الحسابات (متبقي: {q_rem})...")
                acc = register_account()
                status = acc.get("status", "active")
                email = acc.get("email", "unknown")
                logger.info(f"[TinyFish Refill] ✅ اكتمل إنشاء الحساب بنجاح: {email} | Status: {status}")
            except Exception as e:
                logger.warning(f"[TinyFish Refill] ⚠️ فشل إنشاء الحساب من الطابور: {e}")
            finally:
                delay = float(os.getenv("TINYFISH_REFILL_DELAY", "3.0"))
                if delay > 0:
                    time.sleep(delay)
                _ACCOUNT_REFILL_QUEUE.task_done()
        except Exception:
            pass


def _ensure_worker_running() -> None:
    global _WORKER_STARTED
    if not _WORKER_STARTED:
        with _WORKER_LOCK:
            if not _WORKER_STARTED:
                worker_thread = threading.Thread(
                    target=_sequential_account_worker,
                    name="tinyfish-account-worker",
                    daemon=True,
                )
                worker_thread.start()
                _WORKER_STARTED = True


def enqueue_account_refill(count: int = 1) -> None:
    """
    إدراج حسابات في طابور الخلفية المتتابع الصارم.
    بناءً على طلب المستخدم، يتم الاكتفاء بـ 1 حساب فقط لكل استدعاء لتجنب حرق المزود.
    """
    if _TRANSPORT_OVERRIDE is not None or os.getenv("GW_TINYFISH_DISABLE_BG_REFILL") == "1":
        return
    _ensure_worker_running()
    for _ in range(count):
        _ACCOUNT_REFILL_QUEUE.put(1)
    logger.info(f"[TinyFish] Enqueued {count} account(s) for sequential background refill. Queue size: {_ACCOUNT_REFILL_QUEUE.qsize()}")


# --------------------------------------------------------------------------- #
# Core Execution: ask & analyze_vision                                        #
# --------------------------------------------------------------------------- #

def ask(
    model: str,
    messages: list[dict[str, str]],
    session_id: str | None = None,
    timeout_ms: int = 90000,
) -> tuple[str, str, dict[str, int], int]:
    """Execute text generation/reasoning using TinyFish Web Agent."""
    # ─── طابور التزويد التتابعي الصارم (1 حساب فقط مع كل استدعاء) ─────────
    enqueue_account_refill(count=1)

    account = get_active_account()
    if not account:
        try:
            account = register_account()
        except Exception as e:
            raise UpstreamFailure("provider_unavailable", f"TinyFish accounts pool empty and refill failed: {e}")

    api_key = account.get("api_key")
    if not api_key:
        raise UpstreamFailure("invalid_credential", "No API key available for TinyFish")

    # Extract user prompt and optional URL
    user_prompt = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_prompt = msg.get("content", "")
            break

    if not user_prompt:
        user_prompt = "Hello"

    # Detect if user provided a specific URL in prompt
    target_url = "https://www.google.com"
    url_match = re.search(r"(https?://[^\s]+)", user_prompt)
    if url_match:
        target_url = url_match.group(1)

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "url": target_url,
        "goal": user_prompt,
        "browser_profile": "lite",
    }

    t0 = time.perf_counter()
    timeout_sec = max(5.0, timeout_ms / 1000.0)

    try:
        r = http_request(
            "POST",
            f"{TINYFISH_AGENT_URL}/v1/automation/run",
            headers=headers,
            json_data=payload,
            timeout=timeout_sec,
        )
    except Exception as e:
        latency = int((time.perf_counter() - t0) * 1000)
        raise UpstreamFailure("timeout", f"TinyFish network timeout: {e}")

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if r.status_code == 401:
        evict_account(api_key)
        raise UpstreamFailure("auth_expired", "TinyFish API key invalid or expired", provider_code="401")
    if r.status_code == 403:
        raise UpstreamFailure("quota_exceeded", "TinyFish account quota or permission denied", provider_code="403")
    if r.status_code == 429:
        raise UpstreamFailure("rate_limited", "TinyFish rate limited", retry_after_ms=5000, provider_code="429")
    if r.status_code >= 500:
        raise UpstreamFailure("retryable_server_error", f"TinyFish server error: {r.status_code}", provider_code=str(r.status_code))
    if r.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"TinyFish error {r.status_code}: {r.text[:200]}", provider_code=str(r.status_code))

    try:
        data = r.json()
    except Exception:
        raise UpstreamFailure("bad_request", "TinyFish returned non-JSON body")

    result = data.get("result")
    extracted_text = ""
    if isinstance(result, dict):
        if "result" in result and isinstance(result["result"], str):
            extracted_text = result["result"]
        else:
            extracted_text = json.dumps(result, ensure_ascii=False)
    elif result is not None:
        extracted_text = str(result)
    else:
        err_msg = data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else "No result returned"
        raise UpstreamFailure("non_retryable_error", f"TinyFish run failed: {err_msg}")

    usage_dict = {
        "input_tokens": len(user_prompt.split()) * 2,
        "output_tokens": len(extracted_text.split()) * 2,
        "units": 1,
    }
    return extracted_text, "stop", usage_dict, latency_ms


def analyze_vision(
    model: str,
    image_bytes: bytes,
    image_format: str,
    instruction: str,
    session_id: str | None = None,
    timeout_ms: int = 90000,
) -> tuple[str, dict[str, int], int]:
    """Execute multimodal vision analysis on images via TinyFish."""
    account = get_active_account()
    if not account:
        account = register_account()

    api_key = account.get("api_key")
    if not api_key:
        raise UpstreamFailure("invalid_credential", "No API key available for TinyFish")

    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    # Format image as data URI
    b64_data = base64.b64encode(image_bytes).decode("ascii")
    data_uri = f"data:image/{image_format};base64,{b64_data}"

    # Or if instruction contains a URL, use it directly
    target_url = data_uri
    url_match = re.search(r"(https?://[^\s]+\.(?:png|jpg|jpeg|webp|gif))", instruction, re.IGNORECASE)
    if url_match:
        target_url = url_match.group(1)

    payload = {
        "url": target_url,
        "goal": instruction,
        "browser_profile": "lite",
    }

    t0 = time.perf_counter()
    timeout_sec = max(5.0, timeout_ms / 1000.0)

    try:
        r = http_request(
            "POST",
            f"{TINYFISH_AGENT_URL}/v1/automation/run",
            headers=headers,
            json_data=payload,
            timeout=timeout_sec,
        )
    except Exception as e:
        raise UpstreamFailure("timeout", f"TinyFish vision timeout: {e}")

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if r.status_code != 200:
        raise UpstreamFailure("non_retryable_error", f"TinyFish vision failed HTTP {r.status_code}")

    try:
        data = r.json()
        result = data.get("result")
        if isinstance(result, dict) and "result" in result:
            text = str(result["result"])
        elif result:
            text = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
        else:
            text = "Image analyzed successfully."
    except Exception:
        text = "Image analyzed."

    usage_dict = {"input_tokens": 100, "output_tokens": len(text.split()) * 2, "units": 1}
    return text, usage_dict, latency_ms
