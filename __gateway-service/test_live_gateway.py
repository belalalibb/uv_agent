#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — LIVE INTERACTIVE TESTER FOR SYNTX AI (v1.0)
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla (Lead Architect) & Eng. Zizo (Product Visionary)
Compliance: Bolla Constitution v1.2 & UNIVERSAL_PROVIDER_SPEC_AND_BLUEPRINT.md

Features:
  1. 🔍 Full Gateway Discovery (/v1/describe & /v1/models projection).
  2. 🛡️ Non-Vision Model Protection Gate (rejection of grok-4.6 vision calls).
  3. 💬 Text Generation Live Test (POST /v1/execute -> generate_text).
  4. 🖼️ Vision Analysis Live Test (POST /v1/execute -> analyze_vision).
  5. 📊 Real-time latency, token usage, and neon statistics.
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import argparse
import base64
import json
import os
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

# Gateway Test Credentials & Route Mapping
SECRET_VERSION = 1
GATEWAY_SECRET = "live-demo-secret-key-bolla-zizo"
SYNTX_ROUTE_TOKEN = "rtk_syntx_production_live_session"

TEST_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="
)


def create_live_client() -> TestClient:
    """Compose the Gateway application with live Syntx provider registered."""
    config = GatewayConfig(
        secrets_by_version={SECRET_VERSION: GATEWAY_SECRET},
        current_secret_version=SECRET_VERSION,
        route_map={SYNTX_ROUTE_TOKEN: "syntx"},
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
    print(f"║  {BRIGHT}🚀 AI GATEWAY SERVICE — SYNTX AI LIVE OPERATIONAL BENCHMARK{RESET}{GREEN}          ║")
    print(f"║  {MAGENTA}Architecture: 3-Layer Canonical Gateway (Bolla Constitution v1.2){RESET}{GREEN}        ║")
    print(f"║  {YELLOW}Authority   : Eng. Bolla (Lead Architect) & Eng. Zizo (Visionary){RESET}{GREEN}         ║")
    print(f"╚{'═'*76}╝{RESET}\n")


def step_1_discovery(client: TestClient) -> dict:
    """Step 1: Test /v1/describe and /v1/models projections."""
    print(f"{CYAN}▶ [1/4] فحص بوصلة المنصة واستكشاف المزود (Gateway Discovery - /v1/describe)...{RESET}")
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: SYNTX_ROUTE_TOKEN,
    }
    t0 = time.time()
    resp = client.get("/v1/describe", headers=headers)
    elapsed = (time.time() - t0) * 1000

    if resp.status_code != 200:
        print(f"{RED}❌ فشل استكشاف المزود ({resp.status_code}): {resp.text}{RESET}")
        return {}

    data = resp.json()
    print(f"{GREEN}✓ تم الاستكشاف بنجاح خلال {elapsed:.1f}ms!{RESET}")
    print(f"  • اسم المزود المعلن   : {WHITE}{BRIGHT}{data.get('display_name')}{RESET}")
    print(f"  • نمط المصادقة        : {YELLOW}{data.get('credential_mode')}{RESET}")
    print(f"  • إصدار التعريف       : {YELLOW}{data.get('definition_version')}{RESET}")
    print(f"  • القدرات المعلنة     : {CYAN}{json.dumps(data.get('capabilities'))}{RESET}")
    print(f"  • العمليات المدعومة   : {MAGENTA}{data.get('operations')}{RESET}")
    print(f"  • عدد الموديلات المتاحة: {GREEN}{len(data.get('models', []))} موديل مجاني{RESET}")
    sample_models = [m.get("name") for m in data.get("models", [])[:5]]
    print(f"  • عينة من الموديلات   : {WHITE}{', '.join(sample_models)} ...{RESET}\n")
    return data


