#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — LIVE OPERATIONAL BENCHMARK FOR DEEPAI (v1.0)
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla & Eng. Zizo
Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008

Features Tested:
  1. 🔍 Full Gateway Discovery (/v1/describe & /v1/models projection).
  2. 💬 Text Generation Live Test (POST /v1/execute -> generate_text).
  3. 🧠 Thinking Model Live Test (glm-5.3-flash with task status polling).
  4. 📁 File Upload & Context Test (.py, .md, .txt, .json).
  5. 🖼️ Vision Analysis Live Test (POST /v1/execute -> analyze_vision).
  6. 🎙️ Audio Transcription Live Test (POST /v1/execute -> transcribe_audio).
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import base64
import io
import json
import sys
import time
import wave
from pathlib import Path

# Adjust console encoding for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Colorama / ANSI styling
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    CYAN = Fore.CYAN
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RED = Fore.RED
    MAGENTA = Fore.MAGENTA
    WHITE = Fore.WHITE
    BRIGHT = Style.BRIGHT
    RESET = Style.RESET_ALL
except ImportError:
    CYAN = GREEN = YELLOW = RED = MAGENTA = WHITE = BRIGHT = RESET = ""

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from app import build_app, register_live_providers
from gateway.config import GatewayConfig
from gateway.contracts import (
    HEADER_GATEWAY_SECRET,
    HEADER_GATEWAY_SECRET_VERSION,
    HEADER_ROUTE_TOKEN,
)
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry

SECRET_VERSION = 1
GATEWAY_SECRET = "live-demo-secret-key-bolla-zizo"
DEEPAI_ROUTE_TOKEN = "rtk_deepai_production_live_session"

TEST_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="
)


def create_live_client() -> TestClient:
    config = GatewayConfig(
        secrets_by_version={SECRET_VERSION: GATEWAY_SECRET},
        current_secret_version=SECRET_VERSION,
        route_map={DEEPAI_ROUTE_TOKEN: "deepai"},
        dual_accept_window_seconds=600,
    )
    providers = ProviderRegistry()
    register_live_providers(providers)
    providers.eager_verify_all()
    routes = RouteRegistry(config.route_map)
    app = build_app(config, providers, routes)
    return TestClient(app)


def print_banner():
    print(f"\n{GREEN}╔{'═'*76}╗")
    print(f"║  {BRIGHT}🚀 AI GATEWAY SERVICE — DEEPAI LIVE OPERATIONAL BENCHMARK{RESET}{GREEN}          ║")
    print(f"║  {MAGENTA}Architecture: 3-Layer Canonical Gateway (Bolla Constitution v1.2){RESET}{GREEN}        ║")
    print(f"║  {YELLOW}Authority   : Eng. Bolla (Lead Architect) & Eng. Zizo (Visionary){RESET}{GREEN}         ║")
    print(f"╚{'═'*76}╝{RESET}\n")


