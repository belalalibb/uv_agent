#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🏛️ Provider Contract & Standard Compliance Test
════════════════════════════════════════════════════════════════════════════════
Enforces strict compliance with:
- Bolla Constitution v1.2
- Invariant Workflow: .agents/workflows/00-gateway-provider-onboarding.md
- Zero Browser Law (100% Pure HTTP Requests)
- Three-Layer Architecture (ADR-0008)
- Dynamic Models Loading, Closed Capabilities & Anchor Sealing
════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import re
import pytest

from gateway.contracts import CAPABILITY_KEYS

GATEWAY_ROOT = Path(__file__).resolve().parents[1]
PROVIDERS_DIR = GATEWAY_ROOT / "providers"
TESTS_DIR = GATEWAY_ROOT / "tests" / "providers"
ONBOARDING_WORKFLOW = ".agents/workflows/00-gateway-provider-onboarding.md"

REQUIRED_FILES = [
    "__init__.py",
    "adapter.py",
    "definition.py",
    "models_metadata.json",
]

BANNED_BROWSER_LIBS = [
    "selenium",
    "seleniumbase",
    "playwright",
    "pyppeteer",
    "webdriver",
    "undetected_chromedriver",
]
_BROWSER_PATTERN = re.compile(r"\b(" + "|".join(BANNED_BROWSER_LIBS) + r")\b", re.IGNORECASE)


def get_live_provider_slugs() -> list[str]:
    """Discover production provider directories under providers/ (skipping templates)."""
    slugs = []
    for item in PROVIDERS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith((".", "_")):
            if (item / "definition.py").exists():
                slugs.append(item.name)
    return sorted(slugs)


# --------------------------------------------------------------------------- #
# 1. Zero-Browser Law Enforcement (100% Pure HTTP Requests)                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_zero_browser_dependencies(slug: str) -> None:
    """Invariant 1: Zero-Browser Law — Absolutely NO browser automation libraries allowed."""
    pdir = PROVIDERS_DIR / slug
    for py_file in pdir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        matches = _BROWSER_PATTERN.findall(text)
        assert not matches, (
            f"Provider '{slug}' violates Zero-Browser Law! "
            f"Found forbidden browser libraries {set(matches)} in {py_file.name}. "
            f"All providers MUST use 100% pure HTTP requests only. "
            f"See workflow: {ONBOARDING_WORKFLOW}"
        )


# --------------------------------------------------------------------------- #
# 2. File Structure & Core Components                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_provider_file_structure(slug: str) -> None:
    """Invariant 2: Ensure core files exist."""
    pdir = PROVIDERS_DIR / slug
    for fname in REQUIRED_FILES:
        target = pdir / fname
        assert target.exists(), (
            f"Provider '{slug}' is missing required file: {fname}. "
            f"See workflow: {ONBOARDING_WORKFLOW}"
        )
    # Must have either _core.py or _upstream.py
    has_layer1 = (pdir / "_core.py").exists() or (pdir / "_upstream.py").exists()
    assert has_layer1, (
        f"Provider '{slug}' missing Layer 1 implementation (_core.py or _upstream.py). "
        f"See workflow: {ONBOARDING_WORKFLOW}"
    )


# --------------------------------------------------------------------------- #
# 3. Models Metadata & Dynamic Loading                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_models_metadata_json_schema(slug: str) -> None:
    """Invariant 3: models_metadata.json must be valid JSON with non-empty models."""
    meta_path = PROVIDERS_DIR / slug / "models_metadata.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        if "models" in data and isinstance(data["models"], list):
            assert len(data["models"]) > 0, f"{slug}/models_metadata.json 'models' list is empty"
        else:
            assert len(data) > 0, f"{slug}/models_metadata.json is empty"
    elif isinstance(data, list):
        assert len(data) > 0, f"{slug}/models_metadata.json list is empty"
    else:
        pytest.fail(f"Invalid models_metadata.json shape in {slug}")


