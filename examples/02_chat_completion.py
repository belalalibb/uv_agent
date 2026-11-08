"""Example 02: Chat Completion with Usage and Latency Tracking."""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import ChatMessage, GatewayClient, GatewayConfig, SmartRouter


async def main() -> None:
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )
    router = SmartRouter({
        "syntx": "rtk_syntx_production_live_session",
        "groq": "rtk_groq_production",
    })

    async with GatewayClient(config=config, router=router) as client:
        print("Sending chat request to Gateway (Syntx AI -> deepseek-v3)...")

        messages = [
            ChatMessage(role="system", content="أنت مساعد تقني ذكي ودقيق ومختصر."),
            ChatMessage(role="user", content="ما هي معمارية الـ Microservices في 3 نقاط محددة؟"),
        ]

        result = await client.generate_text(
            route_token="syntx",
            model="deepseek-v3",
            messages=messages,
            temperature=0.7,
            timeout_ms=60000,
        )

        print("\n=== استجابة النموذج ===")
        print(result.output.text)
        print(f"Finish Reason: {result.output.finish_reason}")
        print("\n=== إحصائيات الاستهلاك والسرعة ===")
        print(f"Latency: {result.latency_ms} ms")
        if result.usage:
            print(f"Input Tokens : {result.usage.input_tokens}")
            print(f"Output Tokens: {result.usage.output_tokens}")
            print(f"Units Consumed: {result.usage.units}")


if __name__ == "__main__":
    asyncio.run(main())

