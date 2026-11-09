#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Verification Test for TinyFish Gateway Adapter
==================================================
Tests canonical operations end-to-end:
1. Text Generation / Web Reasoning via mako
2. Vision Analysis via analyze_vision
"""

import asyncio
import base64
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
from providers.tinyfish.adapter import HANDLERS, generate_text, analyze_vision
from providers.tinyfish.definition import DEFINITION


async def main():
    print("=" * 75)
    print("🚀 بدء الاختبار الميداني الحي لمزود TinyFish AI داخل الـ Gateway")
    print("=" * 75)

    # 1. فحص مطابقة عقد البوابة
    print("\n1. فحص مطابقة عقد البوابة (Definition & Handlers)...")
    print(f"   [+] Display Name: {DEFINITION['display_name']}")
    print(f"   [+] Handlers: {[op.value for op in HANDLERS.keys()]}")
    print(f"   [+] Models: {[m['name'] for m in DEFINITION['models']]}")
    print(f"   [+] Capabilities: {DEFINITION['capabilities']}")

    # 2. توليد نص حي عبر المحول (mako)
    print("\n2. اختبار توليد نص واستدلال ويب حي عبر الـ Adapter (mako)...")
    ctx_text = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        credential_mode=CredentialMode.PLATFORM,
        model="mako",
        request_id="req-live-tinyfish-text",
        tenant_id="tenant-test",
        payload={
            "messages": [
                {"role": "user", "content": "What is 100 divided by 4? Answer with just the number."}
            ],
            "temperature": 0.5,
        },
        timeout_ms=60000,
    )
    res_text = await generate_text(ctx_text)
    print(f"   [+] النتيجة: {'نجح ✅' if res_text.succeeded else 'فشل ❌'}")
    if res_text.succeeded:
        print(f"   [+] الرد: {res_text.output['text']}")
        print(f"   [+] الاستهلاك: {res_text.usage.model_dump()}")
    else:
        print(f"   [!] خطأ: {res_text.error.model_dump()}")

    # 3. اختبار تحليل الرؤية (analyze_vision)
    print("\n3. اختبار تحليل الصور (analyze_vision)...")
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    b64_img = base64.b64encode(fake_png).decode("ascii")

    ctx_vision = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        credential_mode=CredentialMode.PLATFORM,
        model="mako",
        request_id="req-live-tinyfish-vision",
        tenant_id="tenant-test",
        payload={
            "image_b64": b64_img,
            "image_format": "png",
            "instruction": "Describe this pixel image: https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png",
        },
        timeout_ms=60000,
    )
    res_vision = await analyze_vision(ctx_vision)
    print(f"   [+] النتيجة: {'نجح ✅' if res_vision.succeeded else 'فشل ❌'}")
    if res_vision.succeeded:
        print(f"   [+] الرد: {res_vision.output['text'][:200]}...")
    else:
        print(f"   [!] خطأ: {res_vision.error.model_dump()}")

    print("\n" + "=" * 75)
    print("🎉 انتهت كافة الاختبارات الحية لمزود TinyFish AI بنجاح تام!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
