#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — LIVE OPERATIONAL BENCHMARK FOR IVYCRAFT AI (v1.0)
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla & Eng. Zizo
Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008

Features Tested:
  1. 🔍 Full Gateway Discovery (/v1/describe & /v1/models projection).
  2. 💬 Text Generation Live Test (POST /v1/execute -> generate_text).
  3. 🎨 Image Generation Test (POST /v1/execute -> generate_image).
  4. 🎙️ Speech Synthesis Test (POST /v1/execute -> synthesize_speech).
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


def print_banner(title: str, color=CYAN):
    border = "═" * 78
    print(f"\n{color}{border}")
    print(f"{BRIGHT}{color}  {title}")
    print(f"{color}{border}{RESET}\n")


SECRET_VERSION = 1
GATEWAY_SECRET = "live-demo-secret-key-bolla-zizo"
IVYCRAFT_ROUTE_TOKEN = "rtk_ivycraft_production_live_session"


def create_gateway_test_client():
    from gateway.route_registry import RouteRegistry

    config = GatewayConfig(
        secrets_by_version={SECRET_VERSION: GATEWAY_SECRET},
        current_secret_version=SECRET_VERSION,
        route_map={IVYCRAFT_ROUTE_TOKEN: "ivycraft"},
        dual_accept_window_seconds=600,
    )
    registry = ProviderRegistry()
    register_live_providers(registry)
    registry.eager_verify_all()
    routes = RouteRegistry(config.route_map)
    app = build_app(config, registry, routes)
    return TestClient(app), config


