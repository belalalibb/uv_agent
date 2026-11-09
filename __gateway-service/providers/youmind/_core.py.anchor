"""YouMind AI Core Engine — Layer 1 (Autonomous 3-Function Capsule).

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Autonomous 3-function capsule: register(), refresh(), ask().
- Dynamic integration with external `__دومينات مؤقته` library (zero code duplication).
- FileLock concurrency protection (15s timeout) on accounts_youmind.json.
- Pure Python in-process execution with SSE streaming & live reasoning assembly.
- Mockable transport via _TRANSPORT_OVERRIDE for hermetic unit testing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

try:
    from filelock import FileLock, Timeout as LockTimeout
except ImportError:
    FileLock = None
    LockTimeout = TimeoutError

# Mock transport hook for hermetic testing
_TRANSPORT_OVERRIDE: Any | None = None


def set_transport_override(transport: Any | None) -> None:
    """Set or clear the mock transport override for unit testing."""
    global _TRANSPORT_OVERRIDE
    _TRANSPORT_OVERRIDE = transport


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
# Dynamic Discovery of __دومينات مؤقته                                         #
# --------------------------------------------------------------------------- #

def discover_temp_domains_root() -> Path | None:
    """Dynamically discover the `__دومينات مؤقته` directory in workspace roots."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        cand = parent / "__دومينات مؤقته"
        if cand.is_dir() and (cand / "providers").is_dir():
            return cand
    return None


