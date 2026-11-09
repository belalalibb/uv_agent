"""Launch the Gateway service using only its shared connection settings."""

import uvicorn

from app import build_app
from gateway.config import load_config_from_env


def start_server(host: str = "127.0.0.1", port: int = 8800) -> None:
    # The gateway secret/version remain required shared settings. Provider
    # packages are discovered from providers/; no provider list, allowlist, or
    # default route map is injected by this launcher.
    config = load_config_from_env()
    app = build_app(config)

    print("=" * 60)
    print(f"🚀 AI Gateway Service running at http://{host}:{port}")
    print(f"🔒 Secret Version: {config.current_secret_version}")
    print(f"🛣️  Legacy Route Tokens: {len(config.route_map)}")
    print("🤖 Providers: auto-discovered from providers/")
    print("=" * 60)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