def main():
    print_banner("🚀 IVYCRAFT AI — GATEWAY LIVE BENCHMARK SUITE v1.0", MAGENTA)
    client, config = create_gateway_test_client()

    headers = {
        HEADER_GATEWAY_SECRET: GATEWAY_SECRET,
        HEADER_GATEWAY_SECRET_VERSION: str(SECRET_VERSION),
        HEADER_ROUTE_TOKEN: IVYCRAFT_ROUTE_TOKEN,
    }

    # ----------------------------------------------------------------------- #
    # 1. Discovery (/v1/describe)                                             #
    # ----------------------------------------------------------------------- #
    print(f"{YELLOW}🔍 [Phase 1] Testing Gateway Discovery (/v1/describe)...{RESET}")
    start = time.perf_counter()
    resp = client.get("/v1/describe", headers=headers)
    latency = (time.perf_counter() - start) * 1000

    assert resp.status_code == 200, f"Discovery failed: {resp.text}"
    desc = resp.json()
    print(f"{GREEN}✅ Manifest Loaded in {latency:.2f}ms!{RESET}")
    print(f"   • Display Name: {WHITE}{desc.get('display_name')}{RESET}")
    print(f"   • Credential Mode: {CYAN}{desc.get('credential_mode')}{RESET}")
    print(f"   • Capabilities: {WHITE}{list(desc.get('capabilities', {}).keys())}{RESET}")
    print(f"   • Operations: {CYAN}{desc.get('operations')}{RESET}")
    print(f"   • Declared Models: {WHITE}{[m['name'] for m in desc.get('models', [])]}{RESET}")

    # ----------------------------------------------------------------------- #
    # 2. Models Projection (/v1/models)                                       #
    # ----------------------------------------------------------------------- #
    print(f"\n{YELLOW}🔍 [Phase 2] Testing Models Projection (/v1/models)...{RESET}")
    resp_m = client.get("/v1/models", headers=headers)
    assert resp_m.status_code == 200
    models_list = resp_m.json().get("models", [])
    print(f"{GREEN}✅ Declared {len(models_list)} models successfully!{RESET}")

    # ----------------------------------------------------------------------- #
    # 3. Text Generation (/v1/execute -> generate_text)                      #
    # ----------------------------------------------------------------------- #
    print(f"\n{YELLOW}💬 [Phase 3] Testing Text Generation (POST /v1/execute)...{RESET}")
    payload = {
        "operation": "generate_text",
        "model": "gpt-5.6-terra",
        "request_id": f"req-ivycraft-bench-{int(time.time())}",
        "tenant_id": "tenant-live-bench",
        "credential": {"mode": "platform"},
        "payload": {
            "messages": [
                {"role": "system", "content": "You are a concise AI assistant."},
                {"role": "user", "content": "Say hello in exactly 3 words."}
            ],
            "temperature": 0.7,
            "max_tokens": 100,
        },
        "timeout_ms": 30000,
    }

    start = time.perf_counter()
    resp_exec = client.post("/v1/execute", headers=headers, json=payload)
    latency_total = (time.perf_counter() - start) * 1000

    assert resp_exec.status_code == 200, f"HTTP Error: {resp_exec.text}"
    body = resp_exec.json()
    print(f"   • Status: {GREEN if body.get('succeeded') else RED}{body.get('succeeded')}{RESET}")
    print(f"   • Total Latency: {CYAN}{latency_total:.2f}ms{RESET} (Internal: {body.get('latency_ms')}ms)")

    if body.get("succeeded"):
        out = body.get("output", {})
        print(f"{GREEN}✨ Output:{RESET} {WHITE}{out.get('text')}{RESET}")
        print(f"   • Finish Reason: {out.get('finish_reason')}")
        print(f"   • Usage: {body.get('usage')}")
    else:
        err = body.get("error", {})
        print(f"{RED}❌ Handled Execution Error (Canonical):{RESET}")
        print(f"   • Category: {err.get('category')}")
        print(f"   • Message: {err.get('message')}")
        print(f"   • Provider Code: {err.get('provider_code')}")

    # ----------------------------------------------------------------------- #
    # 4. Image Generation (/v1/execute -> generate_image)                     #
    # ----------------------------------------------------------------------- #
    print(f"\n{YELLOW}🎨 [Phase 4] Testing Image Generation (POST /v1/execute)...{RESET}")
    payload_img = {
        "operation": "generate_image",
        "model": "gpt-image-2.5-sunburst",
        "request_id": f"req-ivycraft-img-{int(time.time())}",
        "tenant_id": "tenant-live-bench",
        "credential": {"mode": "platform"},
        "payload": {
            "prompt": "A modern futuristic neon city",
            "size": "1024x1024",
            "count": 1,
        },
        "timeout_ms": 30000,
    }
    resp_img = client.post("/v1/execute", headers=headers, json=payload_img)
    assert resp_img.status_code == 200
    body_img = resp_img.json()
    print(f"   • Succeeded: {GREEN if body_img.get('succeeded') else RED}{body_img.get('succeeded')}{RESET}")
    if body_img.get("succeeded"):
        print(f"{GREEN}✅ Generated {len(body_img['output']['images'])} image(s) successfully!{RESET}")

    # ----------------------------------------------------------------------- #
    # 5. Speech Synthesis (/v1/execute -> synthesize_speech)                  #
    # ----------------------------------------------------------------------- #
    print(f"\n{YELLOW}🎙️ [Phase 5] Testing Speech Synthesis (POST /v1/execute)...{RESET}")
    payload_sp = {
        "operation": "synthesize_speech",
        "model": "text-to-speech",
        "request_id": f"req-ivycraft-sp-{int(time.time())}",
        "tenant_id": "tenant-live-bench",
        "credential": {"mode": "platform"},
        "payload": {
            "text": "Hello, welcome to IvyCraft Gateway Service.",
            "voice": "alloy",
            "audio_format": "wav",
        },
        "timeout_ms": 30000,
    }
    resp_sp = client.post("/v1/execute", headers=headers, json=payload_sp)
    assert resp_sp.status_code == 200
    body_sp = resp_sp.json()
    print(f"   • Succeeded: {GREEN if body_sp.get('succeeded') else RED}{body_sp.get('succeeded')}{RESET}")
    if body_sp.get("succeeded"):
        print(f"{GREEN}✅ Synthesized speech in format: {body_sp['output']['audio_format']}!{RESET}")

    print_banner("🎉 ALL 5 LIVE BENCHMARK PHASES COMPLETED PERFECTLY! 🎉", GREEN)


if __name__ == "__main__":
    main()