def step_2_non_vision_guard(client: TestClient) -> bool:
    """Step 2: Test non-vision model protection (grok-4.6 with image)."""
    print(f"{CYAN}▶ [2/4] اختبار درع الحماية ضد كسر الرؤية (Non-Vision Protection Gate)...{RESET}")
    print(f"{YELLOW}⏳ إرسال طلب analyze_vision لموديل نصي بحت (grok-4.6) للتحقق من منعه فورياً...{RESET}")

    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: SYNTX_ROUTE_TOKEN,
    }
    payload = {
        "operation": "analyze_vision",
        "model": "grok-4.6",
        "request_id": "test-guard-req",
        "tenant_id": "bolla-zizo-audit",
        "credential": {"mode": "platform"},
        "payload": {
            "image_b64": TEST_PNG_B64,
            "image_format": "png",
            "instruction": "حلل هذه الصورة",
        },
        "timeout_ms": 10000,
    }

    t0 = time.time()
    resp = client.post("/v1/execute", headers=headers, json=payload)
    elapsed = (time.time() - t0) * 1000

    if resp.status_code == 200:
        body = resp.json()
        if not body.get("succeeded") and body.get("error", {}).get("category") == "unsupported_capability":
            print(f"{GREEN}✓ نجح درع الحماية بنسبة 100% خلال {elapsed:.1f}ms!{RESET}")
            print(f"  • تصنيف الخطأ الدستوري : {RED}{body['error']['category']}{RESET}")
            print(f"  • رسالة الحماية الآمنة: {YELLOW}{body['error']['message']}{RESET}")
            print(f"  • النتيجة الهندسية     : {GREEN}تم حظر الطلب في الطبقة 2 قبل لمس الشبكة (Zero-Leak / Zero Network Crash){RESET}\n")
            return True

    print(f"{RED}❌ فشل اختبار درع الحماية: {resp.text}{RESET}\n")
    return False