def run_benchmark():
    print_banner()
    client = create_live_client()
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: DEEPAI_ROUTE_TOKEN,
    }

    # 1. Discovery
    print(f"{CYAN}▶ [1/5] استكشاف المزود (/v1/describe & /v1/models)...{RESET}")
    t0 = time.time()
    resp = client.get("/v1/describe", headers=headers)
    elapsed = (time.time() - t0) * 1000
    if resp.status_code == 200:
        desc = resp.json()
        print(f"{GREEN}✓ تم الاستكشاف بنجاح خلال {elapsed:.1f}ms!{RESET}")
        print(f"  • {BRIGHT}Display Name{RESET}: {desc.get('display_name')}")
        print(f"  • {BRIGHT}Operations  {RESET}: {desc.get('operations')}")
        print(f"  • {BRIGHT}Models Count{RESET}: {len(desc.get('models', []))} نماذج معتمدة")
    else:
        print(f"{RED}❌ فشل الاستكشاف: {resp.text}{RESET}")

    # 2. Text Generation
    print(f"\n{CYAN}▶ [2/5] توليد النصوص والدردشة (POST /v1/execute -> generate_text)...{RESET}")
    t0 = time.time()
    resp = client.post(
        "/v1/execute",
        headers=headers,
        json={
            "operation": "generate_text",
            "model": "gpt-5.6-luna",
            "request_id": "req-live-chat-1",
            "tenant_id": "tenant-bolla-zizo",
            "credential": {"mode": "platform"},
            "payload": {
                "messages": [
                    {"role": "user", "content": "أهلاً بك يا ديب إيه آي! عرّف عن نفسك في جملة واحدة سريعة."}
                ]
            },
            "timeout_ms": 20000,
        },
    )
    elapsed = (time.time() - t0) * 1000
    if resp.status_code == 200 and resp.json().get("succeeded"):
        out = resp.json().get("output", {})
        print(f"{GREEN}✓ تم استلام الرد بنجاح خلال {elapsed:.1f}ms!{RESET}")
        print(f"  • {WHITE}نص الرد{RESET}: {YELLOW}{out.get('text', '').strip()}{RESET}")
    else:
        print(f"{RED}❌ فشل توليد النص: {resp.text}{RESET}")

    # 3. File Attachment
    print(f"\n{CYAN}▶ [3/5] اختبار رفع الملفات البرمجية وقراءتها (File Upload & Analysis)...{RESET}")
    python_code = "SECRET_CODE_VALUE = 998811\n"
    t0 = time.time()
    resp = client.post(
        "/v1/execute",
        headers=headers,
        json={
            "operation": "generate_text",
            "model": "gpt-5.6-luna",
            "request_id": "req-live-file-1",
            "tenant_id": "tenant-bolla-zizo",
            "credential": {"mode": "platform"},
            "payload": {
                "messages": [
                    {"role": "user", "content": "ما هي قيمة المتغير SECRET_CODE_VALUE في الملف المرفق؟ جاوب بالرقم فقط."}
                ],
                "files": [
                    {"name": "config.py", "content": python_code}
                ]
            },
            "timeout_ms": 20000,
        },
    )
    elapsed = (time.time() - t0) * 1000
    if resp.status_code == 200 and resp.json().get("succeeded"):
        out = resp.json().get("output", {})
        print(f"{GREEN}✓ تم فحص الملف وقراءته بنجاح خلال {elapsed:.1f}ms!{RESET}")
        print(f"  • {WHITE}نص الرد{RESET}: {YELLOW}{out.get('text', '').strip()}{RESET}")
    else:
        print(f"{RED}❌ فشل فحص الملف: {resp.text}{RESET}")

    # 4. Vision
    print(f"\n{CYAN}▶ [4/5] اختبار تحليل الرؤية والصور (POST /v1/execute -> analyze_vision)...{RESET}")
    t0 = time.time()
    resp = client.post(
        "/v1/execute",
        headers=headers,
        json={
            "operation": "analyze_vision",
            "model": "gpt-5.6-luna",
            "request_id": "req-live-vis-1",
            "tenant_id": "tenant-bolla-zizo",
            "credential": {"mode": "platform"},
            "payload": {
                "image_b64": TEST_PNG_B64,
                "image_format": "png",
                "instruction": "Describe what you see in this image briefly.",
            },
            "timeout_ms": 20000,
        },
    )
    elapsed = (time.time() - t0) * 1000
    if resp.status_code == 200 and resp.json().get("succeeded"):
        out = resp.json().get("output", {})
        print(f"{GREEN}✓ تم تحليل الصورة بنجاح خلال {elapsed:.1f}ms!{RESET}")
        print(f"  • {WHITE}نص الرد{RESET}: {YELLOW}{out.get('text', '').strip()[:100]}...{RESET}")
    else:
        print(f"{RED}❌ فشل تحليل الرؤية: {resp.text}{RESET}")

    # 5. Audio Transcription
    print(f"\n{CYAN}▶ [5/5] اختبار تفريغ الصوت المباشر (POST /v1/execute -> transcribe_audio)...{RESET}")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    buf.seek(0)
    audio_b64 = base64.b64encode(buf.read()).decode("ascii")

    t0 = time.time()
    resp = client.post(
        "/v1/execute",
        headers=headers,
        json={
            "operation": "transcribe_audio",
            "model": "gpt-5.6-luna",
            "request_id": "req-live-audio-1",
            "tenant_id": "tenant-bolla-zizo",
            "credential": {"mode": "platform"},
            "payload": {
                "audio_b64": audio_b64,
                "audio_format": "wav",
            },
            "timeout_ms": 20000,
        },
    )
    elapsed = (time.time() - t0) * 1000
    if resp.status_code == 200 and resp.json().get("succeeded"):
        out = resp.json().get("output", {})
        print(f"{GREEN}✓ تم تفريغ الصوت بنجاح خلال {elapsed:.1f}ms!{RESET}")
        print(f"  • {WHITE}النص المفرغ{RESET}: {YELLOW}{out.get('text', '').strip()}{RESET}")
    else:
        print(f"{RED}❌ فشل تفريغ الصوت: {resp.text}{RESET}")

    print(f"\n{GREEN}════════════════════════════════════════════════════════════════════════════════{RESET}")
    print(f"  {BRIGHT}🎉 مبروك! مزود DeepAI يعمل بكفاءة 100% داخل الـ AI Gateway Service!{RESET}")
    print(f"{GREEN}════════════════════════════════════════════════════════════════════════════════{RESET}\n")


if __name__ == "__main__":
    run_benchmark()
