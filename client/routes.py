"""Smart Routing and Fallback Management for External Platforms.

Since the Gateway enforces zero retries and rigid 1:1 token routing, this
module gives the external platform high availability, automatic failover,
and seamless provider switching without violating the gateway contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence


@dataclass
class RouteGroup:
    """A prioritized list of route tokens for automatic fallback."""
    name: str
    primary_token: str
    fallback_tokens: list[str] = field(default_factory=list)

    @property
    def all_tokens(self) -> list[str]:
        return [self.primary_token, *self.fallback_tokens]


class SmartRouter:
    """Manages friendly aliases, token mappings, and fallback chains."""

    def __init__(self, initial_tokens: dict[str, str] | None = None) -> None:
        self._tokens: dict[str, str] = dict(initial_tokens or {})
        self._groups: dict[str, RouteGroup] = {}

    def register_token(self, alias: str, token: str) -> None:
        """Register a friendly name for an opaque route token."""
        self._tokens[alias.lower()] = token

    def resolve_token(self, alias_or_token: str) -> str:
        """Resolve a friendly alias (e.g., 'groq') or return the raw token."""
        return self._tokens.get(alias_or_token.lower(), alias_or_token)

    def register_group(
        self,
        group_name: str,
        primary: str,
        fallbacks: Sequence[str] | None = None,
    ) -> None:
        """Define a fallback chain of providers for high availability.

        Example:
            router.register_group("smart_chat", primary="groq", fallbacks=["syntx", "youmind"])
        """
        resolved_primary = self.resolve_token(primary)
        resolved_fallbacks = [self.resolve_token(f) for f in (fallbacks or [])]
        self._groups[group_name.lower()] = RouteGroup(
            name=group_name,
            primary_token=resolved_primary,
            fallback_tokens=resolved_fallbacks,
        )

    def get_group(self, group_name: str) -> RouteGroup | None:
        return self._groups.get(group_name.lower())

