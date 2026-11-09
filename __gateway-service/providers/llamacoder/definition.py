"""LlamaCoder Together AI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Closed capability keys projection to Gateway v1 (chat, vision_input, file_upload, reasoning, code).
- Dynamic models population from models_metadata.json with 1M context windows.
- Credential mode: platform (zero cookies, zero tokens, pure anonymous HTTP requests).
- Strictly NO audio_input (upstream rejects audio with 415), NO image_generation, NO browser capabilities.
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
    {
        "name": m_id,
        "context_window": meta.get("context_window"),
    }
    for m_id, meta in _MODELS_DATA.items()
]

DEFINITION: dict[str, object] = {
    "display_name": "LlamaCoder Together AI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "vision_input": True,
        "audio_input": False,
        "file_upload": True,
        "reasoning": True,
        "code": True,
    },
    "operations": [
        "generate_text",
        "analyze_vision",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": True,
}
