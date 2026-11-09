#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dual-Agent Architecture Session Runner (Streamlined & WAF-Safe)
=============================================================
Conducts the interactive architectural session between Antigravity IDE and FreebuFF GLM 5.3 Flash.
Produces `DUAL_AGENT_COOPERATION_PROTOCOL_V2.md`.
"""

import sys
import os
import json
import time
import re
from pathlib import Path
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

GATEWAY_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = GATEWAY_DIR / "docs"
V1_PATH = DOCS_DIR / "DUAL_AGENT_COOPERATION_PROTOCOL_V1.md"
DIALOG_LOG_PATH = DOCS_DIR / "DUAL_AGENT_DIALOG_LOG.md"

sys.path.insert(0, str(GATEWAY_DIR))
from tools.continuous_glm_optimizer import get_cookie, clean_cookie, send_chat_stream

def extract_markdown(text: str) -> str:
    matches = list(re.finditer(r"```(?:markdown)?\s*\n(.*?)```", text, re.DOTALL))
    if matches:
        return matches[-1].group(1).strip()
    return text.strip()

def run_session():
    print("="*80)
    print("🤝 إطلاق جلسة التعاون المعماري الثنائي (Dual-Agent Collaboration Session)")
    print("🎯 المحاورون: Antigravity IDE (محلي) ⚡ FreebuFF GLM 5.3 Flash (سحابي)")
    print("="*80)
    
    session = requests.Session()
    session.headers.update({"Cookie": clean_cookie(get_cookie())})
    
    # فحص الجلسة
    print("\n📡 فحص جلسة FreebuFF...")
    chk = session.get("https://freebuff.com/api/auth/session", timeout=15)
    if chk.status_code == 200 and chk.json().get("user"):
        u = chk.json()["user"]
        print(f"✅ الجلسة نشطة ومصادق عليها: {u.get('email')}")
    else:
        print(f"⚠️ تحذير: الجلسة غير مصادق عليها: {chk.status_code}")
    
    # صياغة البرومبت المركز عالي الكثافة (Safe Byte-Budget < 6KB)
    prompt = (
        "تحية معمارية طيبة يا زميلي المعماري في FreebuFF،\n"
        "أنا Antigravity IDE Assistant، وكيل تحرير البرمجيات والتشغيل المحلي.\n"
        "أعمل بتوجيه مباشر من البروفيسور زيزو والباشمهندس بولا في مشروع AI Gateway Service.\n"
        "أنا أمتلك التيرمينال الحقيقي على Windows، والمتصفح الحي، وأدوات py_compile واختبارات الشبكة.\n"
        "وأنت تمثل محرك التفكير والتحليل العميق (Max Reasoning) وخبير تفكيك الـ HAR واستخراج الـ Payloads.\n\n"
        "قام زيزو وبولا باعتماد وتجميد الوثيقة التأسيسية DUAL_AGENT_COOPERATION_PROTOCOL_V1.md، "
        "والتي تنص على:\n"
        "1. سلطة القرار النهائي: الحكم ليس للأشخاص بل للأدلة التجريبية الميدانية في التيرمينال لدى Antigravity.\n"
        "2. خط أنابيب التوازي (Zero-Waiting Pipeline): توزيع المهام متدفقة ومحدش يستنى التاني.\n"
        "3. كسر عقدة دالة التسجيل register(): تكامل فحص المتصفح/DOM لدي مع قوة تفكيك الـ Regex والـ Payloads لديك وتمرير البارامترات.\n"
        "4. ميثاق حظر التخمين (قانون بولا 8): لا قرار ولا كود بدون دليل سطري صريح من الـ HAR أو العقد.\n\n"
        "المطلوب منك الآن في هذه الجلسة المعمارية:\n"
        "بصفتك كبير المستشارين المعماريين، قم بصياغة وإخراج الوثيقة المطورة المعتمدة رسمياً بيننا كنسخة ثانية كاملة:\n"
        "`DUAL_AGENT_COOPERATION_PROTOCOL_V2.md`\n"
        "بحيث تشتمل على:\n"
        "- ميثاق التوأمة والتعاون بين الوكيلين والمسؤوليات التفصيلية لكل طرف.\n"
        "- بروتوكول تمرير البارامترات (Parameter Passing Schema) في دالة الـ register والـ ask.\n"
        "- جدول مصفوفة اتخاذ القرار وفض النزاع عند التعارض.\n"
        "- خطة العمل التتابعي دالة بدالة لتطوير مزود FreebuFF من واقع الـ HAR الرابع.\n"
        "- معايير الجودة والتسليم وقائمة التحقق Acceptance Checklist.\n\n"
        "اكتب الوثيقة v2.0 كاملة، متكاملة، شاملة، بصياغة RFC 2119 الصارمة، داخل بلوك كود: ```markdown ... ```"
    )
    
    print(f"\n📢 إرسال البرومبت المعماري (حجم النص: {len(prompt)} حرف)...")
    start_t = time.time()
    answer, reasoning, thread_id = send_chat_stream(session, prompt)
    elapsed = (time.time() - start_t) / 60
    print(f"\n⏱️ استغرقت الجلسة المعمارية: {elapsed:.2f} دقيقة.")
    
    v2_content = extract_markdown(answer)
    V2_PATH.write_text(v2_content, encoding="utf-8")
    print(f"\n💾 [تم حفظ الوثيقة بنجاح]: {V2_PATH} ({len(v2_content):,} bytes)")
    
    log_entry = (
        f"# 🤝 سجل حوار التوأمة المعمارية بين Antigravity و FreebuFF GLM 5.3 Flash\n"
        f"**التاريخ:** سبتمبر 2026 | **المدة:** {elapsed:.2f} دقيقة | **Thread ID:** {thread_id}\n\n"
        f"## 1. برومبت Antigravity IDE:\n\n{prompt}\n\n"
        f"## 2. تفكير الوكيل الخارجي (Reasoning):\n\n{reasoning}\n\n"
        f"## 3. الرد المعماري والوثيقة v2.0 الناتجة:\n\n{answer}\n"
    )
    DIALOG_LOG_PATH.write_text(log_entry, encoding="utf-8")
    print(f"📝 [تم تدوين سجل الحوار كاملاً في]: {DIALOG_LOG_PATH}")
    print("\n🎉 اكتملت الجلسة المعمارية بنجاح 100%!")

if __name__ == "__main__":
    run_session()
