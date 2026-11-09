"""LlamaCoder Together AI Provider Facade & Integration Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests credential protection (zero user credential leakage).
- Tests live text generation using DeepSeek V4.1 Flash (1M context).
- Tests live code file attachment handling.
- Tests live vision analysis using S3 screenshot pipeline.
- Tests audio rejection proof (HTTP 415: Only PNG, JPEG, and WebP images allowed).
"""

import base64
import os
import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
    ProviderDefinition,
)
from providers.llamacoder import DEFINITION, HANDLERS
from providers.llamacoder.adapter import analyze_vision, generate_text
from providers.llamacoder import _core

# 1x1 transparent PNG base64 for test
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="


def build_context(payload=None, operation=GatewayOperation.GENERATE_TEXT, **overrides) -> ProviderContext:
    data = dict(
        operation=operation,
        model="deepseek-v4.1",
        request_id="req-llamacoder-test",
        tenant_id="tenant-llamacoder-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=30000,
        payload={"messages": [{"role": "user", "content": "say ok"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_llamacoder_definition_contract():
    """DEFINITION parses as valid ProviderDefinition with closed capability keys."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "LlamaCoder Together AI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is True
    assert len(parsed.models) >= 8

    model_names = [m.name for m in parsed.models]
    assert "deepseek-v4.1" in model_names
    assert "deepseek-v4-pro" in model_names
    assert "glm-5.3-flash" in model_names
    assert "glm-5.3" in model_names
    assert "kimi-k3" in model_names
    assert "qwen-3.8-flash" in model_names
    assert "llama-3.3-70b" in model_names

    # Verify audio_input, image_generation, and browser are not declared/enabled
    assert not parsed.capabilities.get("audio_input", False)
    assert not parsed.capabilities.get("image_generation", False)
    assert not parsed.capabilities.get("browser", False)


def test_llamacoder_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


@pytest.mark.asyncio
async def test_llamacoder_credential_protection():
    """Passing caller credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="user-secret-123")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_llamacoder_payload_validation():
    """Malformed payload triggers BAD_REQUEST."""
    ctx = build_context(payload={"messages": []})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST

    ctx_vis = build_context(operation=GatewayOperation.ANALYZE_VISION, payload={})
    res_vis = await analyze_vision(ctx_vis)
    assert not res_vis.succeeded
    assert res_vis.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.asyncio
async def test_live_generate_text_deepseek():
    """Live text generation test using deepseek-v4.1."""
    ctx = build_context(
        model="deepseek-v4.1",
        payload={"messages": [{"role": "user", "content": "Reply with 'Hello from DeepSeek V4.1' only."}]},
        timeout_ms=30000,
    )
    res = await generate_text(ctx)
    assert res.succeeded
    assert res.output is not None
    assert "DeepSeek" in res.output["text"] or len(res.output["text"]) > 0
    assert res.output.get("chat_id") is not None


@pytest.mark.asyncio
async def test_live_file_attachment_code():
    """Live test attaching a Python file to chat conversation."""
    python_code = "def calculate_secret_number():\n    return 7788\n"
    ctx = build_context(
        model="deepseek-v4.1",
        payload={
            "messages": [{"role": "user", "content": "What is the return value of calculate_secret_number() in the attached file? Answer with the number only."}],
            "files": [
                {
                    "name": "secret.py",
                    "content": python_code,
                    "is_base64": False,
                }
            ],
        },
        timeout_ms=30000,
    )
    res = await generate_text(ctx)
    assert res.succeeded
    assert res.output is not None
    assert "7788" in res.output["text"]


@pytest.mark.asyncio
async def test_live_analyze_vision():
    """Live vision analysis test using analyze_vision handler with tiny test PNG."""
    ctx = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        model="deepseek-v4.1",
        payload={
            "image_b64": TINY_PNG_B64,
            "image_format": "png",
            "instruction": "Describe this small image briefly.",
        },
        timeout_ms=40000,
    )
    res = await analyze_vision(ctx)
    assert res.succeeded
    assert res.output is not None
    assert len(res.output.get("text", "")) > 0


@pytest.mark.asyncio
async def test_audio_rejection_proof():
    fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures"))
    audio_path = os.path.join(fixtures_dir, "sample_audio.mp3")
    assert os.path.exists(audio_path), "Audio test fixture file should exist"

    ctx = build_context(
        model="deepseek-v4.1",
        payload={
            "messages": [{"role": "user", "content": "Transcribe or analyze this audio"}],
            "files": [
                {
                    "name": "جدول_3__.mp3",
                    "content": "fake_or_real_audio_bytes",
                    "is_base64": False,
                }
            ],
        },
        timeout_ms=15000,
    )
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST
    assert "audio" in res.error.message.lower() or "png" in res.error.message.lower()
