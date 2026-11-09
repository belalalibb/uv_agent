"""Live Integration Test for Upstage AI Gateway Provider.

Executes a live call through the Gateway layer against real Upstage Studio endpoints.
Tests models: auto, solar-pro4, solar-docvision, gpt-5.4-openai.
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
from providers.upstage.adapter import generate_text
from providers.upstage._core import AVAILABLE_MODELS


async def run_live_test():
    print("=" * 60)
    print("🚀 [Live Test] Upstage AI Provider Integration Test")
    print("=" * 60)

    test_models = ["auto", "solar-pro4", "solar-docvision", "gpt-5.4-openai"]

    for model in test_models:
        print(f"\n--- Testing Model: [{model}] ---")
        ctx = ProviderContext(
            operation=GatewayOperation.GENERATE_TEXT,
            model=model,
            request_id=f"live-upstage-{model}",
            tenant_id="tenant-test",
            credential_mode=CredentialMode.PLATFORM,
            timeout_ms=45000,
            payload={
                "messages": [
                    {
                        "role": "user",
                        "content": "عرف نفسك في سطر واحد فقط بالمصري واذكر اسمك",
                    }
                ]
            },
        )

        res = await generate_text(ctx)
        if res.succeeded:
            print(f"✅ SUCCESS! Output: {res.output.get('text', '').strip()}")
            if res.usage:
                print(f"   Usage: input={res.usage.input_tokens}, output={res.usage.output_tokens}")
        else:
            print(f"❌ FAILED! Category: {res.error.category} - {res.error.message}")

    print("\n" + "=" * 60)
    print("👁️ [Live Test] Upstage analyze_vision Integration Test")
    print("=" * 60)
    from providers.upstage.adapter import analyze_vision

    tiny_png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAEklEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    ctx_vis = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        model="solar-docvision",
        request_id="live-upstage-vision-test",
        tenant_id="tenant-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=45000,
        payload={
            "image_b64": tiny_png_b64,
            "image_format": "png",
            "instruction": "قولي لون الصورة دي إيه باختصار شديد بالمصري",
        },
    )

    res_vis = await analyze_vision(ctx_vis)
    if res_vis.succeeded:
        print(f"✅ VISION SUCCESS! Output: {res_vis.output.get('text', '').strip()}")
        if res_vis.usage:
            print(f"   Usage: input={res_vis.usage.input_tokens}, output={res_vis.usage.output_tokens}")
    else:
        print(f"❌ VISION FAILED! Category: {res_vis.error.category} - {res_vis.error.message}")

    print("\n" + "=" * 60)
    print("🎉 All Upstage live tests finished!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_live_test())
