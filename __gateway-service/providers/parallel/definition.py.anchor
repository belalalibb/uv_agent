#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parallel AI — definition.py | البطاقة الرسمية للمزود في بوابة الجيتواي"""
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
    "display_name": "Parallel AI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "reasoning": True,
        "code": True,
        "vision_input": False,
        "image_generation": False,
        "audio_input": False,
        "audio_output": False,
        "file_upload": False,
        "browser": False,
        "agent_module": True,
        "tool_use": True,
    },
    "operations": [
        "generate_text",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": True,
}