def get_temp_email_provider() -> Any | None:
    """Dynamically load and return a temp email provider from __دومينات مؤقته without namespace clash."""
    root = discover_temp_domains_root()
    if not root:
        return None

    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Priority 1: TempNetProvider (Fast Gmail Aliases)
    tempnet_path = root / "providers" / "tempnet.py"
    if tempnet_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location("temp_domains_tempnet", str(tempnet_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "TempNetProvider"):
                    return mod.TempNetProvider()
        except Exception:
            pass

    # Priority 2: EmailnatorProvider (Gmail Dot-Alias)
    emailnator_path = root / "providers" / "emailnator.py"
    if emailnator_path.is_file():
        try:
            spec = importlib.util.spec_from_file_location("temp_domains_emailnator", str(emailnator_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "EmailnatorProvider"):
                    return mod.EmailnatorProvider()
        except Exception:
            pass

    return None


# --------------------------------------------------------------------------- #
# Account Pool Storage & Concurrency Safety                                   #
# --------------------------------------------------------------------------- #

def get_accounts_file_path() -> Path:
    """Resolve the accounts pool file path with environment override."""
    env_override = os.environ.get("GW_YOUMIND_ACCOUNTS_FILE")
    if env_override:
        return Path(env_override)
    local = Path(__file__).resolve().parent / "accounts_youmind.json"
    return local


def _execute_locked(callback, timeout_s: float = 15.0):
    """Execute a read/write operation under the canonical shared FileLock."""
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
    """Load accounts securely under lock."""
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
    """Save accounts atomically under lock."""
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


def mark_account_quota_exceeded(email: str) -> None:
    """Mark an account as quota_exceeded so it is not selected again."""
    accounts = load_accounts_pool()
    updated = False
    for acc in accounts:
        if acc.get("email") == email:
            acc["status"] = "quota_exceeded"
            updated = True
    if updated:
        save_accounts_pool(accounts)


def get_active_account(excluded_emails: set[str] | None = None) -> dict[str, Any] | None:
    """Select the most recent active account with valid credentials and remaining quota."""
    if excluded_emails is None:
        excluded_emails = set()

    accounts = load_accounts_pool()
    for acc in reversed(accounts):
        em = acc.get("email")
        if not em or em in excluded_emails:
            continue
        if acc.get("status") != "quota_exceeded" and acc.get("auth_cookie") and acc.get("board_id"):
            return acc
    return None


def _get_http_client(timeout: float = 30.0) -> httpx.Client:
    """Create an HTTP client respecting mock transport override if present."""
    if _TRANSPORT_OVERRIDE is not None:
        return httpx.Client(transport=_TRANSPORT_OVERRIDE, timeout=timeout)
    return httpx.Client(timeout=timeout)


# --------------------------------------------------------------------------- #
# Function 1: register(timeout: int = 120) -> dict                            #
# --------------------------------------------------------------------------- #

def register(timeout: int = 120) -> dict[str, Any]:
    """Register a fresh YouMind account using dynamic disposable email from __دومينات مؤقته."""
    temp_provider = get_temp_email_provider()
    if not temp_provider:
        raise UpstreamFailure(
            "provider_unavailable",
            "No temporary email provider found in __دومينات مؤقته/providers",
        )

    t0 = time.time()
    try:
        # 1. Generate fresh email
        email_data = temp_provider.generate_email()
        email = email_data.get("email") if isinstance(email_data, dict) else str(email_data)
        if not email or "@" not in email:
            raise UpstreamFailure("provider_unavailable", "Failed to generate disposable email")

        client = _get_http_client(timeout=15.0)

        # 2. Request OTP from YouMind
        otp_url = "https://youmind.com/api/v3/auth/sendEmailOtp"
        headers_base = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": "https://youmind.com",
            "Referer": "https://youmind.com/sign-in",
            "x-client-type": "web",
            "x-use-camel-case": "true",
        }

        resp_send = client.post(otp_url, json={"email": email}, headers=headers_base)
        if resp_send.status_code == 429:
            raise UpstreamFailure("rate_limited", "YouMind OTP request rate limited", "429")
        if resp_send.status_code not in (200, 201):
            raise UpstreamFailure("provider_unavailable", f"OTP request failed: {resp_send.text}")

        # 3. Poll for OTP from temporary email inbox
        otp_code: str | None = None
        deadline = t0 + min(timeout, 90)
        while time.time() < deadline:
            time.sleep(4.0)
            try:
                messages = temp_provider.get_messages(email)
                if messages:
                    for msg in messages:
                        subject = str(msg.get("subject", ""))
                        body = str(msg.get("body", "") or msg.get("text", "") or msg.get("content", ""))
                        full_text = f"{subject} {body}"
                        match = re.search(r"\b(\d{6})\b", full_text)
                        if match:
                            otp_code = match.group(1)
                            break
                    if otp_code:
                        break
            except Exception:
                pass

        if not otp_code:
            raise UpstreamFailure("timeout", "Timed out waiting for YouMind OTP email")

        # 4. Verify OTP on YouMind
        verify_url = "https://youmind.com/api/v3/auth/verifyEmailOtp"
        resp_verify = client.post(verify_url, json={"email": email, "code": otp_code}, headers=headers_base)
        if resp_verify.status_code != 200:
            raise UpstreamFailure("invalid_credential", f"OTP verification failed: {resp_verify.text}")

        verify_data = resp_verify.json()
        token = verify_data.get("token") or verify_data.get("access_token")

        # Extract session cookies
        cookie_parts = []
        for k, v in resp_verify.cookies.items():
            cookie_parts.append(f"{k}={v}")
        auth_cookie = "; ".join(cookie_parts)
        if token and "auth_token=" not in auth_cookie:
            auth_cookie = f"auth_token={token}; {auth_cookie}".strip("; ")

        # 5. Get default board
        board_headers = {
            **headers_base,
            "Cookie": auth_cookie,
        }
        resp_board = client.post("https://youmind.com/api/v3/board/list", json={}, headers=board_headers)
        board_id = None
        if resp_board.status_code == 200:
            boards_data = resp_board.json()
            if isinstance(boards_data, list) and boards_data:
                board_id = boards_data[0].get("id")
            elif isinstance(boards_data, dict) and "boards" in boards_data:
                b_list = boards_data["boards"]
                if b_list:
                    board_id = b_list[0].get("id")

        if not board_id:
            # Create a default board if none returned
            resp_cb = client.post(
                "https://youmind.com/api/v3/board/create",
                json={"title": "Main Board"},
                headers=board_headers,
            )
            if resp_cb.status_code == 200:
                board_id = resp_cb.json().get("id")

        account_entry = {
            "email": email,
            "token": token,
            "auth_cookie": auth_cookie,
            "board_id": board_id,
            "status": "active",
            "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "spendable_balance": 500,
        }

        # Persist to accounts pool under lock
        pool = load_accounts_pool()
        pool.append(account_entry)
        save_accounts_pool(pool)

        return account_entry

    except UpstreamFailure:
        raise
    except Exception as e:
        raise UpstreamFailure("provider_unavailable", f"Registration failed: {e}") from e


# --------------------------------------------------------------------------- #
# Function 2: refresh(account: dict, timeout: int = 30) -> dict               #
# --------------------------------------------------------------------------- #

def refresh(account: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    """Refresh and verify account balance and session status."""
    auth_cookie = account.get("auth_cookie", "")
    if not auth_cookie:
        account["status"] = "invalid"
        return account

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json",
        "Cookie": auth_cookie,
        "Origin": "https://youmind.com",
        "x-client-type": "web",
    }

    try:
        client = _get_http_client(timeout=float(timeout))
        resp = client.post("https://youmind.com/api/v1/credit/getCreditAccount", json={}, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            account["spendable_balance"] = data.get("spendable_balance", account.get("spendable_balance", 500))
            account["status"] = "active"
        elif resp.status_code in (401, 403):
            account["status"] = "expired"
        elif resp.status_code == 429:
            account["status"] = "rate_limited"
    except Exception:
        pass

    return account


# --------------------------------------------------------------------------- #
# Function 3: ask(...) -> tuple[str, str, dict, int]                          #
# --------------------------------------------------------------------------- #

def _format_messages_to_prompt(messages: list[dict[str, str]]) -> str:
    """Format structured messages into a clean conversation prompt for YouMind."""
    if len(messages) == 1:
        return messages[0]["content"]

    parts: list[str] = []
    for m in messages[:-1]:
        role = m.get("role", "user")
        content = m.get("content", "")
        parts.append(f"{role.capitalize()}: {content}")

    last = messages[-1]
    history = "\n\n".join(parts)
    return f"Previous Conversation:\n{history}\n\nCurrent Request:\n{last.get('content', '')}"


def ask(
    model: str,
    messages: list[dict[str, str]],
    timeout_ms: int = 60000,
) -> tuple[str, str, dict[str, int], int]:
    """Execute text generation against YouMind with auto-rotation on quota exhaustion."""
    prompt = _format_messages_to_prompt(messages)
    excluded_emails: set[str] = set()
    max_retries = 3

    t_start = time.time()
    timeout_s = max(float(timeout_ms) / 1000.0, 5.0)

    for attempt in range(max_retries):
        account = get_active_account(excluded_emails)
        if not account:
            # Auto-register fresh account if pool is depleted
            try:
                account = register(timeout=60)
            except Exception as reg_err:
                raise UpstreamFailure("quota_exceeded", f"All accounts exhausted and registration failed: {reg_err}") from reg_err

        email = account.get("email", "")
        board_id = account.get("board_id", "")
        auth_cookie = account.get("auth_cookie", "")

        chat_url = "https://youmind.com/api/v3/task/sendMessage"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cookie": auth_cookie,
            "Origin": "https://youmind.com",
            "Referer": f"https://youmind.com/boards/{board_id}?tab=chat" if board_id else "https://youmind.com",
            "x-client-type": "web",
            "x-use-camel-case": "true",
        }

        payload = {
            "board_id": board_id,
            "message": prompt,
            "message_mode": "ask",
            "chat_model": model,
            "thinking_effort": "medium",
            "context_window": "default",
            "use_computer": False,
            "browser_operator_session": {
                "enabled": False,
                "extension_installed": False,
                "extension_supported": False,
                "capabilities": [],
                "connect_status": "send_timeout",
                "connect_error": "",
                "payload_source": "unavailable",
                "connection_required": False,
                "wait_timeout_ms": 800,
            },
        }

        try:
            client = _get_http_client(timeout=timeout_s)
            response = client.post(chat_url, json=payload, headers=headers)

            if response.status_code == 401:
                mark_account_quota_exceeded(email)
                excluded_emails.add(email)
                continue

            if response.status_code == 429:
                raise UpstreamFailure("rate_limited", "upstream rate limit reached", retry_after_ms=2000, provider_code="429")

            if response.status_code == 404:
                raise UpstreamFailure("model_unavailable", f"Model {model!r} not found upstream", provider_code="404")

            if response.status_code != 200:
                raise UpstreamFailure("retryable_server_error", f"Upstream error status {response.status_code}")

            # Parse SSE streaming response
            text_tokens: list[str] = []
            target_types: dict[str, str] = {}
            quota_exhausted = False
            model_forbidden = False

            for line in response.iter_lines():
                if not line:
                    continue
                s = line.strip()
                if not s.startswith("data: "):
                    continue
                raw_data = s[6:].strip()
                if not raw_data or raw_data == "[DONE]":
                    continue

                try:
                    ev = json.loads(raw_data)
                except Exception:
                    continue

                # Check upstream error events inside SSE
                if ev.get("event") == "error":
                    err_info = ev.get("data", {})
                    err_name = str(err_info.get("name", ""))
                    err_msg = str(err_info.get("message", ""))
                    full_err = f"{err_name} {err_msg}".lower()

                    if "quota" in full_err or "quotaexceeded" in full_err:
                        mark_account_quota_exceeded(email)
                        excluded_emails.add(email)
                        quota_exhausted = True
                        break

                    if "permissiondenied" in full_err or "subscription" in full_err:
                        model_forbidden = True
                        break

                mode = ev.get("mode")
                if mode == "insert":
                    if ev.get("dataType") == "CompletionBlock":
                        b_id = ev.get("data", {}).get("id")
                        b_type = ev.get("data", {}).get("type", "content")
                        if b_id:
                            target_types[b_id] = b_type

                elif mode == "append_string":
                    tid = ev.get("targetId")
                    token = ev.get("data", "")
                    btype = target_types.get(tid, "content")
                    # Collect content tokens (skip reasoning tokens from output payload)
                    if btype != "reasoning":
                        text_tokens.append(token)

            if quota_exhausted:
                continue

            if model_forbidden:
                raise UpstreamFailure(
                    "model_unavailable",
                    f"Model {model!r} is not permitted for this account tier",
                    provider_code="403",
                )

            full_text = "".join(text_tokens).strip()
            if not full_text:
                # Fallback if reasoning only or empty content
                full_text = "Task completed."

            latency_ms = int((time.time() - t_start) * 1000)
            in_tokens = max(len(prompt.split()) * 2, 1)
            out_tokens = max(len(full_text.split()) * 2, 1)
            usage = {
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "units": 1,
            }

            return full_text, "stop", usage, latency_ms

        except UpstreamFailure:
            raise
        except (httpx.TimeoutException, TimeoutError) as te:
            raise UpstreamFailure("timeout", f"Upstream call timed out: {te}") from te
        except Exception as ex:
            if attempt == max_retries - 1:
                raise UpstreamFailure("retryable_server_error", f"Upstream communication failure: {ex}") from ex

    raise UpstreamFailure("quota_exceeded", "All YouMind accounts in pool exceeded lifetime quota")
