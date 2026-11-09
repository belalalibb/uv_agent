"""Provider registry — package discovery + eager DEFINITION validation.

Rules (ADR-0008 / report §11):
- Discover provider packages directly under ``providers/`` at startup; skip
  dot/underscore-prefixed reference folders.
- Provider names and manifest data come from each package's folder and
  ``definition.py``. Name-based routing needs no per-provider route-map entry.
- Eager DEFINITION validation at startup and lazy facade imports until
  ``eager_verify_all`` checks handlers.
- OPEN-2 excluded operations in a DEFINITION = startup refusal.
- Provider-default operations plus model-specific operation overrides form
  the declared handler set; a missing or extra facade handler is a STARTUP
  failure, not a runtime 500.
- Duplicate slug or normalized public display name = startup error.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from gateway.contracts import (
    FacadeResult,
    GatewayOperation,
    ProviderContext,
    ProviderDefinition,
    reject_excluded_operations,
)

FacadeHandler = Callable[[ProviderContext], Awaitable[FacadeResult]]


@dataclass
class RegisteredProvider:
    """One discovered provider package (slug is gateway-private)."""

    slug: str
    definition: ProviderDefinition
    facade_module: str  # imported lazily at first dispatch
    _handlers: dict[GatewayOperation, FacadeHandler] | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def handlers(self) -> dict[GatewayOperation, FacadeHandler]:
        """Import the facade lazily and verify declaration<->handler parity."""

        with self._lock:
            if self._handlers is None:
                module = importlib.import_module(self.facade_module)
                handlers = getattr(module, "HANDLERS", None)
                if not isinstance(handlers, dict):
                    msg = f"facade module {self.facade_module} must export HANDLERS dict"
                    raise ValueError(msg)
                declared = set(self.definition.operations)
                for model in self.definition.models:
                    if (
                        model.support is not None
                        and model.support.operations is not None
                    ):
                        declared.update(model.support.operations)
                registered = set(handlers)
                if declared != registered:
                    missing = sorted(op.value for op in declared - registered)
                    extra = sorted(op.value for op in registered - declared)
                    msg = (
                        "DEFINITION<->handler parity violation: "
                        f"declared-without-handler={missing}, handler-without-declaration={extra}"
                    )
                    raise ValueError(msg)
                self._handlers = dict(handlers)
            return self._handlers


class ProviderRegistry:
    """Registry keyed by gateway-private slug."""

    def __init__(self) -> None:
        self._providers: dict[str, RegisteredProvider] = {}

    def register(
        self,
        slug: str,
        raw_definition: dict[str, object],
        facade_module: str,
    ) -> RegisteredProvider:
        """Eager validation at registration (startup)."""

        if slug in self._providers:
            msg = f"duplicate provider slug: {slug!r}"
            raise ValueError(msg)
        raw_ops = raw_definition.get("operations")
        if isinstance(raw_ops, list):
            reject_excluded_operations([str(op) for op in raw_ops])  # OPEN-2
        raw_models = raw_definition.get("models")
        if isinstance(raw_models, list):
            for raw_model in raw_models:
                if not isinstance(raw_model, dict):
                    continue
                raw_support = raw_model.get("support")
                if not isinstance(raw_support, dict):
                    continue
                override_ops = raw_support.get("operations")
                if isinstance(override_ops, list):
                    reject_excluded_operations([str(op) for op in override_ops])
        definition = ProviderDefinition.model_validate(raw_definition)
        normalized_name = definition.display_name.strip().casefold()
        if not normalized_name:
            msg = "provider display name must not be blank"
            raise ValueError(msg)
        if any(
            item.definition.display_name.strip().casefold() == normalized_name
            for item in self._providers.values()
        ):
            msg = f"duplicate provider display name: {definition.display_name!r}"
            raise ValueError(msg)
        provider = RegisteredProvider(
            slug=slug, definition=definition, facade_module=facade_module
        )
        self._providers[slug] = provider
        return provider

    def discover_packages(
        self,
        providers_root: str | Path | None = None,
        *,
        package_prefix: str = "providers",
    ) -> tuple[RegisteredProvider, ...]:
        """Load every complete Provider package below ``providers_root``.

        Each immediate child folder is one Provider: its folder name is the
        private slug, ``definition.py`` must export a DEFINITION mapping, and
        ``adapter.py`` must export HANDLERS. Dot/underscore-prefixed folders
        are ignored for templates and development material. No central list
        or per-Provider routing environment variables are needed.

        Any non-hidden child directory must be a complete Provider package;
        incomplete folders fail startup rather than silently disappearing
        from the catalog. The directory contents are trusted application
        code; adapters are imported by the startup parity check.
        """
        root = (
            Path(providers_root)
            if providers_root is not None
            else Path(__file__).resolve().parent.parent / "providers"
        )
        if not root.is_dir():
            raise ValueError(f"Provider package directory does not exist: {root}")

        importlib.invalidate_caches()
        for package_dir in sorted(root.iterdir(), key=lambda item: item.name):
            if (
                not package_dir.is_dir()
                or package_dir.is_symlink()
                or package_dir.name.startswith((".", "_"))
            ):
                continue

            definition_path = package_dir / "definition.py"
            adapter_path = package_dir / "adapter.py"
            has_definition = definition_path.is_file()
            has_adapter = adapter_path.is_file()
            if not has_definition or not has_adapter:
                missing = "definition.py" if not has_definition else "adapter.py"
                raise ValueError(
                    f"Provider package {package_dir.name!r} is missing {missing}"
                )
            if not package_dir.name.isidentifier():
                raise ValueError(
                    f"Provider folder {package_dir.name!r} must be a Python identifier"
                )

            definition_module_name = (
                f"{package_prefix}.{package_dir.name}.definition"
            )
            definition_module = importlib.import_module(definition_module_name)
            raw_definition = getattr(definition_module, "DEFINITION", None)
            if not isinstance(raw_definition, dict):
                raise ValueError(
                    f"{definition_module_name} must export a DEFINITION mapping"
                )
            self.register(
                package_dir.name,
                raw_definition,
                f"{package_prefix}.{package_dir.name}.adapter",
            )

        return self.all()

    def get(self, slug: str) -> RegisteredProvider | None:
        return self._providers.get(slug)

    def get_by_name(self, name: str) -> RegisteredProvider | None:
        """Resolve a public display name without exposing the private slug."""

        normalized = name.strip().casefold()
        if not normalized:
            return None
        return next(
            (
                provider
                for provider in self._providers.values()
                if provider.definition.display_name.strip().casefold() == normalized
            ),
            None,
        )

    def all(self) -> tuple[RegisteredProvider, ...]:
        """Return the registered providers in deterministic registration order."""

        return tuple(self._providers.values())

    def eager_verify_all(self) -> None:
        """Optional startup strictness: force handler parity for every provider."""

        for provider in self._providers.values():
            provider.handlers()
