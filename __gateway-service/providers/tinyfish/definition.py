"""TinyFish AI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & ADR-0008.
- Closed capability keys projection to Gateway v1 (chat, reasoning, browser, vision_input, tool_use, agent_module).
- Dynamic models population from models_metadata.json.
- Credential mode: platform (internal accounts pool with Zero-Browser pure registration).
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
    "display_name": "TinyFish AI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "reasoning": True,
        "browser": True,
        "vision_input": True,
        "tool_use": True,
        "agent_module": True,
    },
    "operations": [
        "generate_text",
        "analyze_vision",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
