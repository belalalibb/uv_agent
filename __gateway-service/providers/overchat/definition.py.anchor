"""Overchat AI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & ADR-0008.
- Closed capability keys projection to Gateway v1 (chat, reasoning, code, vision_input, audio_input, file_upload).
- Dynamic models population from models_metadata.json (8 free models suite).
- Multi-operation support: generate_text, analyze_vision, transcribe_audio.
- Credential mode: platform (zero-browser OkHttp mobile emulation, autonomous anonymous user auth).
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
    {"name": m_id, "context_window": m_meta.get("context_window", 128000)}
    for m_id, m_meta in _MODELS_DATA.items()
]

DEFINITION: dict[str, object] = {
    "display_name": "Overchat AI",
    "definition_version": "1.1.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "reasoning": True,
        "code": True,
        "vision_input": True,
        "audio_input": True,
        "file_upload": True,
    },
    "operations": [
        "generate_text",
        "analyze_vision",
        "transcribe_audio",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
