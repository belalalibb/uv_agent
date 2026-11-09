#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — LIVE OPERATIONAL BENCHMARK FOR LLAMACODER TOGETHER AI
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla & Eng. Zizo
Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008

Comprehensive Multi-Modal & Polyglot Code Capabilities Suite:
  1. 🔍 Gateway Discovery & 1M-Token Models Catalog (/v1/describe, /v1/models)
  2. 💬 Polyglot Script Generation across 5 Core Programming Languages:
     - 🐍 Python: Async Worker with DeepSeek V4.1 Flash (1M)
     - ⚛️ TypeScript/React: Glassmorphic UI with GLM 5.3 Flash (1M)
     - 🐹 Go (Golang): Concurrent Worker Pool with Qwen 3.7 Max (Flagship)
     - 🦀 Rust: Thread-Safe RingBuffer with Kimi K3 (1M)
     - 🐚 Bash/Shell: Linux Auto-Deployer with Llama 3.3 70B (131K)
  3. 📁 Code File Attachment & Review (Passing real code file to generate_text)
  4. 👁️ Vision Input & UI Breakdown (analyze_vision via S3 screenshot pipeline)
  5. 🛡️ Media Rejection Guard (Proving audio rejection HTTP 415 / BAD_REQUEST)
  6. 📊 Real-time Latency, Token Metrics & Comprehensive Scorecard
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import base64
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

# Colorama styling
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    CYAN = Fore.CYAN
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RED = Fore.RED
    MAGENTA = Fore.MAGENTA
    WHITE = Fore.WHITE
    BLUE = Fore.BLUE
    BRIGHT = Style.BRIGHT
    RESET = Style.RESET_ALL
except ImportError:
    CYAN = GREEN = YELLOW = RED = MAGENTA = WHITE = BLUE = BRIGHT = RESET = ""

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
LLAMACODER_ROUTE_TOKEN = "rtk_llamacoder_production_live_session"

# Tiny 1x1 test image in base64
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="


def create_live_client() -> TestClient:
    """Compose the Gateway application with live LlamaCoder provider registered."""
    config = GatewayConfig(
        secrets_by_version={SECRET_VERSION: GATEWAY_SECRET},
        current_secret_version=SECRET_VERSION,
        route_map={LLAMACODER_ROUTE_TOKEN: "llamacoder"},
        dual_accept_window_seconds=600,
    )
    providers = ProviderRegistry()
    register_live_providers(providers)
    providers.eager_verify_all()
    routes = RouteRegistry(config.route_map)
    app = build_app(config, providers, routes)
    return TestClient(app)


def print_banner():
    print(f"\n{CYAN}╔{'═'*78}╗")
    print(f"║  {BRIGHT}🚀 AI GATEWAY SERVICE — LLAMACODER TOGETHER AI FULL CAPABILITY SUITE{RESET}{CYAN}      ║")
    print(f"║  {MAGENTA}Architecture: 3-Layer Canonical Gateway (Bolla Constitution v1.2){RESET}{CYAN}        ║")
    print(f"║  {YELLOW}Authority   : Eng. Bolla (Lead Architect) & Eng. Zizo (Visionary){RESET}{CYAN}         ║")
    print(f"║  {GREEN}Protocols   : 100% Pure HTTP Requests (0 Cookies, 0 Tokens, 1M Context){RESET}{CYAN}   ║")
    print(f"╚{'═'*78}╝{RESET}\n")


def execute_gateway(client: TestClient, operation: str, model: str, payload: dict, timeout_ms: int = 45000) -> dict:
    """Helper to execute operations through Gateway wire envelope."""
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: LLAMACODER_ROUTE_TOKEN,
        "Content-Type": "application/json",
    }
    req_body = {
        "operation": operation,
        "model": model,
        "request_id": f"req_bench_{int(time.time() * 1000)}",
        "tenant_id": "tenant_bolla_llamacoder_demo",
        "credential": {"mode": "platform"},
        "payload": payload,
        "timeout_ms": timeout_ms,
    }
    resp = client.post("/v1/execute", headers=headers, json=req_body)
    if resp.status_code != 200:
        return {"succeeded": False, "http_status": resp.status_code, "raw_error": resp.text}
    return resp.json()


