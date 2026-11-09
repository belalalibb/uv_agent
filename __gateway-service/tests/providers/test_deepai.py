"""DeepAI Provider Facade & Integration Tests.

Compliance: Bolla Constitution v1.2 & Gateway Contracts ADR-0008.
- Tests Layer 3 parity (DEFINITION <-> HANDLERS).
- Tests Layer 2 facade translation and input validation.
- Tests IslandKey generation logic.
- Tests live text generation, vision analysis, audio transcription, and file attachment handling.
"""

import base64
import io
import wave
import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
    ProviderDefinition,
)
from providers.deepai import DEFINITION
from providers.deepai.adapter import HANDLERS, analyze_vision, generate_text, transcribe_audio
from providers.deepai import _core


# 1x1 transparent PNG base64
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1cAAAAASUVORK5CYII="


def build_context(payload=None, operation=GatewayOperation.GENERATE_TEXT, **overrides) -> ProviderContext:
    data = dict(
        operation=operation,
        model="gpt-6-luna",
        request_id="req-deepai-test",
        tenant_id="tenant-deepai-test",
        credential_mode=CredentialMode.PLATFORM,
        timeout_ms=15000,
        payload={"messages": [{"role": "user", "content": "say ok"}]} if payload is None else payload,
    )
    return ProviderContext(**(data | overrides))


def test_deepai_definition_contract():
    """DEFINITION parses as valid ProviderDefinition with closed capability keys."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert parsed.display_name == "DeepAI"
    assert parsed.credential_mode is CredentialMode.PLATFORM
    assert parsed.health_supported is False
    assert len(parsed.models) >= 10
    # First model must be the default gpt-6-luna
    assert parsed.models[0].name == "gpt-6-luna"
    model_names = [m.name for m in parsed.models]
    assert "gpt-6-luna" in model_names
    assert "gpt-5.6-luna" in model_names
    assert "glm-5.3-flash" in model_names
    assert "deepseek-v4-flash" in model_names
    assert "tencent-hy3" in model_names
    assert "qwen3.8-flash" in model_names
    # Verify locked/pro models are NOT in free models
    assert "claude-opus-5-5" not in model_names
    assert "gpt-5.6-terra" not in model_names
    assert "genius" not in model_names
    # Verify image_generation and browser are not declared/enabled
    assert not parsed.capabilities.get("image_generation", False)
    assert not parsed.capabilities.get("browser", False)


def test_deepai_handlers_parity():
    """Every declared operation must have a matching handler in adapter.py."""
    parsed = ProviderDefinition.model_validate(DEFINITION)
    assert set(parsed.operations) == set(HANDLERS)


def test_deepai_island_key_generation():
    """IslandKey algorithm generates valid tryit- format with MD5 reverse."""
    key = _core.generate_island_key()
    assert key.startswith("tryit-")
    parts = key.split("-")
    assert len(parts) == 3
    assert parts[1].isdigit()
    assert len(parts[2]) == 32  # MD5 hex length


@pytest.mark.asyncio
async def test_deepai_credential_protection():
    """Passing caller credentials must fail as INVALID_CREDENTIAL."""
    ctx = build_context(credential_mode=CredentialMode.USER_KEY, credential_value="user-secret-123")
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.INVALID_CREDENTIAL


@pytest.mark.asyncio
async def test_deepai_payload_validation():
    """Malformed payload triggers BAD_REQUEST."""
    ctx = build_context(payload={"messages": []})
    res = await generate_text(ctx)
    assert not res.succeeded
    assert res.error.category is ErrorCategory.BAD_REQUEST

    ctx_vis = build_context(operation=GatewayOperation.ANALYZE_VISION, payload={})
    res_vis = await analyze_vision(ctx_vis)
    assert not res_vis.succeeded
    assert res_vis.error.category is ErrorCategory.BAD_REQUEST

    ctx_aud = build_context(operation=GatewayOperation.TRANSCRIBE_AUDIO, payload={})
    res_aud = await transcribe_audio(ctx_aud)
    assert not res_aud.succeeded
    assert res_aud.error.category is ErrorCategory.BAD_REQUEST


@pytest.mark.external
@pytest.mark.asyncio
async def test_live_generate_text_luna():
    """Live text generation test using default gpt-6-luna."""
    ctx = build_context(
        model="gpt-6-luna",
        payload={"messages": [{"role": "user", "content": "Reply with 'Luna says hello' only."}]},
    )
    res = await generate_text(ctx)
    assert res.succeeded
    assert res.output is not None
    assert "Luna" in res.output["text"] or len(res.output["text"]) > 0
    assert res.output.get("session_id") is not None


@pytest.mark.external
@pytest.mark.asyncio
async def test_live_generate_text_thinking_glm():
    """Live text generation test using glm-5.3-flash (supports thinking polling)."""
    ctx = build_context(
        model="glm-5.3-flash",
        payload={"messages": [{"role": "user", "content": "Calculate 15 + 27. Answer with number only."}]},
        timeout_ms=25000,
    )
    res = await generate_text(ctx)
    assert res.succeeded
    assert res.output is not None
    assert "42" in res.output["text"]


@pytest.mark.external
@pytest.mark.asyncio
async def test_live_file_attachment_code():
    """Live test attaching a Python file to chat conversation using gpt-6-luna."""
    python_code = "def get_secret():\n    return 4242\n"
    ctx = build_context(
        model="gpt-6-luna",
        payload={
            "messages": [{"role": "user", "content": "What is the return value of get_secret() in the attached file?"}],
            "files": [
                {
                    "name": "calc.py",
                    "content": python_code,
                    "is_base64": False,
                }
            ],
        },
    )
    res = await generate_text(ctx)
    assert res.succeeded
    assert "4242" in res.output["text"]


@pytest.mark.external
@pytest.mark.asyncio
async def test_live_analyze_vision():
    """Live vision analysis test using analyze_vision handler with gpt-6-luna."""
    ctx = build_context(
        operation=GatewayOperation.ANALYZE_VISION,
        model="gpt-6-luna",
        payload={
            "image_b64": TINY_PNG_B64,
            "image_format": "png",
            "instruction": "Describe this small image briefly.",
        },
    )
    res = await analyze_vision(ctx)
    assert res.succeeded
    assert res.output is not None
    assert len(res.output.get("text", "")) > 0


@pytest.mark.external
@pytest.mark.asyncio
async def test_live_transcribe_audio():
    """Live speech-to-text test using transcribe_audio handler."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    buf.seek(0)
    audio_b64 = base64.b64encode(buf.read()).decode("ascii")

    ctx = build_context(
        operation=GatewayOperation.TRANSCRIBE_AUDIO,
        model="default",
        payload={
            "audio_b64": audio_b64,
            "audio_format": "wav",
        },
        timeout_ms=10000,
    )
    res = await transcribe_audio(ctx)
    if res.succeeded:
        assert "text" in res.output
    else:
        assert res.error.category in (
            ErrorCategory.TIMEOUT,
            ErrorCategory.PROVIDER_UNAVAILABLE,
            ErrorCategory.RETRYABLE_SERVER_ERROR,
        )


@pytest.mark.external
def test_deepai_sync_models_free_list():
    """Test that sync_models fetches free models with gpt-6-luna as the #1 default."""
    from providers.deepai.sync_models import fetch_free_models
    data = fetch_free_models()
    assert len(data) >= 10
    keys = list(data.keys())
    assert keys[0] == "gpt-6-luna"
    assert "standard" in data
    assert "glm-5.3-flash" in data
    assert "deepseek-v4-flash" in data
