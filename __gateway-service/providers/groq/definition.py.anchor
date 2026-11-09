"""Groq DEFINITION — the provider's official declaration (deny-by-default).

The registry trusts ONLY this declaration — never code introspection.
G3 scope: ``generate_text`` ONLY; models dynamically populated from metadata.
``health_supported`` is False — no upstream health probe is implemented.
"""

from __future__ import annotations

import json
from pathlib import Path

_METADATA_PATH = Path(__file__).resolve().parent / "models_metadata.json"

try:
    with open(_METADATA_PATH, "r", encoding="utf-8") as _f:
        _MODELS_DATA: dict[str, dict] = json.load(_f)
except Exception:
    _MODELS_DATA = {}

_DECLARED_MODELS: list[dict[str, object]] = [
    {"name": m_id, "context_window": m_meta.get("context_window")}
    for m_id, m_meta in _MODELS_DATA.items()
]

DEFINITION: dict[str, object] = {
    "display_name": "Groq",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {"chat": True, "reasoning": True, "code": True},
    "operations": ["generate_text"],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
