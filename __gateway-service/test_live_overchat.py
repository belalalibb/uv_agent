#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Live Verification Test for Overchat Gateway Adapter
==================================================
Tests all canonical operations end-to-end:
1. Text Generation: gpt-6-luna
2. Text Generation: gemini-3.8-flash
3. Vision Analysis: analyze_vision with S3 upload (test_sample.png)
4. Audio Transcription: transcribe_audio via /v1/transcript (.ogg)
"""

import asyncio
import base64
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

GATEWAY_DIR = Path(__file__).resolve().parent
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from gateway.contracts import CredentialMode, GatewayOperation, ProviderContext
from providers.overchat.adapter import HANDLERS, generate_text, analyze_vision, transcribe_audio
from providers.overchat.definition import DEFINITION


async def main():
    print("=" * 75)
    print("🚀 بدء الاختبار الميداني الحي الشامل لمزود Overchat بكافة قدراته (Text + Vision + Audio)")
    print("=" * 75)

    # 1. فحص مطابقة عقد البوابة
    print("\n1. فحص مطابقة عقد البوابة (Definition & Handlers)...")
    print(f"   [+] Display Name: {DEFINITION['display_name']}")
    print(f"   [+] Handlers: {[op.value for op in HANDLERS.keys()]}")
    print(f"   [+] Models Count: {len(DEFINITION['models'])}")
    print(f"   [+] Capabilities: {DEFINITION['capabilities']}")

    # 2. إرسال طلب محادثة حقيقي عبر الـ Adapter مع GPT-6 Luna
    print("\n2. اختبار توليد نص حي عبر الـ Adapter (GPT-6 Luna)...")
    ctx_text1 = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        credential_mode=CredentialMode.PLATFORM,
        model="gpt-6-luna",
        request_id="req-live-overchat-luna",
        tenant_id="tenant-test",
        payload={
            "messages": [
                {"role": "user", "content": "ما هو حاصل ضرب 12 في 12؟ أجب بالمصري باختصار شديد."}
            ],
            "temperature": 0.5,
        },
        timeout_ms=30000,
    )

    res_text1 = await generate_text(ctx_text1)
    print(f"   [+] Succeeded: {res_text1.succeeded}")
    if res_text1.succeeded:
        print(f"   [+] Output Text: {res_text1.output.get('text')}")
        print(f"   [+] Finish Reason: {res_text1.output.get('finish_reason')}")
        print(f"   [+] Usage: in={res_text1.usage.input_tokens}, out={res_text1.usage.output_tokens}, units={res_text1.usage.units}")
    else:
        print(f"   [-] Error: {res_text1.error.category} - {res_text1.error.message}")
    assert res_text1.succeeded, "Live inference for GPT-6 Luna failed"

    # 3. اختبار توليد نص حي عبر الـ Adapter لموديل إضافي (Gemini 3.8 Flash)
    print("\n3. اختبار توليد نص حي عبر الـ Adapter (Gemini 3.8 Flash)...")
    ctx_text2 = ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        credential_mode=CredentialMode.PLATFORM,
        model="gemini-3.8-flash",
        request_id="req-live-overchat-gemini",
        tenant_id="tenant-test",
        payload={
            "messages": [
                {"role": "user", "content": "ما هي عاصمة فرنسا؟ كلمة واحدة فقط."}
            ],
            "temperature": 0.3,
        },
        timeout_ms=30000,
    )

    res_text2 = await generate_text(ctx_text2)
    print(f"   [+] Succeeded: {res_text2.succeeded}")
    if res_text2.succeeded:
        print(f"   [+] Output Text: {res_text2.output.get('text')}")
        print(f"   [+] Finish Reason: {res_text2.output.get('finish_reason')}")
        print(f"   [+] Usage: in={res_text2.usage.input_tokens}, out={res_text2.usage.output_tokens}, units={res_text2.usage.units}")
    else:
        print(f"   [-] Error: {res_text2.error.category} - {res_text2.error.message}")
    assert res_text2.succeeded, "Live inference for Gemini failed"

    # 4. اختبار تحليل الصور (Vision) عبر رفع S3 والـ SSE Stream
    print("\n4. اختبار تحليل الرؤية (Vision) حياً عبر الـ Adapter...")
    img_path = GATEWAY_DIR / "tests" / "fixtures" / "test_sample.png"
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("ascii")

    ctx_vision = ProviderContext(
        operation=GatewayOperation.ANALYZE_VISION,
        credential_mode=CredentialMode.PLATFORM,
        model="gpt-6-luna",
        request_id="req-live-overchat-vision",
        tenant_id="tenant-test",
        payload={
            "image_b64": img_b64,
            "image_format": "png",
            "instruction": "اقرأ النص المكتوب في الصورة بدقة.",
        },
        timeout_ms=35000,
    )

    res_vision = await analyze_vision(ctx_vision)
    print(f"   [+] Succeeded: {res_vision.succeeded}")
    if res_vision.succeeded:
        print(f"   [+] Vision Output Text: {res_vision.output.get('text')}")
        print(f"   [+] Usage: in={res_vision.usage.input_tokens}, out={res_vision.usage.output_tokens}, units={res_vision.usage.units}")
    else:
        print(f"   [-] Error: {res_vision.error.category} - {res_vision.error.message}")
    assert res_vision.succeeded, "Live Vision Analysis failed"

    # 5. اختبار تحويل الصوت إلى نص (Audio Transcription) عبر /v1/transcript
    print("\n5. اختبار تحويل الصوت إلى نص (Audio Transcription) حياً عبر الـ Adapter...")
    audio_path = GATEWAY_DIR / "tests" / "fixtures" / "sample_audio.ogg"
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("ascii")

    ctx_audio = ProviderContext(
        operation=GatewayOperation.TRANSCRIBE_AUDIO,
        credential_mode=CredentialMode.PLATFORM,
        model="whisper",
        request_id="req-live-overchat-audio",
        tenant_id="tenant-test",
        payload={
            "audio_b64": audio_b64,
            "audio_format": "ogg",
        },
        timeout_ms=35000,
    )

    res_audio = await transcribe_audio(ctx_audio)
    print(f"   [+] Succeeded: {res_audio.succeeded}")
    if res_audio.succeeded:
        print(f"   [+] Audio Transcript: {res_audio.output.get('text')}")
        print(f"   [+] Detected Language: {res_audio.output.get('language')}")
        print(f"   [+] Usage units: {res_audio.usage.units}")
    else:
        print(f"   [-] Error: {res_audio.error.category} - {res_audio.error.message}")
    assert res_audio.succeeded, "Live Audio Transcription failed"

    print("\n" + "=" * 75)
    print("🎉 تم اجتياز الاختبار الحي الكامل بنجاح 100% لكافة العمليات:")
    print("   [1] Text Generation (gpt-6-luna) -> PASSED")
    print("   [2] Text Generation (gemini-3.8-flash) -> PASSED")
    print("   [3] Multimodal Vision Analysis -> PASSED")
    print("   [4] Speech-to-Text Audio Transcription -> PASSED")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(main())
