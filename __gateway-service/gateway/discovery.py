"""Discovery projections — /v1/providers, /v1/describe, /v1/models, /v1/health.

The projection NEVER contains the slug or any upstream identity: only the
Provider's public definition crosses the boundary. Model-level defaults are
resolved here so SDK consumers do not need to implement inheritance.
"""

from __future__ import annotations

from collections.abc import Iterable

from gateway.contracts import (
    DeclaredModel,
    DescribeResponse,
    DiscoveredModel,
    HealthResponse,
    ModelsResponse,
    ProviderCatalogEntry,
    ProviderCatalogResponse,
    ProviderDefinition,
)


def project_model(
    definition: ProviderDefinition,
    model: DeclaredModel,
) -> DiscoveredModel:
    """Return a model row with Provider defaults and model overrides resolved."""
    override = model.support
    operations = (
        override.operations
        if override is not None and override.operations is not None
        else definition.operations
    )
    capabilities = (
        override.capabilities
        if override is not None and override.capabilities is not None
        else definition.capabilities
    )
    return DiscoveredModel(
        name=model.name,
        context_window=model.context_window,
        operations=list(operations),
        capabilities=dict(capabilities),
    )


def project_models(definition: ProviderDefinition) -> ModelsResponse:
    """Project declared models with their effective support fields."""
    return ModelsResponse(
        models=[project_model(definition, model) for model in definition.models]
    )


def project_describe(definition: ProviderDefinition) -> DescribeResponse:
    return DescribeResponse(
        display_name=definition.display_name,
        credential_mode=definition.credential_mode,
        capabilities=dict(definition.capabilities),
        operations=list(definition.operations),
        models=project_models(definition).models,
        definition_version=definition.definition_version,
        health_supported=definition.health_supported,
    )


def project_catalog(definitions: Iterable[ProviderDefinition]) -> ProviderCatalogResponse:
    """Expose registered public names and manifests, never internal slugs/tokens."""

    ordered = sorted(definitions, key=lambda item: item.display_name.casefold())
    return ProviderCatalogResponse(
        providers=[
            ProviderCatalogEntry(
                name=definition.display_name,
                description=project_describe(definition),
            )
            for definition in ordered
        ]
    )


def project_health(definition: ProviderDefinition) -> HealthResponse:
    """Health checks are not implemented; UNKNOWN remains the honest answer.

    Provider connectivity is currently observed from ordinary execute results,
    not by an independent probe. ``health_supported`` is retained for
    compatibility but does not authorize a Gateway-side network call here.
    """

    return HealthResponse(status="UNKNOWN", checked_at=None)
