"""Launch the AI Gateway Service with development defaults if not in environment."""

import os
import uvicorn
from app import build_app, register_live_providers
from gateway.config import GatewayConfig, load_config_from_env
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry

DEFAULT_ROUTE_MAP = {
    "rtk_groq_production": "groq",
    "rtk_syntx_production_live_session": "syntx",
    "rtk_deepai_production": "deepai",
    "rtk_freebuff_production": "freebuff",
    "rtk_youmind_production": "youmind",
    "rtk_ivycraft_production": "ivycraft",
    "rtk_llamacoder_production": "llamacoder",
    "rtk_upstage_production": "upstage",
    "rtk_voyage_production": "voyage",
    "rtk_runpod_production": "runpod_console",
    "rtk_parallel_production": "parallel",
    "rtk_notegpt_production": "notegpt",
    "rtk_overchat_production": "overchat",
    "rtk_tinyfish_production": "tinyfish",
}


def start_server(host: str = "127.0.0.1", port: int = 8800) -> None:
    # Set default dev environment variables if not already provided
    os.environ.setdefault("GW_SECRET_CURRENT", "live-demo-secret-key-bolla-zizo")
    os.environ.setdefault("GW_SECRET_CURRENT_VERSION", "1")

    # If route map is set in env use it, otherwise use all 14 registered providers
    if "GW_ROUTE_MAP" not in os.environ:
        os.environ["GW_ROUTE_MAP"] = ",".join(f"{t}:{s}" for t, s in DEFAULT_ROUTE_MAP.items())

    config = load_config_from_env()
    registry = ProviderRegistry()
    register_live_providers(registry)
    registry.eager_verify_all()

    routes = RouteRegistry(config.route_map, config.disabled_slugs)
    app = build_app(config, registry, routes)

    print("=" * 60)
    print(f"🚀 AI Gateway Service running at http://{host}:{port}")
    print(f"🔒 Secret Version: {config.current_secret_version}")
    print(f"🛣️  Mapped Routes : {len(config.route_map)} active routes")
    print(f"🤖 Live Providers: {len(registry._providers)} registered providers")
    print("=" * 60)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()