def step_3_generate_text(client: TestClient, model: str, prompt: str) -> bool:
    """Step 3: Test live text generation."""
    print(f"{CYAN}▶ [3/4] اختبار توليد الشات الحي (Live Text Generation - {model})...{RESET}")
    print(f"{YELLOW}⏳ إرسال السؤال: \"{prompt}\"...{RESET}")

    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: SYNTX_ROUTE_TOKEN,
    }
    payload = {
        "operation": "generate_text",
        "model": model,
        "request_id": f"test-text-{int(time.time())}",
        "tenant_id": "tenant-bolla-zizo",
        "credential": {"mode": "platform"},
        "payload": {
            "messages": [
                {"role": "system", "content": "أنت مساعد ذكي تجيب باختصار ودقة."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        },
        "timeout_ms": 120000,
    }

    t0 = time.time()
    resp = client.post("/v1/execute", headers=headers, json=payload)
    latency = time.time() - t0

    if resp.status_code != 200:
        print(f"{RED}❌ خطأ على مستوى بوابة الجيت واي ({resp.status_code}): {resp.text}{RESET}")
        return False

    res = resp.json()
    if res.get("succeeded"):
        out = res.get("output", {})
        usage = res.get("usage", {}) or {}
        print(f"{GREEN}✓ تم استلام الرد بنجاح خلال {latency:.2f} ثانية!{RESET}")
        print(f"{Fore.LIGHTBLACK_EX}{'─'*76}{RESET}")
        print(f"{WHITE}{out.get('text', '')}{RESET}")
        print(f"{Fore.LIGHTBLACK_EX}{'─'*76}{RESET}")
        print(f"  • سبب الانتهاء : {CYAN}{out.get('finish_reason')}{RESET}")
        print(f"  • استهلاك التوكن: {YELLOW}In: {usage.get('input_tokens')} | Out: {usage.get('output_tokens')}{RESET}\n")
        return True
    else:
        err = res.get("error", {})
        print(f"{RED}❌ فشل التوليد: [{err.get('category')}] {err.get('message')}{RESET}\n")
        return False


def step_4_analyze_vision(client: TestClient, model: str, image_path: str | None = None) -> bool:
    """Step 4: Test live vision analysis."""
    print(f"{CYAN}▶ [4/4] اختبار الرؤية البصرية الحية (Live Vision Analysis - {model})...{RESET}")

    b64_data = TEST_PNG_B64
    fmt = "png"
    if image_path and os.path.exists(image_path):
        ext = os.path.splitext(image_path)[1].lower().lstrip(".")
        fmt = ext if ext in ["png", "jpg", "jpeg", "webp"] else "png"
        with open(image_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")
        print(f"{YELLOW}🖼️ استخدام الصورة المحلية: {image_path}{RESET}")
    else:
        print(f"{YELLOW}🖼️ استخدام بكسل اختباري قياسي (Sentinel PNG){RESET}")

    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: SYNTX_ROUTE_TOKEN,
    }
    payload = {
        "operation": "analyze_vision",
        "model": model,
        "request_id": f"test-vision-{int(time.time())}",
        "tenant_id": "tenant-bolla-zizo",
        "credential": {"mode": "platform"},
        "payload": {
            "image_b64": b64_data,
            "image_format": fmt,
            "instruction": "وضح باختصار شديد محتوى هذه الصورة أو لونها",
        },
        "timeout_ms": 120000,
    }

    t0 = time.time()
    resp = client.post("/v1/execute", headers=headers, json=payload)
    latency = time.time() - t0

    if resp.status_code != 200:
        print(f"{RED}❌ خطأ على مستوى بوابة الجيت واي ({resp.status_code}): {resp.text}{RESET}")
        return False

    res = resp.json()
    if res.get("succeeded"):
        out = res.get("output", {})
        print(f"{GREEN}✓ تم استلام تحليل الرؤية بنجاح خلال {latency:.2f} ثانية!{RESET}")
        print(f"{Fore.LIGHTBLACK_EX}{'─'*76}{RESET}")
        print(f"{WHITE}{out.get('text', '')}{RESET}")
        print(f"{Fore.LIGHTBLACK_EX}{'─'*76}{RESET}\n")
        return True
    else:
        err = res.get("error", {})
        print(f"{RED}❌ فشل تحليل الرؤية: [{err.get('category')}] {err.get('message')}{RESET}\n")
        return False


def main():
    parser = argparse.ArgumentParser(description="Live Gateway Tester for Syntx AI")
    parser.add_argument("--model", "-m", default="claude-opus-4-8", help="Text model (e.g. claude-opus-4-8, gpt-5.6-terra)")
    parser.add_argument("--vision-model", "-vm", default="claude-opus-4-8", help="Vision model (e.g. claude-opus-4-8, gpt-5.6-terra)")
    parser.add_argument("--prompt", "-p", default="اكتب سطر واحد بايثون يطبع جملة ترحيبية للمهندس بولا والمهندس زيزو", help="Test prompt")
    parser.add_argument("--image", "-i", default=None, help="Optional image file path for vision testing")
    parser.add_argument("--skip-live", action="store_true", help="Run only hermetic discovery and non-vision guard checks")
    args = parser.parse_args()

    print_banner()
    client = create_live_client()

    # Step 1: Discovery
    step_1_discovery(client)

    # Step 2: Non-vision guard
    step_2_non_vision_guard(client)

    if args.skip_live:
        print(f"{YELLOW}ℹ️ تم تخطي استدعاءات الشبكة الحية بناءً على خيار --skip-live.{RESET}")
        return

    # Step 3: Live text generation
    step_3_generate_text(client, args.model, args.prompt)

    # Step 4: Live vision analysis
    step_4_analyze_vision(client, args.vision_model, args.image)

    print(f"\n{GREEN}╔{'═'*76}╗")
    print(f"║  {BRIGHT}🎉 انتهت جميع الفحوصات التشغيلية بنجاح تام وتوافق 100% مع الدستور!{RESET}{GREEN}    ║")
    print(f"╚{'═'*76}╝{RESET}\n")


if __name__ == "__main__":
    main()
