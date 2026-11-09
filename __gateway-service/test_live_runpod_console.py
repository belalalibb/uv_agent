# -*- coding: utf-8 -*-
"""Live Integration Test for RunPod Console Assistant Gateway Provider.

Executes a live call through the Gateway layer (ProviderContext -> Facade Adapter -> Upstream)
against real RunPod Console Assistant stream endpoints.
"""

from __future__ import annotations

import asyncio
import sys

# Ensure UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from gateway.contracts import (
    CredentialMode,
    GatewayOperation,
    ProviderContext,
)
from providers.runpod_console.adapter import generate_text


async def run_live_test():
    print("=" * 70)
    print("🚀 [Live Test] RunPod Console Assistant Gateway Provider Integration Test")
    print("=" * 70)

    ctx = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model="runpod-console-gpt4",
        request_id="live-runpod-console-01",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={
            "messages": [
                {
                    "role": "user",
                    "content": "عرف نفسك في سطر واحد بالمصري وقل لي ما هي طبيعة دورك في RunPod.",
                }
            ]
        },
    )

    print("\n📡 Invoking RunPod Console Provider Facade...")
    res = await generate_text(ctx)

    if res.succeeded:
        print("✅ SUCCESS! Facade Returned Canonical Output:")
        print(f"   • Text: {res.output.get('text', '').strip()}")
        print(f"   • Finish Reason: {res.output.get('finish_reason')}")
        if res.usage:
            print(f"   • Usage: input_tokens={res.usage.input_tokens}, output_tokens={res.usage.output_tokens}, units={res.usage.units}")
    else:
        print(f"❌ FAILED! Error Category: {res.error.category}")
        print(f"   • Message: {res.error.message}")
        print(f"   • Retryable: {res.error.retryable}")
        print(f"   • Provider Code: {res.error.provider_code}")

    assert res.succeeded is True, "Live test must succeed!"

    print("\n" + "=" * 70)
    print("🚀 [Live Test 2] analyze_vision with Real In-Memory Image")
    print("=" * 70)

    # 1x1 green PNG base64
    green_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    vision_ctx = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        model="runpod-console-vision",
        request_id="live-runpod-console-vision-01",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={
            "instruction": "ما هو اللون السائد في هذه الصورة؟ جاوب في كلمة واحدة أو سطر واحد.",
            "image_b64": green_png_b64,
            "image_format": "png",
        },
    )

    from providers.runpod_console.adapter import analyze_vision

    print("📡 Invoking RunPod Console analyze_vision Facade...")
    vision_res = await analyze_vision(vision_ctx)

    if vision_res.succeeded:
        print("✅ SUCCESS! Vision Returned Canonical Output:")
        print(f"   • Text: {vision_res.output.get('text', '').strip()}")
    else:
        print(f"❌ FAILED Vision! Error: {vision_res.error.message}")

    assert vision_res.succeeded is True, "Vision live test must succeed!"

    print("\n" + "=" * 70)
    print("🎉 ALL LIVE INTEGRATION CHECKS (TEXT + VISION) COMPLETED SUCCESSFULLY")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_live_test())

