"""Entrypoint and composition for the Gateway service.

Provider implementations depend only on ``gateway.contracts``. The Gateway
core owns package discovery, validation, routing, and HTTP composition; provider
packages never import this module.
"""

from __future__ import annotations

from fastapi import FastAPI

from gateway.config import GatewayConfig, load_config_from_env
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from gateway.routes import build_router


def build_app(
    config: GatewayConfig,
    providers: ProviderRegistry | None = None,
    routes: RouteRegistry | None = None,
) -> FastAPI:
    """Compose the Gateway, auto-discovering packages when none are supplied."""

    if providers is None:
        providers = ProviderRegistry()
        providers.discover_packages()
        providers.eager_verify_all()

    app = FastAPI(title="Provider Gateway", docs_url=None, redoc_url=None, openapi_url=None)
    route_registry = routes or RouteRegistry(config.route_map, config.disabled_slugs)
    app.include_router(build_router(config, route_registry, providers))
    return app


def main() -> None:  # pragma: no cover — process entrypoint, not hermetic
    import uvicorn

    config = load_config_from_env()
    uvicorn.run(build_app(config), host="127.0.0.1", port=8800)


def register_live_providers(registry: ProviderRegistry) -> None:
    """Compatibility shim: discover every live package instead of a fixed list.

    Production startup calls ``build_app`` without a registry, which performs
    this discovery automatically. Kept for older test/live scripts that still
    call the former registration helper; underscore-prefixed reference
    packages such as ``_example`` and ``_template`` are excluded by the
    registry.
    """

    registry.discover_packages()


if __name__ == "__main__":  # pragma: no cover
    main()
