#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 KIMI K3 (moonshotai/Kimi-K3) — COMPREHENSIVE ENDURANCE & STRESS BENCHMARK
════════════════════════════════════════════════════════════════════════════════
Authority : Eng. Bolla & Eng. Zizo
Focus     : Testing Kimi K3 (1M Context) endurance, 2-minute barrier, concurrency,
            streaming sustained throughput, and multi-modal file analysis.
════════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
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

import requests
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
KIMI_MODEL = "kimi-k3"


def create_live_client() -> TestClient:
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


def execute_gateway(client: TestClient, payload: dict, timeout_ms: int = 60000) -> dict:
    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: LLAMACODER_ROUTE_TOKEN,
        "Content-Type": "application/json",
    }
    req_body = {
        "operation": "generate_text",
        "model": KIMI_MODEL,
        "request_id": f"req_kimi_{int(time.time() * 1000)}",
        "tenant_id": "tenant_bolla_kimi_endurance",
        "credential": {"mode": "platform"},
        "payload": payload,
        "timeout_ms": timeout_ms,
    }
    resp = client.post("/v1/execute", headers=headers, json=req_body)
    if resp.status_code != 200:
        return {"succeeded": False, "http_status": resp.status_code, "raw_error": resp.text}
    return resp.json()


def run_kimi_live_stream(prompt: str, max_wait_sec: int = 180) -> tuple[bool, str, float, int]:
    """
    Direct low-level streaming monitor that measures time-to-first-token (TTFT),
    sustained streaming rate, and whether it survives past the 2-minute mark.
    """
    base_url = "https://llamacoder.together.ai"
    headers = {
        "Origin": base_url,
        "Referer": f"{base_url}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    t_start = time.time()
    # 1. Create chat
    try:
        r1 = requests.post(
            f"{base_url}/api/create-chat",
            headers=headers,
            json={"prompt": prompt, "model": "moonshotai/Kimi-K3"},
            timeout=20,
        )
    except Exception as e:
        return False, f"create-chat network error: {e}", 0.0, 0
        
    if r1.status_code != 200:
        return False, f"create-chat HTTP {r1.status_code}: {r1.text[:100]}", 0.0, 0

    data1 = r1.json()
    msg_id = data1.get("lastMessageId")
    if not msg_id:
        return False, "Missing lastMessageId", 0.0, 0
        
    t_chat_created = time.time()
    
    # 2. Stream completion
    try:
        r2 = requests.post(
            f"{base_url}/api/get-next-completion-stream-promise",
            headers=headers,
            json={"messageId": msg_id, "model": "moonshotai/Kimi-K3"},
            stream=True,
            timeout=max_wait_sec,
        )
    except Exception as e:
        return False, f"stream network error: {e}", 0.0, 0

    if r2.status_code != 200:
        return False, f"stream HTTP {r2.status_code}: {r2.text[:150]}", 0.0, 0

    collected = []
    chunk_count = 0
    t_first_token = None
    last_print = time.time()
    
    for line in r2.iter_lines():
        if line:
            now = time.time()
            try:
                chunk = json.loads(line.decode("utf-8"))
                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content") or delta.get("reasoning_content") or ""
                if content:
                    if t_first_token is None:
                        t_first_token = now
                    collected.append(content)
                    chunk_count += 1
                
                # Print live ticker every 10 seconds
                if now - last_print >= 10.0:
                    elapsed = now - t_start
                    print(f"      ⏳ [استمرار البث الحي] مضى {elapsed:.0f}s | تم استقبال {len(collected)} كلمة/جزء...", flush=True)
                    last_print = now
                    
                if choice.get("finish_reason") in ("stop", "length", "eos"):
                    break
            except Exception:
                continue

    total_time = time.time() - t_start
    full_text = "".join(collected)
    return True, full_text, total_time, chunk_count


def test_level_1_quick_logic(client: TestClient) -> dict:
    print(f"\n{CYAN}▶ [المستوى 1/5] ⚡ اختبار الأسئلة السريعة والمنطق التحليلي العربي (Short Query)...{RESET}")
    prompt = "لغز منطقي سريع: عندك 3 صناديق مقفولة: واحد فيه تفاح، وواحد برتقال، وواحد مشكل، وكل الصناديق عليها لافتات غلط 100%. مسموح لك تفتح صندوق واحد وتسحب حبة فاكهة واحدة فقط بدون ما تبص جواه. اشرح في 4 خطوات إزاي تعرف محتوى كل صندوق بيقين؟"
    t0 = time.time()
    res = execute_gateway(client, {"messages": [{"role": "user", "content": prompt}]}, timeout_ms=30000)
    dur = time.time() - t0
    
    if res.get("succeeded"):
        text = res.get("output", {}).get("text", "")
        print(f"   {GREEN}✔ نجح Kimi K3 خلال {dur:.2f} ثانية! الحجم: {len(text):,} حرف{RESET}")
        print(f"   {WHITE}مقتطف الإجابة: {text[:220].strip()}...{RESET}")
        return {"passed": True, "dur": dur, "chars": len(text)}
    else:
        err = res.get("error", {})
        print(f"   {RED}❌ فشل: {err.get('category')} - {err.get('message')}{RESET}")
        return {"passed": False, "dur": dur, "err": err}


def test_level_2_medium_code(client: TestClient) -> dict:
    print(f"\n{CYAN}▶ [المستوى 2/5] 🐍 اختبار توليد كود بايثون متقدم (Token Bucket Rate Limiter)...{RESET}")
    prompt = "Write a complete production-ready Python Async Token Bucket Rate Limiter using asyncio and dataclasses with proper type annotations and doctests."
    t0 = time.time()
    res = execute_gateway(client, {"messages": [{"role": "user", "content": prompt}]}, timeout_ms=60000)
    dur = time.time() - t0
    
    if res.get("succeeded"):
        text = res.get("output", {}).get("text", "")
        print(f"   {GREEN}✔ تم توليد الكود بنجاح خلال {dur:.2f} ثانية! الحجم: {len(text):,} حرف{RESET}")
        print(f"   {WHITE}مقتطف الكود: {text[:200].strip()}...{RESET}")
        return {"passed": True, "dur": dur, "chars": len(text)}
    else:
        err = res.get("error", {})
        print(f"   {RED}❌ فشل: {err.get('category')} - {err.get('message')}{RESET}")
        return {"passed": False, "dur": dur, "err": err}


def test_level_3_endurance_barrier() -> dict:
    print(f"\n{CYAN}▶ [المستوى 3/5] ⏱️ اختبار كسر حاجز الدقيقتين والتحمل الأقصى (The 2-Minute + Endurance Barrier)...{RESET}")
    print(f"   {YELLOW}سنطلب من Kimi K3 توليد منظومة معمارية ضخمة بملفات متعددة لاختبار استمرارية البث الحي وتجاوز الـ 120 ثانية...{RESET}")
    prompt = (
        "Architect and implement a complete High-Throughput Distributed RingBuffer and Event Stream engine in Rust. "
        "Include full definitions for zero-copy ring buffer with atomic head/tail pointers, worker threads using crossbeam, "
        "comprehensive error handling, concurrency benchmarks, and complete comments."
    )
    ok, text, total_time, chunks = run_kimi_live_stream(prompt=prompt, max_wait_sec=240)
    
    exceeded_2min = total_time >= 120.0
    status_emoji = "🔥" if exceeded_2min else "⚡"
    
    if ok and len(text) > 200:
        print(f"   {GREEN}✔ صمد Kimi K3 واكتمل التوليد بنجاح!{RESET}")
        print(f"   • زمن التشغيل الفعلي: {BRIGHT}{total_time:.2f} ثانية{RESET} {status_emoji}")
        print(f"   • هل تخطى حاجز الدقيقتين (120s)؟ {GREEN if exceeded_2min else YELLOW}{'نعم تخطى الدقيقتين بثبات كامل!' if exceeded_2min else f'انتهى في وقت أسرع ({total_time:.1f}s)'}{RESET}")
        print(f"   • حجم الناتج الكلي: {MAGENTA}{len(text):,} حرف{RESET} عبر {CYAN}{chunks:,} chunks{RESET}")
        return {"passed": True, "dur": total_time, "exceeded_2min": exceeded_2min, "chars": len(text)}
    else:
        print(f"   {RED}❌ انقطع الاتصال أو حدث خطأ بعد {total_time:.2f}s: {text[:200]}{RESET}")
        return {"passed": False, "dur": total_time, "err": text[:200]}


def test_level_4_file_attachment(client: TestClient) -> dict:
    print(f"\n{CYAN}▶ [المستوى 4/5] 📁 اختبار مراجعة وتدقيق ملف برمجي كامل (Deadlock & Memory Leak Audit)...{RESET}")
    buggy_code = """import threading
import time

lock_a = threading.Lock()
lock_b = threading.Lock()

def thread_one():
    with lock_a:
        time.sleep(0.1)
        with lock_b:
            print("Thread 1 finished")

def thread_two():
    with lock_b:
        time.sleep(0.1)
        with lock_a:
            print("Thread 2 finished")
"""
    t0 = time.time()
    res = execute_gateway(
        client,
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": "حلل الكود المرفق واكتشف ثغرة الـ Deadlock الناتجة عن ترتيب الأقفال وقدم النسخة المصححة بمبدأ Lock Ordering مع الشرح بالمصري.",
                }
            ],
            "files": [
                {
                    "name": "deadlock_sample.py",
                    "content": buggy_code,
                    "is_base64": False,
                }
            ],
        },
        timeout_ms=45000,
    )
    dur = time.time() - t0
    if res.get("succeeded"):
        text = res.get("output", {}).get("text", "")
        print(f"   {GREEN}✔ تم تدقيق الملف المرفق وحل الثغرة بنجاح خلال {dur:.2f} ثانية!{RESET}")
        print(f"   {WHITE}مقتطف التدقيق: {text[:220].strip()}...{RESET}")
        return {"passed": True, "dur": dur, "chars": len(text)}
    else:
        err = res.get("error", {})
        print(f"   {RED}❌ فشل التدقيق: {err.get('message')}{RESET}")
        return {"passed": False, "dur": dur, "err": err}


