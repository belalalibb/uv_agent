#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Verification Test for Freebuff Gateway Adapter
==================================================
Tests end-to-end integration:
ProviderContext -> Freebuff Adapter -> Freebuff _core -> Live Freebuff SSE API -> FacadeResult.
"""

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

GATEWAY_DIR = Path(__file__).resolve().parent
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from gateway.contracts import CredentialMode, GatewayOperation, ProviderContext
from providers.freebuff.adapter import generate_text
from providers.freebuff import DEFINITION, HANDLERS, _core


async def main():
    print("=" * 70)
    print("🚀 بدء الاختبار الميداني الحي لمزود Freebuff داخل الـ Gateway")
    print("=" * 70)

    # 1. فحص صحة الجلسة
    print("\n1. فحص صحة الجلسة (Health Check)...")
    is_healthy = _core.check_health()
    print(f"   [+] Session Health: {'✅ نشطة ومصرح بها (200 OK)' if is_healthy else '❌ غير مصرح'}")
    assert is_healthy, "Freebuff session is not healthy"

    # 2. فحص مطابقة عقد البوابة
    print("\n2. فحص مطابقة عقد البوابة (Definition & Handlers)...")
    print(f"   [+] Display Name: {DEFINITION['display_name']}")
    print(f"   [+] Handlers: {list(HANDLERS.keys())}")

    # 3. إرسال طلب محادثة حقيقي عبر الـ Adapter
    print("\n3. اختبار توليد نص حي (Live Inference via Adapter)...")
    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        credential_mode=CredentialMode.PLATFORM,
        model="glm-5.3-flash",
        tenant_id="test-tenant",
        payload={
            "messages": [
                {"role": "user", "content": "أهلاً بك! في سطر واحد، عرّف عن نفسك كوكيل ذكاء اصطناعي."}
            ],
            "model": "glm-5.3-flash",
        },
        timeout_ms=60000,
        request_id="live-test-001",
    )

    result = await generate_text(ctx)
    print(f"   [+] النجاح (Succeeded): {result.succeeded}")

    if result.succeeded:
        out = result.output or {}
        print(f"   [+] نص الإجابة (Text): {out.get('text', '').strip()}")
        if out.get("reasoning"):
            print(f"   [+] تدفق التفكير (Reasoning): {out['reasoning'][:120]}...")
        print(f"   [+] الموديل المستخدم: {out.get('model')}")
        print(f"   [+] استمرار الجلسة (Thread ID): {out.get('session_id')}")
        print(f"   [+] وحدات الاستخدام (Usage): {result.usage}")
        print("\n🎉 الاختبار الميداني الحي نجح بنسبة 100%!")
    else:
        print(f"   [-] فشل الطلب! تفاصيل الخطأ: {result.error}")
        sys.exit(1)

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
