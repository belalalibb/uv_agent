# -*- coding: utf-8 -*-
"""Provider Definition for RunPod Console Assistant.

Exposes OpenAI GPT-4 class capabilities via RunPod's web console assistant.
Supports text generation, file attachment comprehension, and vision analysis.
Credential mode: platform (session managed internally).
"""

DEFINITION: dict[str, object] = {
    "display_name": "RunPod Console Assistant",
    "definition_version": "1.1.0",
    "credential_mode": "platform",
    "capabilities": {
        "chat": True,
        "reasoning": True,
        "code": True,
        "vision_input": True,
        "file_upload": True,
    },
    "operations": ["generate_text", "analyze_vision"],
    "models": [
        {"name": "runpod-console-gpt4", "context_window": 128000},
        {"name": "runpod-console-vision", "context_window": 128000},
        {"name": "default", "context_window": 128000},
    ],
    "health_supported": False,
}
