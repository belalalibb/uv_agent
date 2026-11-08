"""Example 03: Multimodal Vision Analysis (POST /v1/execute -> analyze_vision)."""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import GatewayClient, GatewayConfig, SmartRouter

# 1x1 Transparent PNG Base64 for testing
SAMPLE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="
)


async def main() -> None:
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )
    router = SmartRouter({
        "syntx": "rtk_syntx_production_live_session",
        "deepai": "rtk_deepai_production",
    })

    async with GatewayClient(config=config, router=router) as client:
        print("Sending Vision Analysis request to Gateway...")

        result = await client.analyze_vision(
            route_token="syntx",
            model="gemini-2.5-flash",
            image=SAMPLE_PNG_B64,
            instruction="صف محتويات هذه الصورة بالتفصيل.",
            image_format="png",
            timeout_ms=45000,
        )

        print("\n=== Vision Analysis Result ===")
        print(result.output.text)
        print(f"Latency: {result.latency_ms} ms")
        if result.usage:
            print(f"Usage: {result.usage.input_tokens} in / {result.usage.output_tokens} out")


if __name__ == "__main__":
    asyncio.run(main())

