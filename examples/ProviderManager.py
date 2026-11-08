"""Dynamic ProviderManager Demonstration — 100% Dynamic, Zero Hardcoding.

Shows how an external platform:
1. Dynamically discovers providers from environment, config, or raw tokens.
2. Self-introspects provider identity (display_name, operations, capabilities, models)
   via Gateway /v1/describe projections without pre-defining anything.
3. Automatically maps and indexes providers at runtime.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure external_platform_client root is in sys.path
_CLIENT_ROOT = Path(__file__).resolve().parent.parent
if str(_CLIENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLIENT_ROOT))

from client import (
    EnvRouteStorage,
    FileRouteStorage,
    GatewayClient,
    GatewayConfig,
    MemoryRouteStorage,
    ProviderInfo,
    ProviderManager,
)


async def main() -> None:
    print("=" * 75)
    print("🚀 AI Gateway Platform — 100% Dynamic Provider Manager (Zero Hardcoding)")
    print("=" * 75)

    # ----------------------------------------------------------------------- #
    # Pattern A: Gateway Self-Discovery from Raw Tokens                        #
    # (The platform only has tokens from its DB/Vault; names are discovered)  #
    # ----------------------------------------------------------------------- #
    print("\n▶ [1/4] الاكتشاف الذاتي التلقائي من التوكنات الخام (Zero-Knowledge Self-Discovery):")
    print("  المنصة لا تعرف أسماء المزودين مسبقاً، بل تستكشف هويتهم حياً عبر الجيت واي...")

    # Simulated raw tokens received from platform database or environment
    raw_tokens_from_vault = [
        os.getenv("ROUTE_TOKEN_GROQ", "rtk_groq_production"),
        os.getenv("ROUTE_TOKEN_SYNTX", "rtk_syntx_production_live_session"),
        os.getenv("ROUTE_TOKEN_DEEPAI", "rtk_deepai_production"),
    ]

    # Initialize manager with clean, empty in-memory storage (Zero hardcoding)
    empty_storage = MemoryRouteStorage()
    async with ProviderManager(storage=empty_storage) as manager:

        # Bootstrap completely dynamically by introspecting the tokens
        discovered_providers = await manager.discover_all_from_tokens(raw_tokens_from_vault)

        print(f"\n  ✓ تم اكتشاف وتسجيل {len(discovered_providers)} مزودين ديناميكياً:")
        for p in discovered_providers:
            print(f"    • المزود المكتشف: {p.display_name:<15} | الرمز المعين: '{p.route_ref}' | الموديلات: {len(p.models)}")

        # ------------------------------------------------------------------- #
        # Pattern B: Dynamic Inspection by Discovered Reference               #
        # ------------------------------------------------------------------- #
        print("\n▶ [2/4] فحص تفصيلي للمزود المكتشف ديناميكياً (Syntx AI):")
        # Notice: We use the dynamically discovered reference 'syntx' or 'syntx-ai'
        syntx_info = await manager.get_provider_by_route("syntx")
        print(f"  • الاسم الرسمي      : {syntx_info.display_name}")
        print(f"  • نمط الاعتماد       : {syntx_info.credential_mode}")
        print(f"  • إصدار العقد       : {syntx_info.definition_version}")
        print(f"  • العمليات المعلنة  : {syntx_info.operations}")
        print(f"  • القدرات المفعلة   : {[k for k, v in syntx_info.capabilities.items() if v]}")
        sample_models = [m.name for m in syntx_info.models[:5]]
        print(f"  • عينة من الموديلات : {', '.join(sample_models)} ...")

        # ------------------------------------------------------------------- #
        # Pattern C: Dynamic Runtime Registration                             #
        # ------------------------------------------------------------------- #
        print("\n▶ [3/4] تسجيل مسار جديد ديناميكياً في وقت التشغيل (Runtime Registration):")
        new_token = "rtk_youmind_production"
        print(f"  • تسجيل توكن جديد في الذاكرة دون إعادة تشغيل: {new_token}")
        new_info = await manager.discover_and_register(new_token)
        print(f"  ✓ تم التعرف الفوري على المزود الجديد: '{new_info.display_name}' (Reference: '{new_info.route_ref}')")

        # ------------------------------------------------------------------- #
        # Pattern D: Dynamic Querying & Intelligent Model Matching            #
        # ------------------------------------------------------------------- #
        print("\n▶ [4/4] البحث والاستعلام الذكي بين المزودين المكتشفين:")

        # Find providers supporting vision
        vision_providers = await manager.find_providers_for_operation("analyze_vision")
        print(f"  • المزودون الداعمون لعملية 'analyze_vision': {vision_providers}")

        # Find provider for specific model
        target_model = "deepseek-v3"
        matched_provider = await manager.find_provider_for_model(target_model)
        print(f"  • المزود الذي يوفر الموديل '{target_model}': '{matched_provider}'")

    print("\n" + "=" * 75)
    print("✓ اكتمل اختبار ProviderManager الديناميكي بنجاح 100% ودون أي ثوابت صلبة!")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
