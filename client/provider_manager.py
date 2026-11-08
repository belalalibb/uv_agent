"""Dynamic ProviderManager — Zero-Hardcoding, Pluggable Discovery & Token Management.

Architecture:
- 100% Dynamic: Zero hardcoded provider slugs or route tokens.
- Pluggable Storages: Env, File (JSON), Memory, or Custom Async Resolvers.
- Gateway Self-Discovery: Introspects provider identity (display_name, operations,
  models, capabilities) live via Gateway '/v1/describe' projections.
- High Availability: In-memory TTL caching with automatic refresh.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Protocol, Sequence

from .client import GatewayClient
from .config import GatewayConfig
from .models import HealthResponse, ModelInfo, ProviderManifest
from .routes import SmartRouter


# --------------------------------------------------------------------------- #
# Provider Info Data Model                                                    #
# --------------------------------------------------------------------------- #

@dataclass
class ProviderInfo:
    """Consolidated provider information discovered dynamically from the Gateway."""
    route_ref: str
    route_token: str
    display_name: str
    credential_mode: str
    definition_version: str
    capabilities: dict[str, bool]
    operations: list[str]
    models: list[ModelInfo]
    health_supported: bool
    health_status: str | None = None

    def has_capability(self, capability_name: str) -> bool:
        """Check if provider explicitly enables a capability."""
        return bool(self.capabilities.get(capability_name, False))

    def supports_operation(self, operation_name: str) -> bool:
        """Check if provider explicitly declares an operation."""
        return operation_name in self.operations

    def supports_model(self, model_name: str) -> bool:
        """Check if a specific model is declared by this provider."""
        target = model_name.strip().lower()
        return any(m.name.lower() == target for m in self.models)


# --------------------------------------------------------------------------- #
# Pluggable Route Token Storage Engine                                        #
# --------------------------------------------------------------------------- #

class RouteTokenStorage(ABC):
    """Abstract interface for retrieving and persisting route tokens."""

    @abstractmethod
    async def get_token(self, route_ref: str) -> str | None:
        """Retrieve token for a given route alias or reference."""

    @abstractmethod
    async def get_all_routes(self) -> dict[str, str]:
        """Return all registered route mappings {alias: token}."""

    @abstractmethod
    async def set_route(self, route_ref: str, route_token: str) -> None:
        """Register or update a route token."""

    @abstractmethod
    async def remove_route(self, route_ref: str) -> None:
        """Remove a route mapping."""


class MemoryRouteStorage(RouteTokenStorage):
    """Dynamic in-memory storage for route tokens."""

    def __init__(self, initial_routes: dict[str, str] | None = None) -> None:
        self._routes: dict[str, str] = {
            k.strip().lower(): v.strip() for k, v in (initial_routes or {}).items()
        }

    async def get_token(self, route_ref: str) -> str | None:
        return self._routes.get(route_ref.strip().lower())

    async def get_all_routes(self) -> dict[str, str]:
        return dict(self._routes)

    async def set_route(self, route_ref: str, route_token: str) -> None:
        self._routes[route_ref.strip().lower()] = route_token.strip()

    async def remove_route(self, route_ref: str) -> None:
        self._routes.pop(route_ref.strip().lower(), None)


class EnvRouteStorage(RouteTokenStorage):
    """Discovers route tokens dynamically from OS environment variables.

    Supports:
    1. Variables with prefix (e.g. ROUTE_TOKEN_GROQ=rtk_..., ROUTE_TOKEN_SYNTX=rtk_...)
    2. Comma-separated map string (e.g. ROUTE_MAP="groq:rtk_groq,syntx:rtk_syntx")
    3. Gateway internal route map (e.g. GW_ROUTE_MAP="rtk_groq:groq,rtk_syntx:syntx")
    """

    def __init__(
        self,
        prefix: str = "ROUTE_TOKEN_",
        map_env_var: str = "ROUTE_MAP",
        gw_map_env_var: str = "GW_ROUTE_MAP",
    ) -> None:
        self.prefix = prefix
        self.map_env_var = map_env_var
        self.gw_map_env_var = gw_map_env_var
        self._memory = MemoryRouteStorage()
        self._reload_from_env()

    def _reload_from_env(self) -> None:
        # A. Discover from prefix: ROUTE_TOKEN_<ALIAS>=<TOKEN>
        for key, val in os.environ.items():
            if key.startswith(self.prefix) and val.strip():
                alias = key[len(self.prefix):].lower().replace("_", "-")
                self._memory._routes[alias] = val.strip()

        # B. Discover from ROUTE_MAP="alias1:token1,alias2:token2"
        map_str = os.getenv(self.map_env_var, "")
        if map_str:
            for item in map_str.split(","):
                if ":" in item:
                    part1, part2 = item.split(":", 1)
                    if part1.strip() and part2.strip():
                        # If part2 starts with rtk_, it is alias:token
                        if part2.strip().startswith("rtk_") or len(part2) > len(part1):
                            self._memory._routes[part1.strip().lower()] = part2.strip()
                        else:
                            self._memory._routes[part2.strip().lower()] = part1.strip()

        # C. Discover from GW_ROUTE_MAP="token1:slug1,token2:slug2"
        gw_map = os.getenv(self.gw_map_env_var, "")
        if gw_map:
            for item in gw_map.split(","):
                if ":" in item:
                    token, slug = item.split(":", 1)
                    if token.strip() and slug.strip():
                        self._memory._routes[slug.strip().lower()] = token.strip()

    async def get_token(self, route_ref: str) -> str | None:
        return await self._memory.get_token(route_ref)

    async def get_all_routes(self) -> dict[str, str]:
        return await self._memory.get_all_routes()

    async def set_route(self, route_ref: str, route_token: str) -> None:
        await self._memory.set_route(route_ref, route_token)

    async def remove_route(self, route_ref: str) -> None:
        await self._memory.remove_route(route_ref)


class FileRouteStorage(RouteTokenStorage):
    """Dynamically reads and writes route tokens to a JSON file."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._memory = MemoryRouteStorage()
        self._load_file()

    def _load_file(self) -> None:
        if self.file_path.is_file():
            try:
                data = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._memory = MemoryRouteStorage(data)
            except Exception:
                pass

    def _save_file(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(self._memory._routes, indent=2), encoding="utf-8")

    async def get_token(self, route_ref: str) -> str | None:
        return await self._memory.get_token(route_ref)

    async def get_all_routes(self) -> dict[str, str]:
        return await self._memory.get_all_routes()

    async def set_route(self, route_ref: str, route_token: str) -> None:
        await self._memory.set_route(route_ref, route_token)
        self._save_file()

    async def remove_route(self, route_ref: str) -> None:
        await self._memory.remove_route(route_ref)
        self._save_file()


