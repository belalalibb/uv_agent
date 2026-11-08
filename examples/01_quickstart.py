"""Example 01: Quickstart — Health check, Provider Discovery, and Model Listing."""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import GatewayClient, GatewayConfig, SmartRouter


async def main() -> None:
    # 1. Initialize configuration with Gateway Secret and Route Tokens
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )

    # 2. Setup Smart Router with friendly provider aliases
    router = SmartRouter({
        "groq": "rtk_groq_production",
        "syntx": "rtk_syntx_production_live_session",
        "deepai": "rtk_deepai_production",
    })

    async with GatewayClient(config=config, router=router) as client:
        # A. Gateway Process Liveness Check
        print("Checking Gateway Liveness (/healthz)...")
        is_live = await client.healthz()
        print(f"Gateway Liveness Status: {'ONLINE' if is_live else 'OFFLINE'}\n")

        # B. Discover Provider Capabilities (/v1/describe)
        print("Discovering Syntx AI capabilities (/v1/describe)...")
        manifest = await client.describe(route_token="syntx")
        print(f"Provider Display Name: {manifest.display_name}")
        print(f"Credential Mode      : {manifest.credential_mode}")
        print(f"Declared Operations  : {manifest.operations}")
        print(f"Supported Capabilities: {list(manifest.capabilities.keys())}")
        print(f"Total Declared Models : {len(manifest.models)}\n")

        # C. Query Provider Model List (/v1/models)
        print("Listing Models for Groq (/v1/models)...")
        models = await client.list_models(route_token="groq")
        for m in models[:5]:
            print(f" - Model: {m.name:<30} (Context Window: {m.context_window})")


if __name__ == "__main__":
    asyncio.run(main())

