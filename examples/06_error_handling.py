"""Example 06: Comprehensive Typed Error Handling.

Demonstrates catching the 12 Canonical Error Categories mapped by the Gateway
into strongly-typed Python exceptions.
"""

import asyncio
import sys
from pathlib import Path

# Add external_platform_client to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import (
    AuthExpiredError,
    BadRequestError,
    ChatMessage,
    ContentRejectedError,
    GatewayClient,
    GatewayConfig,
    GatewayError,
    InvalidCredentialError,
    ModelUnavailableError,
    QuotaExceededError,
    RateLimitedError,
    RouteNotFoundError,
    SmartRouter,
    TimeoutError,
    UnsupportedCapabilityError,
)


async def main() -> None:
    config = GatewayConfig(
        base_url="http://127.0.0.1:8800",
        gateway_secret="live-demo-secret-key-bolla-zizo",
        secret_version=1,
    )
    router = SmartRouter({
        "syntx": "rtk_syntx_production_live_session",
    })

    async with GatewayClient(config=config, router=router) as client:
        # Scenario A: Trying an unknown route token
        print("\n--- سيناريو 1: استدعاء توكن مسار غير موجود (Anti-Enumeration 404) ---")
        try:
            await client.describe(route_token="invalid_token_123")
        except RouteNotFoundError as exc:
            print(f"✓ تم التقاط خطأ المسار بدقة: {exc}")
            print(f"  HTTP Status: {exc.http_status}, Category: {exc.category}")

        # Scenario B: Calling a non-vision model with vision instruction
        print("\n--- سيناريو 2: إرسال صورة لموديل نصي بحت (Non-Vision Guard) ---")
        try:
            await client.analyze_vision(
                route_token="syntx",
                model="grok-4.6",  # Pure text model
                image="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII=",
                instruction="ما هذا؟",
            )
        except UnsupportedCapabilityError as exc:
            print(f"✓ تم التقاط عدم دعم الميزة بنجاح: {exc}")
            print(f"  Category: {exc.category}, Message: {exc.message}")
        except GatewayError as exc:
            print(f"خطأ جيت واي عام: {exc}")

        # Scenario C: Simulating Rate Limit handling with retry_after_ms
        print("\n--- سيناريو 3: معالجة تجاوز معدل الطلبات (Rate Limiting) ---")
        try:
            # If an upstream provider returns 429, it raises RateLimitedError
            raise RateLimitedError(
                category="rate_limited",
                message="Upstream throttled",
                retryable=True,
                retry_after_ms=3500,
                provider_code="429",
            )
        except RateLimitedError as exc:
            print(f"✓ تم اكتشاف Rate Limit! إعادة المحاولة ممكنة: {exc.retryable}")
            print(f"  يجب الانتظار لمدة: {exc.retry_after_ms} مللي ثانية")


if __name__ == "__main__":
    asyncio.run(main())

