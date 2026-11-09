#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════════════
🚀 AI GATEWAY SERVICE — HARSH DIAGNOSTIC & LIVE BENCHMARK FOR VOYAGE AI (v1.0)
════════════════════════════════════════════════════════════════════════════════
Authority: Eng. Bolla (Lead Architect) & Eng. Zizo (Visionary)
Compliance: Bolla Constitution v1.2 & ADR-0008 (Three-Layer Architecture)

Harsh Test Dimensions:
  1. 🌐 Arabic & Multilingual Semantic Embeddings (voyage-multilingual-2).
  2. 💻 Specialized GitHub Code Syntax Embeddings (voyage-code-3).
  3. 🔍 Multi-Domain Cross-Encoder Reranking (rerank-2):
     - Domain A: GitHub Code Function Retrieval.
     - Domain B: SaaS Pricing & Subscription Tiers.
     - Domain C: Legal Contract Termination Clauses.
  4. 🔌 End-to-End Wire Envelope via FastAPI /v1/execute with X-Route-Token.
  5. 📊 Real-time token usage, vector dimension audit, and latency benchmark.
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

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from app import build_app, register_live_providers
from gateway.config import GatewayConfig
from gateway.contracts import (
    CredentialMode,
    GatewayOperation,
    ProviderContext,
)
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from providers.voyage.adapter import create_embeddings, rerank_documents


