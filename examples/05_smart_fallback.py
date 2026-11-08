"""Example 05: Smart Router Fallback — Automatic Failover for High Availability.

Since the Gateway enforces zero retries and rigid 1:1 token routing, this
example demonstrates how the external platform client transparently fails
over from Primary provider to Secondary providers if rate limited or unavailable.
"""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import (
    ChatMessage,
    GatewayClient,
    GatewayConfig,
    GatewayError,
    SmartRouter,
)


async def main() -> None:
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )

    router = SmartRouter({
        "groq": "rtk_groq_production",
        "syntx": "rtk_syntx_production_live_session",
        "youmind": "rtk_youmind_production",
    })

    # Register a fallback group:
    # 1st try: groq (super fast)
    # 2nd try (fallback): syntx (high-capacity)
    # 3rd try (fallback): youmind (knowledge/reasoning)
    router.register_group(
        group_name="high_availability_chat",
        primary="groq",
        fallbacks=["syntx", "youmind"],
    )

    async with GatewayClient(config=config, router=router) as client:
        print("Sending request to Fallback Group 'high_availability_chat'...")

        messages = [
            ChatMessage(role="user", content="اشرح الفرق بين الـ SQL والـ NoSQL باختصار شديد."),
        ]

        try:
            # We pass the group_name as the route_token parameter!
            result = await client.generate_text(
                route_token="high_availability_chat",
                model="llama-3.3-70b-versatile",
                messages=messages,
                timeout_ms=30000,
            )
            print("\n✓ النجاح عبر التوجيه الذكي!")
            print("الرد:", result.output.text)
            print(f"السرعة: {result.latency_ms} ms")
        except GatewayError as exc:
            print(f"❌ فشل جميع المزودين في السلسلة: [{exc.category}] {exc.message}")


if __name__ == "__main__":
    asyncio.run(main())

