"""Syntx AI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & UNIVERSAL_PROVIDER_SPEC_AND_BLUEPRINT.md
- Closed capability keys projection to Gateway v1 (chat, vision_input, reasoning, code, browser).
- Dynamic models population from models_metadata.json (preserving all 28 free upstream models).
- Credential mode: platform (internal accounts pool management).
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
    {"name": m_id} for m_id in _MODELS_DATA
]

DEFINITION: dict[str, object] = {
    "display_name": "Syntx AI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "vision_input": True,
        "reasoning": True,
        "code": True,
        "browser": True,
    },
    "operations": [
        "generate_text",
        "analyze_vision",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