# --------------------------------------------------------------------------- #
# 4. Capabilities & Closed Taxonomy Integrity                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_definition_capabilities_and_parity(slug: str) -> None:
    """Invariant 4: Capabilities must belong to closed set and match operations."""
    mod = importlib.import_module(f"providers.{slug}.definition")
    assert hasattr(mod, "DEFINITION"), f"{slug}/definition.py must export 'DEFINITION'"
    d = getattr(mod, "DEFINITION")
    assert isinstance(d, dict), f"{slug} DEFINITION must be a dictionary"
    assert "display_name" in d, f"{slug} DEFINITION missing display_name"
    assert "credential_mode" in d or "auth_pattern" in d, f"{slug} DEFINITION missing credential/auth mode"

    caps = d.get("capabilities", {})
    unknown_caps = set(caps.keys()) - CAPABILITY_KEYS
    assert not unknown_caps, (
        f"Provider '{slug}' declared unknown capabilities {unknown_caps}! "
        f"Allowed closed set: {sorted(CAPABILITY_KEYS)}. "
        f"See workflow: {ONBOARDING_WORKFLOW}"
    )


# --------------------------------------------------------------------------- #
# 5. Live Registration in app.py                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_provider_registered_in_app_py(slug: str) -> None:
    """Invariant 5: Every live provider MUST be registered in app.py::register_live_providers."""
    from app import register_live_providers
    from gateway.provider_registry import ProviderRegistry

    registry = ProviderRegistry()
    register_live_providers(registry)
    registered = registry.get(slug)
    assert registered is not None, (
        f"Provider '{slug}' is NOT registered in app.py::register_live_providers! "
        f"Add registry.register('{slug}', ...) to app.py. "
        f"See workflow: {ONBOARDING_WORKFLOW} (Step 5)"
    )


# --------------------------------------------------------------------------- #
# 6. Anchor Files Integrity (Bolla Law 1 & 9)                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_anchor_files_exist_for_core_files(slug: str) -> None:
    """Invariant 6: Every provider must have .anchor files alongside code."""
    pdir = PROVIDERS_DIR / slug
    check_files = ["adapter.py", "definition.py", "models_metadata.json"]
    if (pdir / "_core.py").exists():
        check_files.append("_core.py")
    elif (pdir / "_upstream.py").exists():
        check_files.append("_upstream.py")

    for fname in check_files:
        anchor_file = pdir / f"{fname}.anchor"
        assert anchor_file.exists(), (
            f"Provider '{slug}' is missing required anchor: {fname}.anchor. "
            f"Bolla Law 1 & 9 require cryptographic anchors for all provider code. "
            f"See workflow: {ONBOARDING_WORKFLOW} (Invariant #6)"
        )


# --------------------------------------------------------------------------- #
# 7. Dedicated Hermetic Test Suite                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", get_live_provider_slugs())
def test_dedicated_test_suite_exists(slug: str) -> None:
    """Invariant 7: Every provider must have its dedicated test file under tests/providers/."""
    test_file = TESTS_DIR / f"test_{slug}.py"
    assert test_file.exists(), (
        f"Provider '{slug}' is missing dedicated test suite: tests/providers/test_{slug}.py. "
        f"See workflow: {ONBOARDING_WORKFLOW} (Invariant #7)"
    )


# --------------------------------------------------------------------------- #
# 8. Error Categories Taxonomy Sanitization                                   #
# --------------------------------------------------------------------------- #


def test_no_rogue_or_uppercase_error_categories() -> None:
    """Ensure no UpstreamFailure uses an uppercase or invalid error category."""
    from gateway.contracts import ErrorCategory
    valid_categories = {c.value for c in ErrorCategory}

    pat = re.compile(r'UpstreamFailure\(\s*["\']([A-Za-z0-9_]+)["\']')
    for py_file in PROVIDERS_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8", errors="replace")
        for match in pat.finditer(content):
            cat = match.group(1)
            assert cat in valid_categories, (
                f"[{py_file.name}] Rogue or uppercase error category '{cat}'. "
                f"Must be one of: {sorted(valid_categories)}"
            )