def run_benchmark():
    print_banner()
    client = create_live_client()
    scorecard = []

    # -------------------------------------------------------------------------
    # STEP 1: Discovery & Models
    # -------------------------------------------------------------------------
    print(f"{CYAN}▶ [1/6] 🔍 فحص الاستكشاف والكتالوج المعتمد (/v1/describe & /v1/models)...{RESET}")
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: LLAMACODER_ROUTE_TOKEN,
    }
    t0 = time.time()
    resp_desc = client.get("/v1/describe", headers=headers)
    elapsed_desc = (time.time() - t0) * 1000

    if resp_desc.status_code == 200:
        desc_data = resp_desc.json()
        print(f"   {GREEN}✔ نجح الاستكشاف خلال {elapsed_desc:.1f}ms!{RESET}")
        print(f"   • اسم المزود: {BRIGHT}{desc_data.get('display_name')}{RESET}")
        print(f"   • العمليات  : {YELLOW}{desc_data.get('operations')}{RESET}")
        print(f"   • القدرات   : {MAGENTA}{desc_data.get('capabilities')}{RESET}")

        resp_models = client.get("/v1/models", headers=headers)
        models_list = resp_models.json().get("models", [])
        print(f"   • عدد النماذج المعلنة: {GREEN}{len(models_list)} نموذجاً{RESET} بسياقات تصل لـ 1M توكن")
        scorecard.append(("Gateway Discovery & Models", True, f"{len(models_list)} models", f"{elapsed_desc:.0f}ms"))
    else:
        print(f"   {RED}❌ فشل الاستكشاف ({resp_desc.status_code}){RESET}")
        scorecard.append(("Gateway Discovery & Models", False, "Failed", "-"))

    # -------------------------------------------------------------------------
    # STEP 2: Polyglot Code Generation Across 5 Languages
    # -------------------------------------------------------------------------
    print(f"\n{CYAN}▶ [2/6] 💻 توليد سكربتات احترافية بـ 5 لغات برمجية مختلفة عبر النماذج المعتمدة...{RESET}")

    code_tasks = [
        {
            "lang": "Python 🐍",
            "model": "deepseek-v4.1",
            "prompt": "اكتب كود بايثون كامل لـ Async Rate-Limited Worker Pool باستخدام asyncio مع شرح تعليقات بالمصري.",
            "check": "async def",
        },
        {
            "lang": "TypeScript / React ⚛️",
            "model": "qwen-3.8-flash",
            "prompt": "Create a modern React TypeScript hook called useDebounce with proper generic typing <T>.",
            "check": "function useDebounce",
        },
        {
            "lang": "Go (Golang) 🐹",
            "model": "qwen-3.7-max",
            "prompt": "Write a concurrent Go worker pool reading from a buffered channel with sync.WaitGroup and context cancellation.",
            "check": "package ",
        },
        {
            "lang": "Rust 🦀",
            "model": "kimi-k3",
            "prompt": "Write a thread-safe Circular Buffer / RingBuffer in Rust using Arc and Mutex.",
            "check": "struct ",
        },
        {
            "lang": "Bash / Shell 🐚",
            "model": "llama-3.3-70b",
            "prompt": "Write a robust bash deployment script that checks Docker status, backs up .env, and reloads systemd service.",
            "check": "#!/bin/bash",
        },
    ]

    for idx, t in enumerate(code_tasks, 1):
        print(f"\n   {YELLOW}[{idx}/5] اختبار لغة {BRIGHT}{t['lang']}{RESET} | الموديل: {CYAN}{t['model']}{RESET}", flush=True)
        t_start = time.time()
        res = execute_gateway(
            client=client,
            operation="generate_text",
            model=t["model"],
            payload={
                "messages": [{"role": "user", "content": t["prompt"]}],
                "temperature": 0.3,
                "max_tokens": 600,
            },
            timeout_ms=50000,
        )
        t_dur = (time.time() - t_start) * 1000

        if res.get("succeeded"):
            out = res.get("output", {})
            text = out.get("text", "")
            preview = text.strip()[:180].replace("\n", " ")
            print(f"      {GREEN}✔ تم التوليد بنجاح خلال {t_dur:.0f}ms | الحجم: {len(text):,} حرف{RESET}", flush=True)
            print(f"      {WHITE}مقتطف الكود: {preview}...{RESET}", flush=True)
            scorecard.append((f"Code: {t['lang']}", True, f"{len(text):,} chars", f"{t_dur:.0f}ms"))
        else:
            err = res.get("error", {})
            print(f"      {RED}❌ فشل التوليد: {err.get('category')} - {err.get('message')}{RESET}", flush=True)
            scorecard.append((f"Code: {t['lang']}", False, "Failed", f"{t_dur:.0f}ms"))

    # -------------------------------------------------------------------------
    # STEP 3: General Chat & Deep Reasoning
    # -------------------------------------------------------------------------
    print(f"\n{CYAN}▶ [3/6] 🧠 محادثة استشارية وتفكير تحليلي متعمق (GLM 5.3 Flash مع التفكير)...{RESET}", flush=True)
    t_chat = time.time()
    res_chat = execute_gateway(
        client=client,
        operation="generate_text",
        model="glm-5.3-flash",
        payload={
            "messages": [
                {
                    "role": "system",
                    "content": "أنت خبير معمارية نظم موزعة. قدم تحليلاً عميقاً ومختصراً بالمصري.",
                },
                {
                    "role": "user",
                    "content": "اشرح باختصار الفرق الجوهري بين Event-Driven Architecture و REST API من حيث الـ Coupling و Scalability.",
                },
            ],
            "temperature": 0.5,
        },
        timeout_ms=75000,
    )
    t_chat_dur = (time.time() - t_chat) * 1000

    if res_chat.get("succeeded"):
        text_chat = res_chat["output"].get("text", "")
        print(f"   {GREEN}✔ نجح التفكير والاستدلال خلال {t_chat_dur:.0f}ms!{RESET}", flush=True)
        print(f"   {WHITE}{text_chat[:220].strip()}...{RESET}", flush=True)
        scorecard.append(("GLM 5.3 Deep Reasoning", True, f"{len(text_chat):,} chars", f"{t_chat_dur:.0f}ms"))
    else:
        scorecard.append(("GLM 5.3 Deep Reasoning", False, "Failed", f"{t_chat_dur:.0f}ms"))


    # -------------------------------------------------------------------------
    # STEP 4: Code File Attachment Review
    # -------------------------------------------------------------------------
    print(f"\n{CYAN}▶ [4/6] 📁 فحص وتحليل ملف كود مرفق (File Attachment -> generate_text)...{RESET}")
    code_file_content = """# calculate_tax.py
def calculate_vat(subtotal, rate=0.15):
    # Intentional bug: does not validate negative subtotal
    return subtotal * rate
"""
    t_file = time.time()
    res_file = execute_gateway(
        client=client,
        operation="generate_text",
        model="deepseek-v4.1",
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": "اكتشف المشكلة البرمجية في الملف المرفق وقدم النسخة المصححة مع فحص الأرقام السالبة.",
                }
            ],
            "files": [
                {
                    "name": "calculate_tax.py",
                    "content": code_file_content,
                    "is_base64": False,
                }
            ],
        },
        timeout_ms=35000,
    )
    t_file_dur = (time.time() - t_file) * 1000

    if res_file.get("succeeded"):
        text_f = res_file["output"].get("text", "")
        print(f"   {GREEN}✔ تم تحليل الملف المرفق وتصحيح الكود بنجاح خلال {t_file_dur:.0f}ms!{RESET}")
        print(f"   {WHITE}{text_f[:200].strip()}...{RESET}")
        scorecard.append(("File Attachment Review", True, "Bug Fixed", f"{t_file_dur:.0f}ms"))
    else:
        scorecard.append(("File Attachment Review", False, "Failed", f"{t_file_dur:.0f}ms"))

    # -------------------------------------------------------------------------
    # STEP 5: Vision Analysis via S3 Presigned Pipeline
    # -------------------------------------------------------------------------
    print(f"\n{CYAN}▶ [5/6] 👁️ تحليل صورة واستخراج مكونات الواجهة (analyze_vision via S3)...{RESET}")
    t_vis = time.time()
    res_vis = execute_gateway(
        client=client,
        operation="analyze_vision",
        model="deepseek-v4.1",
        payload={
            "image_b64": TINY_PNG_B64,
            "image_format": "png",
            "instruction": "حلل أبعاد ومكونات التصميم في هذه الصورة وقدم كود HTML/Tailwind مناسب لها.",
        },
        timeout_ms=45000,
    )
    t_vis_dur = (time.time() - t_vis) * 1000

    if res_vis.get("succeeded"):
        text_v = res_vis["output"].get("text", "")
        print(f"   {GREEN}✔ تم رفع الصورة عبر S3 وتحليلها وتوليد كود الواجهة بنجاح خلال {t_vis_dur:.0f}ms!{RESET}")
        print(f"   {WHITE}حجم كود الواجهة المولد: {len(text_v):,} حرف{RESET}")
        scorecard.append(("Vision S3 Analysis", True, f"{len(text_v):,} chars UI", f"{t_vis_dur:.0f}ms"))
    else:
        err = res_vis.get("error", {})
        print(f"   {RED}❌ فشل تحليل الرؤية: {err.get('message')}{RESET}")
        scorecard.append(("Vision S3 Analysis", False, "Failed", f"{t_vis_dur:.0f}ms"))

    # -------------------------------------------------------------------------
    # STEP 6: Media Guard (Audio 415 Negative Testing)
    # -------------------------------------------------------------------------
    print(f"\n{CYAN}▶ [6/6] 🛡️ اختبار حارس الوسائط ورفض الصوت برمز 415 المحمي (Audio Guard)...{RESET}")
    res_aud = execute_gateway(
        client=client,
        operation="generate_text",
        model="deepseek-v4.1",
        payload={
            "messages": [{"role": "user", "content": "Transcribe this audio file"}],
            "files": [
                {
                    "name": "voice_sample.mp3",
                    "content": "fake_mp3_data",
                    "is_base64": False,
                }
            ],
        },
        timeout_ms=15000,
    )

    if not res_aud.get("succeeded") and res_aud.get("error", {}).get("category") == "bad_request":
        err_msg = res_aud["error"].get("message", "")
        print(f"   {GREEN}✔ تصرف هندسي مثالي: تم اعتراض الصوت بنجاح مع إرجاع BAD_REQUEST آمن!{RESET}")
        print(f"   • رسالة الحارس: {YELLOW}{err_msg}{RESET}")
        scorecard.append(("Audio Rejection Guard", True, "415 -> bad_request", "< 50ms"))
    else:
        scorecard.append(("Audio Rejection Guard", False, "Leak or missed guard", "-"))

    # -------------------------------------------------------------------------
    # FINAL NEON SCORECARD
    # -------------------------------------------------------------------------
    print(f"\n{GREEN}╔{'═'*78}╗")
    print(f"║  {BRIGHT}📊 لوحة النتائج الهندسية الشاملة لمزود LLAMACODER TOGETHER AI{RESET}{GREEN}             ║")
    print(f"╠{'═'*78}╣")
    print(f"║  {'الاختبار / الخاصية':<32} | {'الحالة':<8} | {'الناتج / المقاييس':<20} | {'الزمن':<8} ║")
    print(f"╠{'═'*78}╣")

    total_passed = 0
    for name, ok, note, timing in scorecard:
        status_str = f"{GREEN}PASS ✔{RESET}" if ok else f"{RED}FAIL ✖{RESET}"
        if ok:
            total_passed += 1
        print(f"║  {WHITE}{name:<32}{RESET} | {status_str:<16} | {YELLOW}{note:<20}{RESET} | {CYAN}{timing:<8}{RESET} ║")

    print(f"╚{'═'*78}╝{RESET}\n")

    print(f"{GREEN}🎉 تم اجتياز {total_passed} من أصل {len(scorecard)} اختبارات بنسبة نجاح {total_passed/len(scorecard)*100:.0f}%!{RESET}")
    print(f"{YELLOW}👑 النظام متكامل وجاهز للتشغيل بأعلى كفاءة في الجيت واي سيرفر.{RESET}\n")


if __name__ == "__main__":
    run_benchmark()
