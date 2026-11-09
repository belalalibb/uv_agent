"""DeepAI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Closed capability keys projection to Gateway v1 (chat, vision_input, audio_input, file_upload, reasoning, code).
- Dynamic models population from models_metadata.json.
- Credential mode: platform (internal autonomous IslandKey calculation, zero user credential leakage).
- Strictly NO image_generation and NO browser capabilities declared.
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
    "display_name": "DeepAI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "vision_input": True,
        "audio_input": True,
        "file_upload": True,
        "reasoning": True,
        "code": True,
    },
    "operations": [
        "generate_text",
        "analyze_vision",
        "transcribe_audio",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
