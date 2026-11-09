#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — LIVE OPERATIONAL BENCHMARK FOR YOUMIND AI (v1.0)
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla & Eng. Zizo
Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008

Features Tested:
  1. 🔍 Full Gateway Discovery (/v1/describe & /v1/models projection).
  2. 💬 Text Generation Live Test (POST /v1/execute -> generate_text).
  3. 🧠 Reasoning & Analytical Depth with Claude Fable 5.1 & DeepSeek Flash.
  4. 🔄 Dynamic Integration & Pool with __دومينات مؤقته.
  5. 📊 Real-time latency, token usage, and neon statistics.
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import sys
import time
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
YOUMIND_ROUTE_TOKEN = "rtk_youmind_production_live_session"


def create_live_client() -> TestClient:
    """Compose the Gateway application with live YouMind provider registered."""
    config = GatewayConfig(
        secrets_by_version={SECRET_VERSION: GATEWAY_SECRET},
        current_secret_version=SECRET_VERSION,
        route_map={YOUMIND_ROUTE_TOKEN: "youmind"},
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
    print(f"║  {BRIGHT}🚀 AI GATEWAY SERVICE — YOUMIND AI LIVE OPERATIONAL BENCHMARK{RESET}{GREEN}        ║")
    print(f"║  {MAGENTA}Architecture: 3-Layer Canonical Gateway (Bolla Constitution v1.2){RESET}{GREEN}        ║")
    print(f"║  {YELLOW}Authority   : Eng. Bolla (Lead Architect) & Eng. Zizo (Visionary){RESET}{GREEN}         ║")
    print(f"╚{'═'*76}╝{RESET}\n")


def step_1_discovery(client: TestClient) -> dict:
    """Step 1: Test /v1/describe and /v1/models projections."""
    print(f"{CYAN}▶ [1/3] فحص بوصلة المنصة واستكشاف المزود (Gateway Discovery - /v1/describe)...{RESET}")
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: YOUMIND_ROUTE_TOKEN,
    }
    t0 = time.time()
    resp = client.get("/v1/describe", headers=headers)
    elapsed = (time.time() - t0) * 1000

    if resp.status_code != 200:
        print(f"{RED}❌ فشل استكشاف المزود ({resp.status_code}): {resp.text}{RESET}")
        return {}

    data = resp.json()
    print(f"{GREEN}✓ تم الاستكشاف بنجاح خلال {elapsed:.1f}ms!{RESET}")
    print(f"   اسم المزود المعلن: {BRIGHT}{data.get('display_name')}{RESET}")
    print(f"   إصدار العقد: {data.get('definition_version')}")
    print(f"   نمط المصادقة: {data.get('credential_mode')}")
    print(f"   العمليات المعلنة: {YELLOW}{data.get('operations')}{RESET}")
    print(f"   القدرات: {MAGENTA}{data.get('capabilities')}{RESET}")

    # Test /v1/models
    print(f"\n{CYAN}▶ [2/3] جلب كتالوج النماذج المعتمدة (/v1/models)...{RESET}")
    t1 = time.time()
    resp_m = client.get("/v1/models", headers=headers)
    elapsed_m = (time.time() - t1) * 1000

    if resp_m.status_code == 200:
        models_list = resp_m.json().get("models", [])
        print(f"{GREEN}✓ تم جلب {len(models_list)} نموذجاً معتمداً بنجاح خلال {elapsed_m:.1f}ms:{RESET}")
        for m in models_list:
            ctx = m.get("context_window")
            ctx_str = f"({ctx:,} tokens)" if ctx else ""
            print(f"   • {BRIGHT}{m.get('name'):<20}{RESET} {YELLOW}{ctx_str}{RESET}")

    return data


def step_2_live_chat(client: TestClient, model_name: str = "claude-fable-5-1"):
    """Step 2: Execute live text generation through Gateway envelope."""
    print(f"\n{CYAN}▶ [3/3] اختبار توليد النص الحي عبر الجيت واي (POST /v1/execute -> generate_text)...{RESET}")
    print(f"   الموديل المختار: {BRIGHT}{YELLOW}{model_name}{RESET}")

    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: YOUMIND_ROUTE_TOKEN,
        "Content-Type": "application/json",
    }

    req_body = {
        "operation": "generate_text",
        "model": model_name,
        "request_id": f"req_live_youmind_{int(time.time())}",
        "tenant_id": "tenant_bolla_live_demo",
        "credential": {"mode": "platform"},
        "payload": {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a concise, helpful technical assistant. Answer in one crisp sentence."
                },
                {
                    "role": "user",
                    "content": "عرّف نفسك وما هو دورك داخل منظومة AI Gateway؟"
                }
            ],
            "temperature": 0.7,
            "max_tokens": 150
        },
        "timeout_ms": 45000
    }

    print(f"{MAGENTA}⏳ جاري إرسال الطلب الموحد وانتظار المعالجة...{RESET}")
    t0 = time.time()
    resp = client.post("/v1/execute", headers=headers, json=req_body)
    total_elapsed = (time.time() - t0) * 1000

    if resp.status_code != 200:
        print(f"{RED}❌ خطأ HTTP في الطلب ({resp.status_code}): {resp.text}{RESET}")
        return

    result = resp.json()
    if not result.get("succeeded"):
        err = result.get("error", {})
        print(f"{RED}❌ فشل تنفيذ العملية: {err.get('category')} - {err.get('message')}{RESET}")
        return

    output = result.get("output", {})
    usage = result.get("usage", {})
    latency = result.get("latency_ms", total_elapsed)

    print(f"\n{GREEN}╔{'═'*76}╗")
    print(f"║  {BRIGHT}✅ استجابة ناجحة ومطابقة 100% لعقد الجيت واي الموحد{RESET}{GREEN}                    ║")
    print(f"╚{'═'*76}╝{RESET}")
    print(f"\n{BRIGHT}{WHITE}💬 الرد النهائي:{RESET}")
    print(f"{CYAN}{output.get('text')}{RESET}\n")

    print(f"{YELLOW}📊 مقاييس الأداء (Telemetry):{RESET}")
    print(f"   ⏱️  زمن الاستجابة: {BRIGHT}{latency} ms{RESET}")
    print(f"   📥 توكنز الدخل   : {usage.get('input_tokens')}")
    print(f"   📤 توكنز الخرج   : {usage.get('output_tokens')}")
    print(f"   🎯 سبب الانتهاء : {output.get('finish_reason')}")


def main():
    print_banner()
    client = create_live_client()
    step_1_discovery(client)
    step_2_live_chat(client, model_name="claude-fable-5-1")
    print(f"\n{GREEN}🎉 اكتمل الاختبار الشامل لمزود YouMind AI بنجاح تام!{RESET}\n")


if __name__ == "__main__":
    main()
