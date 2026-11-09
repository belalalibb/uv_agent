# -*- coding: utf-8 -*-
"""
================================================================================
🏭 PARALLEL.AI — مصنع الحسابات الآلي المطور (Parallel Account Factory v1.1)
================================================================================
المطور: زيزو الهندسية (Zizo Engineering) بالتعاون مع الباشمهندس بولا
المميزات:
  - استدعاء تلقائي لمزودي الجيميل المؤقتين من (__دومينات مؤقته) مع اشتراط @gmail.com.
  - محاكاة متطابقة 100% مع الـ HAR (Browser Parity) لكوكيز Vercel و PostHog.
  - إرسال طلب الإنشاء والتسجيل النقي (Pure Server Action) بدون كابتشا.
  - مراقبة صندوق الوارد واستقبال رابط السحر (Magic Link) لحظياً وفك تشفيره.
  - تنفيذ Redirect Server Action (4079bceeefa2e5c9100c4d32fcf388c8890c30b8d0).
  - تفعيل جلسة NextAuth واستخراج الكوكيز والمفاتيح الرسمية.
  - إنشاء المنظمة واستخراج الـ API Key وفحص الرصيد الترحيبي.
  - حفظ الحسابات الجاهزة في accounts_parallel.json بصيغة قياسية.
================================================================================
"""

import os
import sys
import time
import json
import re
import uuid
import base64
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional, Tuple
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Dynamic TempMail Import ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BASE_DIR.parent.parent.parent
TEMPMAIL_DIR = WORKSPACE_ROOT / "__دومينات مؤقته"

if TEMPMAIL_DIR.exists() and str(TEMPMAIL_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPMAIL_DIR))

try:
    from tempmail import get_provider, TempMail
    TEMPMAIL_LOADED = True
except Exception:
    TEMPMAIL_LOADED = False

ACCOUNTS_FILE = BASE_DIR / "accounts_parallel.json"

BANNER = """\033[96m
╔══════════════════════════════════════════════════════════════════════════╗
║     🏭 PARALLEL.AI — AUTOMATED ACCOUNT FACTORY v1.1                     ║
╚══════════════════════════════════════════════════════════════════════════╝\033[0m"""


