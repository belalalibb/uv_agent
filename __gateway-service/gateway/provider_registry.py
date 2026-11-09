"""Provider registry — package discovery + eager DEFINITION validation.

Rules (ADR-0008 / report §11):
- Auto-discovery of packages under ``providers/`` (skip ``_``-prefixed:
  ``_template`` and ``_example`` are reference material, never live).
- Discovery != activation: a discovered provider with no route_token
  mapping is simply unreachable (deny-by-default extends across the wire).
- Eager DEFINITION validation at startup; LAZY facade import at first
  dispatch (heavy SDK imports don't block boot; lying DEFINITIONs still
  fail loud at startup).
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
