"""Provider registry tests — eager validation, OPEN-2, parity, duplicates."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway.provider_registry import ProviderRegistry
from providers._example.definition import DEFINITION as EXAMPLE_DEFINITION


def _register_example(registry: ProviderRegistry, slug: str = "example_mock"):
    return registry.register(
        slug=slug,
        raw_definition=dict(EXAMPLE_DEFINITION),
        facade_module="providers._example.adapter",
    )


def test_register_and_lazy_handlers_parity_ok() -> None:
    registry = ProviderRegistry()
    provider = _register_example(registry)
    handlers = provider.handlers()  # lazy import + parity check
    assert {op.value for op in handlers} == {"generate_text"}


def test_duplicate_slug_is_startup_error() -> None:
    registry = ProviderRegistry()
    _register_example(registry)
    with pytest.raises(ValueError, match="duplicate provider slug"):
        _register_example(registry)


def test_excluded_operation_rejected_at_registration() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    definition["operations"] = ["generate_text", "run_provider_agent"]
    with pytest.raises(ValueError, match="OPEN-2"):
        registry.register("x", definition, "providers._example.adapter")


def test_declared_without_handler_fails_parity() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    # analyze_vision is declared but the example facade has no handler for it.
    definition["operations"] = ["generate_text", "analyze_vision"]
    provider = registry.register("y", definition, "providers._example.adapter")
    with pytest.raises(ValueError, match="parity"):
        provider.handlers()


def test_invalid_definition_fails_eagerly() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    definition["definition_version"] = "not-semver"
    with pytest.raises(Exception):  # noqa: B017 — any validation failure is loud
        registry.register("z", definition, "providers._example.adapter")


def test_unregistered_slug_lookup_is_none() -> None:
    assert ProviderRegistry().get("ghost") is None


def test_public_name_lookup_is_case_insensitive() -> None:
    registry = ProviderRegistry()
    provider = _register_example(registry)

    assert registry.get_by_name("  example provider (MOCK) ") is provider
    assert registry.all() == (provider,)


def test_similar_public_display_names_are_rejected_at_startup() -> None:
    registry = ProviderRegistry()
    _register_example(registry, slug="first")
    duplicate = dict(EXAMPLE_DEFINITION)
    duplicate["display_name"] = "  example provider (MOCK) "

    with pytest.raises(ValueError, match="duplicate provider display name"):
        registry.register("second", duplicate, "providers._example.adapter")


def test_blank_public_display_name_is_startup_error() -> None:
    definition = dict(EXAMPLE_DEFINITION)
    definition["display_name"] = "   "

    with pytest.raises(ValueError, match="display name must not be blank"):
        ProviderRegistry().register("example_mock", definition, "providers._example.adapter")


def test_model_specific_operation_must_have_a_provider_handler() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    definition["models"] = [
        {
            "name": "vision-model",
            "support": {"operations": ["generate_text", "analyze_vision"]},
        }
    ]
    provider = registry.register(
        "model_override",
        definition,
        "providers._example.adapter",
    )

    with pytest.raises(ValueError, match="parity"):
        provider.handlers()


def test_excluded_operation_rejected_in_model_override_at_registration() -> None:
    definition = dict(EXAMPLE_DEFINITION)
    definition["models"] = [
        {"name": "m", "support": {"operations": ["upload_asset"]}}
    ]

    with pytest.raises(ValueError, match="OPEN-2"):
        ProviderRegistry().register(
            "x",
            definition,
            "providers._example.adapter",
        )



def _write_discoverable_package(
    package_root: Path,
    slug: str,
    *,
    definition: dict[str, object] | None = None,
    include_adapter: bool = True,
) -> None:
    package_dir = package_root / slug
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "definition.py").write_text(
        f"DEFINITION = {definition or dict(EXAMPLE_DEFINITION)!r}\n",
        encoding="utf-8",
    )
    if include_adapter:
        (package_dir / "adapter.py").write_text(
            "from gateway.contracts import FacadeResult, GatewayOperation\n"
            "async def generate_text(_context):\n"
            "    return FacadeResult(succeeded=True, output={'text': 'ok'})\n"
            "HANDLERS = {GatewayOperation.GENERATE_TEXT: generate_text}\n",
            encoding="utf-8",
        )


def test_discover_packages_scans_folders_and_skips_reference_packages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_name = "provider_discovery_fixture"
    package_root = tmp_path / package_name
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    discovered_definition = dict(EXAMPLE_DEFINITION)
    discovered_definition["display_name"] = "Auto Discovered Provider"
    _write_discoverable_package(
        package_root, "auto_discovered", definition=discovered_definition
    )
    _write_discoverable_package(package_root, "_example")
    _write_discoverable_package(package_root, "_template")
    _write_discoverable_package(package_root, ".hidden")

    registry = ProviderRegistry()
    discovered = registry.discover_packages(
        providers_root=package_root,
        package_prefix=package_name,
    )

    assert [provider.slug for provider in discovered] == ["auto_discovered"]
    assert registry.get_by_name("Auto Discovered Provider") is discovered[0]
    registry.eager_verify_all()


def test_discover_packages_fails_on_incomplete_provider_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_name = "incomplete_provider_fixture"
    package_root = tmp_path / package_name
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    broken = package_root / "broken_provider"
    broken.mkdir()
    (broken / "adapter.py").write_text("HANDLERS = {}\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ValueError, match="missing definition.py"):
        ProviderRegistry().discover_packages(
            providers_root=package_root,
            package_prefix=package_name,
        )


def test_discover_packages_does_not_ignore_an_empty_provider_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_name = "empty_provider_fixture"
    package_root = tmp_path / package_name
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "unfinished_provider").mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(ValueError, match="missing definition.py"):
        ProviderRegistry().discover_packages(
            providers_root=package_root,
            package_prefix=package_name,
        )