class ParallelAccountFactory:
    """Automated Account Provisioner for Parallel AI."""

    PLATFORM_BASE = "https://platform.parallel.ai"
    SIGNUP_ACTION_ID = "40ef9673ffe2b52ab83640c68ee5311d93ae81cc30"
    REDIRECT_ACTION_ID = "4079bceeefa2e5c9100c4d32fcf388c8890c30b8d0"

    def __init__(self, provider_name: str = "tempmailclub"):
        self.provider_name = provider_name
        self.session = requests.Session()
        
        # PostHog device ID and tracking matching HAR
        device_id = str(uuid.uuid4())
        ph_cookie_val = json.dumps({
            "$device_id": device_id,
            "distinct_id": device_id,
            "$initial_person_info": {"r": "$direct", "u": "https://parallel.ai/"}
        })
        self.session.cookies.set("pp_region", "unregulated", domain=".parallel.ai")
        self.session.cookies.set("ph_phc_kjbs4YpgGG9pkQoYka6LnO0fNHfDP0Y20JiiG7eZsaD_posthog", ph_cookie_val, domain="platform.parallel.ai")

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
            "Origin": self.PLATFORM_BASE,
            "Referer": f"{self.PLATFORM_BASE}/signup?redirectTo=%2F",
            "sec-ch-ua": '"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin"
        }
        self.tempmail_prov = None
        if TEMPMAIL_LOADED:
            try:
                self.tempmail_prov = get_provider(self.provider_name)
            except Exception:
                pass
        if not self.tempmail_prov and self.provider_name == "tempmailclub":
            club_file = TEMPMAIL_DIR / "providers" / "tempmail_club.py"
            if club_file.exists():
                import importlib.util
                if str(TEMPMAIL_DIR) not in sys.path:
                    sys.path.insert(0, str(TEMPMAIL_DIR))
                spec = importlib.util.spec_from_file_location("tempmail_club_direct", club_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    self.tempmail_prov = mod.TempMailClubProvider()

    def _get_fresh_email(self) -> Any:
        """Find a clean email address from the requested provider."""
        if not self.tempmail_prov:
            raise RuntimeError("TempMail module is not available in workspace.")

        prov = self.tempmail_prov
        print(f"\033[93m[+] Requesting fresh email address from '{self.provider_name}'...\033[0m")
        
        is_gmail_provider = self.provider_name in ("emailnator", "tempnet")
        kwargs = {}
        if is_gmail_provider:
            kwargs = {"domain": "gmail.com"}
        elif self.provider_name == "tempmailclub":
            kwargs = {"domain": "rc.mailings.live"}

        for attempt in range(8):
            try:
                acc = prov.create_email(**kwargs)
                if not is_gmail_provider or acc.address.lower().endswith("@gmail.com"):
                    msgs = prov.get_messages(acc)
                    if len(msgs) == 0:
                        print(f"\033[92m[✓] Provisioned clean email: {acc.address}\033[0m")
                        return acc
            except Exception:
                pass
            time.sleep(1)

        # Fallback to general TempMail create or direct provider create
        if TEMPMAIL_LOADED:
            try:
                acc = TempMail.create(provider=self.provider_name, **kwargs)
                print(f"\033[92m[✓] Provisioned email: {acc.address}\033[0m")
                return acc
            except Exception:
                pass
        acc = self.tempmail_prov.create_email(**kwargs)
        print(f"\033[92m[✓] Provisioned email: {acc.address}\033[0m")
        return acc

    def submit_signup(self, email_address: str) -> bool:
        """Submit email to Parallel AI signup Server Action."""
        url = f"{self.PLATFORM_BASE}/signup?redirectTo=%2F"
        req_headers = {
            **self.headers,
            "accept": "text/x-component",
            "next-action": self.SIGNUP_ACTION_ID,
            "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22signup%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C4112%5D"
        }
        files = {
            "_1_email": (None, email_address),
            "_1_redirectUrl": (None, "/post-auth-sign-up?redirectTo=%2F"),
            "0": (None, '["$K1"]')
        }
        print(f"\033[94m[+] Submitting signup action for: {email_address}...\033[0m")
        res = self.session.post(url, headers=req_headers, files=files, timeout=20)
        if res.status_code == 200:
            print("\033[92m[✓] Signup action accepted. Magic link dispatched.\033[0m")
            return True
        else:
            print(f"\033[91m[-] Signup action rejected: {res.status_code} - {res.text[:200]}\033[0m")
            return False

    def wait_for_magic_link(self, email_obj: Any, timeout: int = 90) -> Tuple[str, str]:
        """Poll inbox for Parallel AI magic link and return (raw_to, decoded_cb)."""
        print(f"\033[93m[+] Polling inbox for magic link (timeout: {timeout}s)...\033[0m")
        prov = self.tempmail_prov or get_provider(self.provider_name)
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                msgs = prov.get_messages(email_obj)
                for m in msgs:
                    if "parallel" in m.subject.lower() or "parallel" in str(m.sender).lower():
                        html = m.body_html or m.body_text or ""
                        # Find redirect link
                        match = re.search(r'https://platform\.parallel\.ai/redirect\?to=([^\s"\'<>]+)', html)
                        if match:
                            raw_to = match.group(1)
                            # URL-safe base64 decode (reversed)
                            padding = '=' * (-len(raw_to) % 4)
                            decoded_raw = base64.urlsafe_b64decode(raw_to + padding).decode("utf-8", errors="ignore")[::-1]
                            cb_match = re.search(r'https?://platform\.parallel\.ai/[^\s"\'<>]+', decoded_raw)
                            decoded_cb = cb_match.group(0) if cb_match else decoded_raw
                            print(f"\033[92m[✓] Magic link received and decoded successfully!\033[0m")
                            return raw_to, decoded_cb
            except Exception:
                pass
            time.sleep(4)

        raise TimeoutError("Timed out waiting for Parallel AI magic link email.")

    def authenticate_and_claim(self, raw_to: str, callback_url: str, org_name: str = "Parallel Labs") -> Dict[str, Any]:
        """Authenticate session, create organization, and claim initial credits & API Key."""
        # 1. Trigger redirect Server Action (HAR Entry 66)
        redirect_url = f"{self.PLATFORM_BASE}/redirect?to={raw_to}"
        redirect_headers = {
            **self.headers,
            "accept": "text/x-component",
            "content-type": "text/plain;charset=UTF-8",
            "next-action": self.REDIRECT_ACTION_ID,
            "next-router-state-tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22redirect%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C4096%5D%7D%2Cnull%2Cnull%2C4112%5D",
            "Referer": redirect_url
        }
        print("\033[94m[+] Executing redirect Server Action...\033[0m")
        try:
            self.session.post(redirect_url, headers=redirect_headers, data='[{"andRedirect":false}]', timeout=15)
        except Exception as e:
            print(f"[-] Redirect action warning: {e}")

        # 2. Authenticate with magic link RPC (HAR Entry 67)
        auth_headers = {
            **self.headers,
            "Content-Type": "application/json",
            "Referer": redirect_url
        }
        print("\033[94m[+] Authenticating with magic link RPC...\033[0m")
        auth_res = self.session.post(
            f"{self.PLATFORM_BASE}/api/rpc/redirect/authenticate-with-magic-link",
            json={"redirectUrl": callback_url},
            headers=auth_headers,
            timeout=15
        )
        auth_res.raise_for_status()

        # 3. Follow NextAuth callback to establish session cookies
        print("\033[94m[+] Following NextAuth callback to establish session cookies...\033[0m")
        cb_res = self.session.get(callback_url, allow_redirects=True, headers=auth_headers, timeout=15)
        cb_res.raise_for_status()

        # 4. Verify session
        sess_res = self.session.get(f"{self.PLATFORM_BASE}/api/auth/session", headers=auth_headers, timeout=15)
        sess_data = sess_res.json()
        user_email = sess_data.get("user", {}).get("email")
        print(f"\033[92m[✓] Session Active: {user_email}\033[0m")

        # 5. Simulate onboard page transition (HAR Entry 80)
        try:
            self.session.get(f"{self.PLATFORM_BASE}/onboard?step=create", headers={**self.headers, "accept": "text/x-component"}, timeout=10)
        except Exception:
            pass

        # 6. Create Org (HAR Entry 84)
        print(f"\033[94m[+] Creating organization: '{org_name}'...\033[0m")
        org_res = self.session.post(
            f"{self.PLATFORM_BASE}/api/rpc/onboard/create-org-with-visibility",
            json={"orgName": org_name, "domainVisibility": "not_set", "onboardSource": "platform"},
            headers=auth_headers,
            timeout=15
        )
        org_res.raise_for_status()
        org_id = org_res.json().get("data", {}).get("data", {}).get("org_id")
        print(f"\033[92m[✓] Organization Created: {org_id}\033[0m")

        self.session.cookies.set("soid", org_id, domain="platform.parallel.ai")

        # 7. Set selected org and preload
        self.session.post(f"{self.PLATFORM_BASE}/api/rpc/onboard/set-selected-org",
                          json={"orgId": org_id}, headers=auth_headers, timeout=10)
        
        try:
            self.session.get(f"{self.PLATFORM_BASE}/onboard?step=invite&orgId={org_id}", headers={**self.headers, "accept": "text/x-component"}, timeout=10)
        except Exception:
            pass

        self.session.post(f"{self.PLATFORM_BASE}/api/rpc/onboard/preload-org-data-for-home",
                          json={"orgId": org_id}, headers=auth_headers, timeout=10)

        # 8. Check balance
        bal_res = self.session.post(f"{self.PLATFORM_BASE}/api/rpc/onboard/get-org-credit-balance",
                                    json={"orgId": org_id}, headers=auth_headers, timeout=10)
        balance_cents = bal_res.json().get("data", {}).get("balanceCents", 0)
        print(f"\033[92m[✓] Credit Balance: ${balance_cents / 100.0:.2f} ({balance_cents} cents)\033[0m")

        # 9. Complete rewards step & ensure org
        try:
            self.session.get(f"{self.PLATFORM_BASE}/onboard?step=rewards&orgId={org_id}", headers={**self.headers, "accept": "text/x-component"}, timeout=10)
            self.session.post(f"{self.PLATFORM_BASE}/api/rpc/auth/ensure-selected-org", json={"selectedOrgId": org_id}, headers=auth_headers, timeout=10)
        except Exception:
            pass

        # 10. Check detailed balance items
        try:
            items_res = self.session.post(f"{self.PLATFORM_BASE}/api/rpc/billing/payments/get-balance-items", json={}, headers=auth_headers, timeout=10)
            items_data = items_res.json().get("data", {}).get("balanceItems", [])
            if items_data:
                print(f"\033[92m[✓] Balance Items: {json.dumps(items_data, ensure_ascii=False)}\033[0m")
        except Exception:
            pass

        # 11. Retrieve API Key
        key_res = self.session.post(f"{self.PLATFORM_BASE}/api/rpc/auth/get-my-api-key-and-session-details",
                                    json={"skipCookieSet": False, "retryCount": 0}, headers=auth_headers, timeout=10)
        key_data = key_res.json().get("data", {})
        api_key = key_data.get("apiKey")
        print(f"\033[92m[✓] API Key Secured: {api_key[:10]}...{api_key[-4:]}\033[0m")

        cookies_dict = self.session.cookies.get_dict()

        account_record = {
            "email": user_email,
            "api_key": api_key,
            "org_id": org_id,
            "org_name": org_name,
            "balance_cents": balance_cents,
            "balance_usd": balance_cents / 100.0,
            "cookies": cookies_dict,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        self._save_account(account_record)
        return account_record

    def _save_account(self, account: Dict[str, Any]):
        """Persist created account to accounts_parallel.json."""
        existing = []
        if ACCOUNTS_FILE.exists():
            try:
                with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing.append(account)
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        print(f"\033[92m[✓] Account saved to: {ACCOUNTS_FILE.name} (Total Accounts: {len(existing)})\033[0m")

    def create_account(self) -> Dict[str, Any]:
        """One-click pure autonomous registration pipeline."""
        print(BANNER)
        email_obj = self._get_fresh_email()
        if not self.submit_signup(email_obj.address):
            raise RuntimeError("Signup submission failed.")
        raw_to, callback_url = self.wait_for_magic_link(email_obj)
        account = self.authenticate_and_claim(raw_to, callback_url)
        print(f"""\033[92m
╔══════════════════════════════════════════════════════════════════════════╗
║  🎉 ACCOUNT CREATED SUCCESSFULLY!                                       ║
║  Email:   {account['email']}
║  API Key: {account['api_key']}
║  Balance: ${account['balance_usd']:.2f}
╚══════════════════════════════════════════════════════════════════════════╝\033[0m""")
        return account


if __name__ == "__main__":
    factory = ParallelAccountFactory(provider_name="tempmailclub")
    factory.create_account()