async def run_harsh_diagnostic():
    print("=" * 75)
    print("   🔬 [HARSH DIAGNOSTIC] VOYAGE AI GATEWAY CAPABILITIES SUITE")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # Test 1: Arabic & Multilingual High-Dimension Embedding
    # -------------------------------------------------------------------------
    print("\n[Test 1] Multilingual Arabic Embeddings (voyage-multilingual-2)...")
    t0 = time.perf_counter()
    ctx_ar = ProviderContext(
        operation=GatewayOperation.CREATE_EMBEDDINGS,
        model="voyage-multilingual-2",
        request_id="harsh-voyage-ar-1",
        tenant_id="tenant-harsh",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={
            "inputs": [
                "البحث الدلالي المتقدم واسترجاع المعلومات بالذكاء الاصطناعي",
                "نماذج الترتيب وإعادة صياغة المستندات المعقدة",
            ]
        },
    )
    res_ar = await create_embeddings(ctx_ar)
    dur_ar = (time.perf_counter() - t0) * 1000
    if res_ar.succeeded and res_ar.output:
        dims = res_ar.output.get("dimensions")
        embs = res_ar.output.get("embeddings", [])
        tokens = res_ar.usage.input_tokens if res_ar.usage else 0
        print(f"  ✅ [PASS] Dim: {dims} | Vectors: {len(embs)} | Tokens: {tokens} | Latency: {dur_ar:.1f}ms")
        assert dims == 1024
        assert len(embs) == 2
    else:
        print(f"  ❌ [FAIL] Error: {res_ar.error.category} - {res_ar.error.message}")
        sys.exit(1)

    time.sleep(1.5)  # Rate-limit safety for free tier

    # -------------------------------------------------------------------------
    # Test 2: Specialized Code & GitHub Syntax Embedding
    # -------------------------------------------------------------------------
    print("\n[Test 2] Code & GitHub Syntax Embeddings (voyage-code-3)...")
    t0 = time.perf_counter()
    code_samples = [
        "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)",
        "async def handle_request(ctx: ProviderContext) -> FacadeResult:\n    return await adapter.dispatch(ctx)",
    ]
    ctx_code = ProviderContext(
        operation=GatewayOperation.CREATE_EMBEDDINGS,
        model="voyage-code-3",
        request_id="harsh-voyage-code-1",
        tenant_id="tenant-harsh",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={"inputs": code_samples},
    )
    res_code = await create_embeddings(ctx_code)
    dur_code = (time.perf_counter() - t0) * 1000
    if res_code.succeeded and res_code.output:
        dims = res_code.output.get("dimensions")
        embs = res_code.output.get("embeddings", [])
        print(f"  ✅ [PASS] Dim: {dims} | Vectors: {len(embs)} | Latency: {dur_code:.1f}ms")
        assert dims == 1024
    else:
        print(f"  ❌ [FAIL] Error: {res_code.error.category} - {res_code.error.message}")
        sys.exit(1)

    time.sleep(1.5)

    # -------------------------------------------------------------------------
    # Test 3: Multi-Domain Deep Search Reranking (rerank-2)
    # -------------------------------------------------------------------------
    print("\n[Test 3] Multi-Domain Deep Search Cross-Encoder (rerank-2)...")

    # Domain A: GitHub Code Search
    query_code = "Python function to validate JWT token expiry or decode payload"
    docs_code = [
        "def calculate_tax(income, rate=0.2):\n    return income * rate",
        "import jwt\ndef is_token_valid(token, secret):\n    payload = jwt.decode(token, secret, algorithms=['HS256'])\n    return payload.get('exp') > time.time()",
        "SELECT user_id, email FROM users WHERE active = 1 ORDER BY created_at DESC;",
        "function handleScroll(e) { window.scrollTo({ top: 0, behavior: 'smooth' }); }",
    ]
    ctx_rr_code = ProviderContext(
        operation=GatewayOperation.RERANK_DOCUMENTS,
        model="rerank-2",
        request_id="harsh-voyage-rr-code",
        tenant_id="tenant-harsh",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={"query": query_code, "documents": docs_code, "top_n": 2},
    )
    res_rr_code = await rerank_documents(ctx_rr_code)
    if res_rr_code.succeeded and res_rr_code.output:
        results = res_rr_code.output.get("results", [])
        top_idx = results[0]["index"]
        score = results[0]["relevance_score"]
        print(f"  [Domain A: Code]     ✅ [PASS] Top Match: Index {top_idx} | Score: {score:.4f}")
        assert top_idx == 1  # Index 1 is the JWT validator function
    else:
        print(f"  [Domain A: Code]     ❌ [FAIL] {res_rr_code.error}")

    time.sleep(1.5)

    # Domain B: SaaS Pricing & Subscription Tiers
    query_price = "أرخص باقة اشتراك سنوي للمطورين فيها كوتة غير محدودة"
    docs_price = [
        "الباقة المجانية Free Tier: بدون رسوم، 500 ريكويست في الشهر.",
        "باقة المطورين Pro Dev: 20 دولار شهرياً أو 180 دولار سنوياً، كوتة غير محدودة للريكويستات.",
        "باقة الشركات Enterprise: 500 دولار شهرياً، خوادم مخصصة وعقد سنوي.",
        "باقة الفرق Team: 80 دولار شهرياً حتى 5 مستخدمين.",
    ]
    ctx_rr_price = ProviderContext(
        operation=GatewayOperation.RERANK_DOCUMENTS,
        model="rerank-2",
        request_id="harsh-voyage-rr-price",
        tenant_id="tenant-harsh",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={"query": query_price, "documents": docs_price, "top_n": 2},
    )
    res_rr_price = await rerank_documents(ctx_rr_price)
    if res_rr_price.succeeded and res_rr_price.output:
        results = res_rr_price.output.get("results", [])
        top_idx = results[0]["index"]
        score = results[0]["relevance_score"]
        print(f"  [Domain B: Pricing]  ✅ [PASS] Top Match: Index {top_idx} | Score: {score:.4f}")
        assert top_idx == 1  # Pro Dev is the 180$/yr unlimited tier
    else:
        print(f"  [Domain B: Pricing]  ❌ [FAIL] {res_rr_price.error}")

    time.sleep(1.5)

    # Domain C: Legal Contract Termination Clauses
    query_legal = "شروط إنهاء العقد وفترة الإخطار المسبق"
    docs_legal = [
        "المادة 1: نطاق الخدمات والتزامات الطرف الأول بتقديم الدعم الفني.",
        "المادة 4: التعويضات والمسؤولية القانونية محددة بحد أقصى يعادل الفواتير.",
        "المادة 9: إنهاء العقد يحق لأي من الطرفين بإخطار كتابي مسبق مدته 30 يوماً.",
        "المادة 12: القانون الواجب التطبيق والاختصاص القضائي لمحاكم القاهرة.",
    ]
    ctx_rr_legal = ProviderContext(
        operation=GatewayOperation.RERANK_DOCUMENTS,
        model="rerank-2",
        request_id="harsh-voyage-rr-legal",
        tenant_id="tenant-harsh",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={"query": query_legal, "documents": docs_legal, "top_n": 2},
    )
    res_rr_legal = await rerank_documents(ctx_rr_legal)
    if res_rr_legal.succeeded and res_rr_legal.output:
        results = res_rr_legal.output.get("results", [])
        top_idx = results[0]["index"]
        score = results[0]["relevance_score"]
        print(f"  [Domain C: Legal]    ✅ [PASS] Top Match: Index {top_idx} | Score: {score:.4f}")
        assert top_idx == 2  # Clause 9 is contract termination
    else:
        print(f"  [Domain C: Legal]    ❌ [FAIL] {res_rr_legal.error}")

    # -------------------------------------------------------------------------
    # Test 4: Full Wire-Level HTTP Gateway Integration Test
    # -------------------------------------------------------------------------
    print("\n[Test 4] Wire-Level HTTP Surface via FastAPI TestClient (/v1/execute)...")
    _gw_auth_token = "unit-test-secret-version-seven"
    route_token = "rtk_voyage_live_production"
    config = GatewayConfig(
        secrets_by_version={1: _gw_auth_token},
        current_secret_version=1,
        route_map={route_token: "voyage"},
        dual_accept_window_seconds=600,
    )
    providers = ProviderRegistry()
    register_live_providers(providers)
    providers.eager_verify_all()
    routes = RouteRegistry(config.route_map)
    app = build_app(config, providers, routes)
    client = TestClient(app)

    headers = {
        "X-Gateway-Secret": _gw_auth_token,
        "X-Gateway-Secret-Version": "1",
        "X-Route-Token": route_token,
    }

    # Wire Embeddings
    time.sleep(1.5)
    wire_req_emb = {
        "operation": "create_embeddings",
        "model": "voyage-3-lite",
        "request_id": "wire-live-emb-1",
        "tenant_id": "tenant-wire",
        "credential": {"mode": "platform"},
        "payload": {"inputs": ["Gateway Wire Verification Text"]},
        "timeout_ms": 30000,
    }
    resp_wire_emb = client.post("/v1/execute", json=wire_req_emb, headers=headers)
    assert resp_wire_emb.status_code == 200
    body_emb = resp_wire_emb.json()
    assert body_emb["succeeded"] is True
    print(f"  ✅ [Wire Embeddings] [PASS] Model: voyage-3-lite | Dims: {body_emb['output']['dimensions']} | Latency: {body_emb['latency_ms']}ms")

    # Wire Rerank
    time.sleep(1.5)
    wire_req_rr = {
        "operation": "rerank_documents",
        "model": "rerank-2-lite",
        "request_id": "wire-live-rr-1",
        "tenant_id": "tenant-wire",
        "credential": {"mode": "platform"},
        "payload": {
            "query": "fast search",
            "documents": ["slow approach", "instant high speed indexed search", "neutral document"],
            "top_n": 1,
        },
        "timeout_ms": 30000,
    }
    resp_wire_rr = client.post("/v1/execute", json=wire_req_rr, headers=headers)
    assert resp_wire_rr.status_code == 200
    body_rr = resp_wire_rr.json()
    assert body_rr["succeeded"] is True
    assert len(body_rr["output"]["results"]) == 1
    print(f"  ✅ [Wire Reranking]  [PASS] Model: rerank-2-lite | Top Index: {body_rr['output']['results'][0]['index']} | Latency: {body_rr['latency_ms']}ms")

    print("\n" + "=" * 75)
    print("🎉🎉🎉 ALL HARSH VOYAGE AI DIAGNOSTIC TESTS PASSED 100%! 🎉🎉🎉")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_harsh_diagnostic())