def test_level_5_concurrency_burst(client: TestClient) -> dict:
    print(f"\n{CYAN}▶ [المستوى 5/5] 💥 اختبار تحمل الطلبات المتزامنة في نفس اللحظة (Burst Concurrency)...{RESET}")
    print(f"   {YELLOW}إرسال 2 طلب متوازي لـ Kimi K3 للتأكد من قدرة السيرفر على خدمة أكثر من محادثة في وقت واحد...{RESET}")
    import concurrent.futures
    
    prompts = [
        "ما هو الفرق بين Mutex و Semaphore في سطرين؟",
        "ما هو الفرق بين TCP و UDP في سطرين؟",
    ]
    
    t0 = time.time()
    results = []
    
    def send_one(p: str):
        c = create_live_client()
        return execute_gateway(c, {"messages": [{"role": "user", "content": p}]}, timeout_ms=35000)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futs = [executor.submit(send_one, p) for p in prompts]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
            
    dur = time.time() - t0
    all_succeeded = all(r.get("succeeded") for r in results)
    
    if all_succeeded:
        print(f"   {GREEN}✔ نجح اختبار التزامن! تم الرد على الطلبين المتزامنين في {dur:.2f} ثانية بنجاح 100%!{RESET}")
        return {"passed": True, "dur": dur}
    else:
        print(f"   {YELLOW}⚠️ انتهى الطلب في {dur:.2f}s لكن واجه أحد الطلبات اعتراضاً.{RESET}")
        return {"passed": False, "dur": dur}


