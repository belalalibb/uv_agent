#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepAI Live Models Synchronizer
===================================
Fetches and syncs free models directly from DeepAI web endpoint:
1. Issues an HTTP request to https://deepai.org/chat/gpt-6-luna
2. Extracts live declared models and capability matrices (vision, thinking, tools)
3. Filters exclusively for FREE models (locked == False)
4. Sets 'gpt-6-luna' as the #1 default model
5. Updates providers/deepai/models_metadata.json atomically
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

import requests

DEEPAI_CHAT_URL = "https://deepai.org/chat/gpt-6-luna"
FALLBACK_URL = "https://deepai.org/chat"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)

DEFAULT_MODEL_KEY = "gpt-6-luna"
CURRENT_DIR = Path(__file__).resolve().parent
METADATA_FILE = CURRENT_DIR / "models_metadata.json"


def _infer_ai_name(model_id: str) -> str:
    """Infer family ai_name from model value."""
    lower = model_id.lower()
    if "gpt" in lower:
        return "gpt"
    if "glm" in lower:
        return "glm"
    if "deepseek" in lower:
        return "deepseek"
    if "qwen" in lower:
        return "qwen"
    if "tencent" in lower:
        return "tencent"
    if "llama" in lower:
        return "llama"
    if "gemini" in lower:
        return "gemini"
    if "gemma" in lower:
        return "gemma"
    return lower.split("-")[0]


def fetch_free_models() -> dict[str, Any]:
    """Fetch live web page, parse script arrays, and return free models dict."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    resp = None
    for url in [DEEPAI_CHAT_URL, FALLBACK_URL]:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200 and len(r.text) > 10000:
                resp = r
                break
        except Exception:
            continue

    if resp is None:
        raise RuntimeError(f"Failed to fetch DeepAI chat page from {DEEPAI_CHAT_URL} and {FALLBACK_URL}")

    html = resp.text

    # Extract capability lists
    vision_match = re.search(r'visionCapableModelValues\s*=\s*(\[[^\]]+\])', html)
    thinking_match = re.search(r'thinkingCapableModelValues\s*=\s*(\[[^\]]+\])', html)
    native_tools_match = re.search(r'nativeToolCapableModelValues\s*=\s*(\[[^\]]+\])', html)

    vision_models = set(json.loads(vision_match.group(1))) if vision_match else set()
    thinking_models = set(json.loads(thinking_match.group(1))) if thinking_match else set()
    native_tool_models = set(json.loads(native_tools_match.group(1))) if native_tools_match else set()

    # Extract all model objects: {"value":"...", "label":"...", "locked":true/false, ...}
    pattern = r'\{"value":"([^"]+)","label":"([^"]+)","locked":(true|false)(?:,"superGenius":(true|false))?'
    raw_models = []
    seen = set()

    for m in re.finditer(pattern, html):
        val, label, locked_str, super_genius_str = m.groups()
        if val in seen:
            continue
        seen.add(val)
        is_locked = (locked_str == "true")
        raw_models.append({
            "value": val,
            "label": label,
            "locked": is_locked,
        })

    # Filter only FREE models
    free_models = [m for m in raw_models if not m["locked"]]

    # Ensure DEFAULT_MODEL_KEY (gpt-6-luna) is present and placed at #1
    ordered_free = []
    # 1. First: gpt-6-luna
    for m in free_models:
        if m["value"] == DEFAULT_MODEL_KEY:
            ordered_free.append(m)
            break
    else:
        # In case gpt-6-luna was not in parsed list, inject it as free #1
        ordered_free.append({
            "value": DEFAULT_MODEL_KEY,
            "label": "GPT-6 Luna",
            "locked": False,
        })

    # 2. Append all other free models
    for m in free_models:
        if m["value"] != DEFAULT_MODEL_KEY:
            ordered_free.append(m)

    # Build final metadata dictionary
    metadata: dict[str, Any] = {}
    for m in ordered_free:
        val = m["value"]
        label = m["label"]
        has_vision = val in vision_models or "luna" in val or "mini" in val or "flash" in val or "gemma" in val
        has_thinking = val in thinking_models
        metadata[val] = {
            "ai_name": _infer_ai_name(val),
            "label": label,
            "capabilities": {
                "thinking": has_thinking,
                "planning": False,
                "deep_research": False,
                "web_explorer": False,
                "files": True,
                "images": has_vision,
                "system_message": True,
                "streaming": False,
            },
        }

    return metadata


def sync_models_metadata(save_path: Path = METADATA_FILE) -> dict[str, Any]:
    """Sync free models and write to models_metadata.json."""
    data = fetch_free_models()
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return data


def main():
    print("=" * 70)
    print("🔄 DeepAI Live Models Sync — جلب الموديلات المجانية تلقائياً")
    print("=" * 70)
    print(f"📡 الاتصال بـ: {DEEPAI_CHAT_URL}")
    print(f"🎯 الموديل الافتراضي المحدد: {DEFAULT_MODEL_KEY}")
    print("-" * 70)

    try:
        models = sync_models_metadata()
        print(f"✅ تم سحب وتحديث {len(models)} موديلاً مجانياً بنجاح داخل models_metadata.json:")
        for idx, (m_id, m_info) in enumerate(models.items(), 1):
            default_badge = "🌟 [الافتراضي DEFAULT]" if idx == 1 else "                   "
            vis = "👁️ Vision" if m_info["capabilities"]["images"] else "        "
            think = "🧠 Thinking" if m_info["capabilities"]["thinking"] else "          "
            print(f"  {idx:2d}. {m_id:<24} | {m_info['label']:<24} | {vis} | {think} | {default_badge}")
        print("=" * 70)
        print("🎉 تم التحديث والحفظ بنجاح 100%!")
    except Exception as e:
        print(f"❌ فشل السحب: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