# --------------------------------------------------------------------------- #
# Dynamic Provider Manager                                                    #
# --------------------------------------------------------------------------- #

class ProviderManager:
    """Platform manager for discovering, inspecting, and managing AI Gateway providers.

    Guarantees:
    - Zero Hardcoded Provider Slugs or Tokens.
    - Completely Dynamic Runtime Configuration.
    - Automatic Discovery of Provider Identity via Gateway Projections.
    """

    def __init__(
        self,
        config: GatewayConfig | None = None,
        storage: RouteTokenStorage | None = None,
        router: SmartRouter | None = None,
        client: GatewayClient | None = None,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        """Initialize the ProviderManager without any static dependencies.

        Args:
            config: Gateway connection parameters (read from env if omitted).
            storage: RouteTokenStorage backend (defaults to EnvRouteStorage).
            router: SmartRouter instance (initialized dynamically from storage).
            client: Optional pre-configured GatewayClient.
            cache_ttl_seconds: Cache TTL for manifest and model queries.
        """
        self.config = config or GatewayConfig.from_env()
        # Default storage: Dynamic discovery from Environment variables
        self.storage: RouteTokenStorage = storage or EnvRouteStorage()
        self.router = router or SmartRouter()

        self._owns_client = client is None
        self.client = client or GatewayClient(config=self.config, router=self.router)

        # In-memory TTL caches for gateway manifest projections
        self.cache_ttl = cache_ttl_seconds
        self._manifest_cache: dict[str, tuple[float, ProviderManifest]] = {}
        self._models_cache: dict[str, tuple[float, list[ModelInfo]]] = {}

        # Reverse lookup map: {route_token -> display_name/alias}
        self._token_to_alias: dict[str, str] = {}

    async def __aenter__(self) -> ProviderManager:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close internal client resources."""
        if self._owns_client and self.client:
            await self.client.close()

    # ----------------------------------------------------------------------- #
    # Dynamic Route Registration & Resolution                                 #
    # ----------------------------------------------------------------------- #

    async def get_all_providers(self) -> dict[str, str]:
        """Get all registered provider routes {alias: route_token} dynamically."""
        return await self.storage.get_all_routes()

    async def register_provider_route(self, route_ref: str, route_token: str) -> None:
        """Dynamically register or update a provider route reference."""
        clean_ref = route_ref.strip().lower()
        clean_token = route_token.strip()
        await self.storage.set_route(clean_ref, clean_token)
        self.router.register_token(clean_ref, clean_token)
        self._token_to_alias[clean_token] = clean_ref

    async def remove_provider_route(self, route_ref: str) -> None:
        """Dynamically unregister a provider route."""
        clean_ref = route_ref.strip().lower()
        token = await self.storage.get_token(clean_ref)
        if token:
            self._token_to_alias.pop(token, None)
        await self.storage.remove_route(clean_ref)

    async def load_routes_from_dict(self, routes: dict[str, str]) -> None:
        """Bulk load route mappings dynamically at runtime."""
        for ref, token in routes.items():
            await self.register_provider_route(ref, token)

    async def load_routes_from_json(self, file_path: str | Path) -> None:
        """Load route mappings from a JSON configuration file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Routes configuration file not found: {file_path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Routes JSON file must contain a key-value mapping of {alias: token}")
        await self.load_routes_from_dict(data)

    async def get_provider_token(self, route_ref: str) -> str:
        """Resolve route token from dynamic storage or raw token.

        Supports:
        1. Friendly alias resolved through storage (e.g. 'groq', 'syntx').
        2. Direct raw route token passed as input (e.g. 'rtk_...').
        """
        clean_ref = route_ref.strip()

        # 1. Lookup in dynamic storage
        token = await self.storage.get_token(clean_ref.lower())
        if token:
            return token

        # 2. Check if the input is already a raw route token
        if clean_ref.startswith("rtk_") or len(clean_ref) >= 16:
            return clean_ref

        # 3. Lookup in SmartRouter
        resolved = self.router.resolve_token(clean_ref)
        if resolved != clean_ref or resolved.startswith("rtk_"):
            return resolved

        routes = await self.storage.get_all_routes()
        raise KeyError(
            f"Provider route reference '{route_ref}' not found in dynamic storage. "
            f"Available routes: {list(routes.keys())}"
        )

    # ----------------------------------------------------------------------- #
    # Gateway Self-Discovery (Zero-Assumptions Introspection)                   #
    # ----------------------------------------------------------------------- #

    async def discover_and_register(self, route_token: str) -> ProviderInfo:
        """Discover a provider's identity directly from the Gateway and register it.

        Takes a raw route token (from a secure vault, DB, or webhook), queries
        '/v1/describe', extracts its official 'display_name', and automatically
        creates a clean alias for it dynamically!
        """
        token = route_token.strip()
        manifest = await self.describe_provider(token, refresh=True)

        # Derive a clean alias from the official display name (e.g. "Syntx AI" -> "syntx-ai", "syntx")
        display_name = manifest.display_name.strip()
        base_alias = re.sub(r"[^a-zA-Z0-9]+", "-", display_name).strip("-").lower()
        first_word = base_alias.split("-")[0] if "-" in base_alias else base_alias

        # Register normalized aliases dynamically
        await self.register_provider_route(base_alias, token)
        if first_word and first_word != base_alias:
            await self.register_provider_route(first_word, token)

        return await self.get_provider_by_route(token)

    async def discover_all_from_tokens(
        self,
        tokens: Sequence[str],
        continue_on_error: bool = True,
    ) -> list[ProviderInfo]:
        """Bootstrap the manager dynamically by discovering a list of raw route tokens."""
        discovered: list[ProviderInfo] = []
        for token in tokens:
            try:
                info = await self.discover_and_register(token)
                discovered.append(info)
            except Exception as exc:
                if not continue_on_error:
                    raise exc
                continue
        return discovered

    # ----------------------------------------------------------------------- #
    # Manifest & Discovery Lookups                                             #
    # ----------------------------------------------------------------------- #

    async def describe_provider(
        self,
        route_token: str,
        refresh: bool = False,
    ) -> ProviderManifest:
        """Get provider manifest projection from the Gateway (/v1/describe)."""
        token = await self.get_provider_token(route_token)
        now = time.monotonic()

        if not refresh and token in self._manifest_cache:
            cached_at, manifest = self._manifest_cache[token]
            if now - cached_at < self.cache_ttl:
                return manifest

        manifest = await self.client.describe(route_token=token)
        self._manifest_cache[token] = (now, manifest)
        return manifest

    async def get_models(
        self,
        route_token: str,
        refresh: bool = False,
    ) -> list[ModelInfo]:
        """Get declared models for a provider (/v1/models)."""
        token = await self.get_provider_token(route_token)
        now = time.monotonic()

        if not refresh and token in self._models_cache:
            cached_at, models = self._models_cache[token]
            if now - cached_at < self.cache_ttl:
                return models

        models = await self.client.list_models(route_token=token)
        self._models_cache[token] = (now, models)
        return models

    async def get_capabilities(
        self,
        route_token: str,
        refresh: bool = False,
    ) -> dict[str, bool]:
        """Get supported provider capabilities."""
        manifest = await self.describe_provider(route_token, refresh=refresh)
        return manifest.capabilities

    async def check_health(self, route_token: str) -> HealthResponse:
        """Check provider operational health status (/v1/health)."""
        token = await self.get_provider_token(route_token)
        return await self.client.check_health(route_token=token)

    async def get_provider_by_route(
        self,
        route_ref: str,
        include_health: bool = False,
    ) -> ProviderInfo:
        """Get complete discovered provider information."""
        token = await self.get_provider_token(route_ref)
        manifest = await self.describe_provider(token)
        models = manifest.models if manifest.models else await self.get_models(token)

        health_status: str | None = None
        if include_health and manifest.health_supported:
            try:
                h = await self.check_health(token)
                health_status = h.status
            except Exception:
                health_status = "UNKNOWN"

        alias = self._token_to_alias.get(token, route_ref.lower())
        return ProviderInfo(
            route_ref=alias,
            route_token=token,
            display_name=manifest.display_name,
            credential_mode=manifest.credential_mode,
            definition_version=manifest.definition_version,
            capabilities=manifest.capabilities,
            operations=manifest.operations,
            models=models,
            health_supported=manifest.health_supported,
            health_status=health_status,
        )

    # ----------------------------------------------------------------------- #
    # Platform Query & Smart Match Helpers                                     #
    # ----------------------------------------------------------------------- #

    async def find_providers_for_operation(self, operation: str) -> list[str]:
        """Find all registered providers that support a specific Gateway operation."""
        matching: list[str] = []
        routes = await self.storage.get_all_routes()
        for ref, token in routes.items():
            try:
                manifest = await self.describe_provider(token)
                if operation in manifest.operations:
                    matching.append(ref)
            except Exception:
                continue
        return matching

    async def find_providers_for_capability(self, capability: str) -> list[str]:
        """Find all registered providers declaring a capability (e.g. 'reasoning', 'vision_input')."""
        matching: list[str] = []
        routes = await self.storage.get_all_routes()
        for ref, token in routes.items():
            try:
                caps = await self.get_capabilities(token)
                if caps.get(capability, False):
                    matching.append(ref)
            except Exception:
                continue
        return matching

    async def find_provider_for_model(self, model_name: str) -> str | None:
        """Find the first registered provider that declares the given model name."""
        target = model_name.strip().lower()
        routes = await self.storage.get_all_routes()
        for ref, token in routes.items():
            try:
                models = await self.get_models(token)
                if any(m.name.lower() == target for m in models):
                    return ref
            except Exception:
                continue
        return None