def main():
    print(f"\n{GREEN}╔{'═'*78}╗")
    print(f"║  {BRIGHT}🚀 KIMI K3 LIVE OPERATIONAL & ENDURANCE STRESS SUITE (1M CONTEXT){RESET}{GREEN}         ║")
    print(f"║  {YELLOW}Authority : Eng. Bolla & Eng. Zizo{RESET}{GREEN}                                           ║")
    print(f"║  {CYAN}Objectives: Test 2-Minute Barrier, Concurrency, File Audit & Code Output{RESET}{GREEN}      ║")
    print(f"╚{'═'*78}╝{RESET}")
    
    client = create_live_client()
    scorecard = []
    
    # 1. Quick Logic
    r1 = test_level_1_quick_logic(client)
    scorecard.append(("1. Quick Arabic Logic", r1["passed"], f"{r1.get('dur', 0):.1f}s", f"{r1.get('chars', 0):,} chars"))
    
    # 2. Medium Code
    r2 = test_level_2_medium_code(client)
    scorecard.append(("2. Python Token Bucket", r2["passed"], f"{r2.get('dur', 0):.1f}s", f"{r2.get('chars', 0):,} chars"))

    # 3. File Attachment
    r4 = test_level_4_file_attachment(client)
    scorecard.append(("3. File Deadlock Audit", r4["passed"], f"{r4.get('dur', 0):.1f}s", f"{r4.get('chars', 0):,} chars"))

    # 4. Concurrency Burst
    r5 = test_level_5_concurrency_burst(client)
    scorecard.append(("4. Concurrency Burst (x2)", r5["passed"], f"{r5.get('dur', 0):.1f}s", "2 Concurrent OK"))

    # 5. The 2-Minute + Endurance Barrier
    r3 = test_level_3_endurance_barrier()
    endurance_note = "Exceeded 2min 🔥" if r3.get("exceeded_2min") else f"{r3.get('dur', 0):.1f}s"
    scorecard.append(("5. The 2-Min Barrier Test", r3["passed"], f"{r3.get('dur', 0):.1f}s", endurance_note))

    # Print Neon Scorecard
    print(f"\n{GREEN}╔{'═'*78}╗")
    print(f"║  {BRIGHT}📊 KIMI K3 ENDURANCE & CAPABILITIES SCORECARD{RESET}{GREEN}                               ║")
    print(f"╠{'═'*78}╣")
    print(f"║  {'الاختبار / المحور':<30} | {'الحالة':<8} | {'الزمن':<10} | {'المقاييس':<22} ║")
    print(f"╠{'═'*78}╣")
    
    passed_count = 0
    for name, ok, timing, metrics in scorecard:
        status_str = f"{GREEN}PASS ✔{RESET}" if ok else f"{RED}FAIL ✖{RESET}"
        if ok:
            passed_count += 1
        print(f"║  {WHITE}{name:<30}{RESET} | {status_str:<16} | {YELLOW}{timing:<10}{RESET} | {CYAN}{metrics:<22}{RESET} ║")
        
    print(f"╚{'═'*78}╝{RESET}\n")
    print(f"{GREEN}🎉 النتيجة الإجمالية: {passed_count} من أصل {len(scorecard)} بنسبة نجاح {passed_count/len(scorecard)*100:.0f}%!{RESET}\n")


if __name__ == "__main__":
    main()
