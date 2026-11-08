"""Unit tests for the External Platform Client SDK."""

import pytest
import httpx
from client import (
    AudioOutput,
    ChatMessage,
    EmbeddingsOutput,
    GatewayClient,
    GatewayConfig,
    GatewayError,
    ImageOutput,
    RateLimitedError,
    RerankOutput,
    RouteNotFoundError,
    SmartRouter,
    SpeechOutput,
    TextOutput,
    VisionOutput,
)


@pytest.mark.asyncio
async def test_client_healthz():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/healthz"
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        config = GatewayConfig(base_url="http://test-gw", gateway_secret="test-secret-123456")
        client = GatewayClient(config=config, http_client=mock_http)
        assert await client.healthz() is True


@pytest.mark.asyncio
async def test_client_generate_text_success():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/execute"
        assert request.headers["X-Gateway-Secret"] == "test-secret-123456"
        assert request.headers["X-Route-Token"] == "rtk_groq"
        return httpx.Response(
            200,
            json={
                "succeeded": True,
                "output": {"text": "مرحبا بك من العميل الموحد!", "finish_reason": "stop"},
                "usage": {"input_tokens": 10, "output_tokens": 8, "units": 1},
                "latency_ms": 250,
                "error": None,
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        config = GatewayConfig(base_url="http://test-gw", gateway_secret="test-secret-123456")
        client = GatewayClient(config=config, http_client=mock_http)

        res = await client.generate_text(
            route_token="rtk_groq",
            model="llama-3.3-70b-versatile",
            messages=[ChatMessage(role="user", content="مرحبا")],
        )

        assert res.succeeded is True
        assert isinstance(res.output, TextOutput)
        assert res.output.text == "مرحبا بك من العميل الموحد!"
        assert res.usage.input_tokens == 10
        assert res.latency_ms == 250


@pytest.mark.asyncio
async def test_client_rate_limited_translation():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "succeeded": False,
                "output": None,
                "usage": None,
                "latency_ms": 100,
                "error": {
                    "category": "rate_limited",
                    "retryable": True,
                    "retry_after_ms": 2500,
                    "message": "rate limit reached",
                    "provider_code": "429",
                },
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        config = GatewayConfig(base_url="http://test-gw", gateway_secret="test-secret-123456")
        client = GatewayClient(config=config, http_client=mock_http)

        with pytest.raises(RateLimitedError) as exc_info:
            await client.generate_text(
                route_token="rtk_groq",
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "مرحبا"}],
            )

        err = exc_info.value
        assert err.category == "rate_limited"
        assert err.retryable is True
        assert err.retry_after_ms == 2500
        assert err.provider_code == "429"


@pytest.mark.asyncio
async def test_smart_router_fallback():
    calls: list[str] = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        token = request.headers["X-Route-Token"]
        calls.append(token)
        if token == "rtk_primary":
            # Primary fails with rate_limited
            return httpx.Response(
                200,
                json={
                    "succeeded": False,
                    "output": None,
                    "usage": None,
                    "latency_ms": 80,
                    "error": {
                        "category": "rate_limited",
                        "retryable": True,
                        "retry_after_ms": 1000,
                        "message": "primary is busy",
                    },
                },
            )
        # Secondary succeeds!
        return httpx.Response(
            200,
            json={
                "succeeded": True,
                "output": {"text": "نجح من المزود الاحتياطي!", "finish_reason": "stop"},
                "usage": {"units": 1},
                "latency_ms": 300,
                "error": None,
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        config = GatewayConfig(base_url="http://test-gw", gateway_secret="test-secret-123456")
        router = SmartRouter({"primary": "rtk_primary", "secondary": "rtk_secondary"})
        router.register_group("auto_fallback", primary="primary", fallbacks=["secondary"])

        client = GatewayClient(config=config, router=router, http_client=mock_http)
        res = await client.generate_text(
            route_token="auto_fallback",
            model="test-model",
            messages=[{"role": "user", "content": "مرحبا"}],
        )

        assert res.succeeded is True
        assert res.output.text == "نجح من المزود الاحتياطي!"
        assert calls == ["rtk_primary", "rtk_secondary"]


@pytest.mark.asyncio
async def test_dynamic_provider_manager():
    from client import MemoryRouteStorage, ProviderManager

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/describe"
        token = request.headers.get("X-Route-Token")
        if token == "rtk_custom_token":
            return httpx.Response(
                200,
                json={
                    "display_name": "Nebula AI",
                    "credential_mode": "platform",
                    "definition_version": "1.0.0",
                    "capabilities": {"chat": True, "code": True},
                    "operations": ["generate_text"],
                    "models": [{"name": "nebula-v1", "context_window": 32000}],
                    "health_supported": False,
                },
            )
        return httpx.Response(404, json={"error": {"category": "provider_unavailable"}})

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as mock_http:
        config = GatewayConfig(base_url="http://test-gw", gateway_secret="test-secret-123456")
        empty_storage = MemoryRouteStorage()
        client = GatewayClient(config=config, http_client=mock_http)
        manager = ProviderManager(config=config, storage=empty_storage, client=client)

        # 1. Zero initial hardcoded providers
        all_provs = await manager.get_all_providers()
        assert len(all_provs) == 0

        # 2. Discover dynamically from raw token
        info = await manager.discover_and_register("rtk_custom_token")
        assert info.display_name == "Nebula AI"
        assert info.route_ref in ("nebula", "nebula-ai")
        assert info.supports_model("nebula-v1")
        assert info.has_capability("chat")

        # 3. Dynamic lookup via newly registered alias
        token = await manager.get_provider_token("nebula")
        assert token == "rtk_custom_token"
        assert await manager.get_provider_token("nebula-ai") == "rtk_custom_token"


