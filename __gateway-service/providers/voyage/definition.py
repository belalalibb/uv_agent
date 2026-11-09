"""Voyage AI DEFINITION — Canonical Provider Declaration for Gateway v1.

Compliance: Bolla Constitution v1.2 & ADR-0008.
- Specialized vector embedding and semantic reranking provider.
- Declared operations: create_embeddings, rerank_documents.
- Dynamic models population from models_metadata.json.
- Closed capability keys: embeddings, rerank, code, vision_input, file_upload.
- Credential mode: platform (internal accounts pool with multi-key rotation).
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
    "display_name": "Voyage AI",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {
        "embeddings": True,
        "rerank": True,
        "code": True,
        "vision_input": True,
        "file_upload": True,
    },
    "operations": [
        "create_embeddings",
        "rerank_documents",
    ],
    "models": _DECLARED_MODELS,
    "health_supported": False,
}
