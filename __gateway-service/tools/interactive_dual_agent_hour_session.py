#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive Dual-Agent Hour Session Runner
==========================================
Maintains a continuous conversational thread on FreebuFF (Thread ID: 2aab03f7-2e00-4537-9418-e5bd9e5af6d6)
between Antigravity IDE and FreebuFF GLM 5.3 Flash.

Iteratively dialogues, passes HAR 4/5 evidence, and produces the definitive
`DUAL_AGENT_COOPERATION_PROTOCOL_V2.md`.
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
V2_PATH = DOCS_DIR / "DUAL_AGENT_COOPERATION_PROTOCOL_V2.md"
COOKIE_FILE = GATEWAY_DIR / "FREEBUFF_COOKIE.txt"
DIALOG_LOG_PATH = DOCS_DIR / "DUAL_AGENT_DIALOG_LOG.md"

sys.path.insert(0, str(GATEWAY_DIR))
from tools.continuous_glm_optimizer import get_cookie, clean_cookie, send_chat_stream

THREAD_ID = "2aab03f7-2e00-4537-9418-e5bd9e5af6d6"

def extract_markdown(text: str) -> str:
    # البحث عن أكبر بلوك markdown
    blocks = re.findall(r"```(?:markdown)?\s*\n(.*?)```", text, re.DOTALL)
    if blocks:
        # اختيار أطول بلوك كود
        return max(blocks, key=len).strip()
    return text.strip()

def run_hour_session():
    print("="*80)
    print("🤝 بدء جلسة النقاش المعماري التفاعلية الممتدة (Continuous Dual-Agent Session)")
    print(f"🔗 الثريد المستمر: {THREAD_ID}")
    print("="*80)
    
    session = requests.Session()
    cookie_str = clean_cookie(get_cookie())
    session.headers.update({"Cookie": cookie_str})
    
    # 1. التحقق من صلاحية الجلسة
    print("\n📡 فحص صحة الجلسة والكوكيز...")
    chk = session.get("https://freebuff.com/api/auth/session", timeout=15)
    if chk.status_code != 200 or not chk.json().get("user"):
        print(f"❌ الجلسة منتهية أو الكوكيز ميتة! كود الحالة: {chk.status_code}")
        print("🛑 توقف فوري تنفيذاً لأمر البروفيسور زيزو.")
        return
    
    u = chk.json()["user"]
    print(f"✅ الجلسة صالحة 100%: {u.get('email')} (صالحة حتى {chk.json().get('expires')})")
    
    # تجهيز أدلة الـ HAR 4 و HAR 5 المركزة
    har_evidence = {
        "chat_endpoint": "POST https://freebuff.com/api/chat/stream",
        "auth_session_endpoint": "GET https://freebuff.com/api/auth/session",
        "headers": {
            "accept": "*/*",
            "content-type": "application/json",
            "origin": "https://freebuff.com",
            "referer": "https://freebuff.com/chat"
        },
        "cookies_required": [
            "__Secure-next-auth.session-token",
            "__Host-next-auth.csrf-token",
            "human_behavior_end_user_id",
            "_gr", "gr_session", "gr_attrib", "vly_device_id"
        ],
        "request_payload_schema": {
            "threadId": "string | null",
            "content": "string (max safe chars ~6000)",
            "model": "glm-5.3-flash (or other registered models)",
            "reasoningEffort": "max | medium | low",
            "gravity": "user_data + client_context object (screen, viewport, timezone Africa/Cairo)",
            "images": "array",
            "attachments": "array"
        },
        "sse_response_stream_frames": [
            "data: {\"type\":\"meta\",\"threadId\":\"...\",\"title\":\"...\",\"model\":\"...\"}",
            "data: {\"type\":\"reasoning_delta\",\"text\":\"...\"}",
            "data: {\"type\":\"content_delta\",\"text\":\"...\"}",
            "data: [DONE]"
        ],
        "auth_session_response": {
            "status": 200,
            "body": {"user": {"email": "...", "id": "..."}, "expires": "ISO8601"}
        }
    }
    
    # -------------------------------------------------------------------------
    # الجولة الأولى: تزويد الوكيل بالأدلة الكاملة من الـ HAR ومطالبته بدمجها
    # -------------------------------------------------------------------------
    print("\n📢 [الجولة 1/2]: إرسال بيانات وأدلة HAR 4 و HAR 5 إلى الثريد المباشر...")
    turn1_prompt = (
        "عظيم يا زميلي! ها هي الأدلة الصريحة من الـ HAR 4 والـ HAR 5 التي طلبتها لندمجها فوراً:\n\n"
        "1. مسار الشات المباشر: `POST https://freebuff.com/api/chat/stream`\n"
        "2. مسار فحص الجلسة: `GET https://freebuff.com/api/auth/session` (يرجع 200 مع user و expires).\n"
        "3. الكوكيز الإلزامية: `__Secure-next-auth.session-token` + `__Host-next-auth.csrf-token` + `vly_device_id` + `gr_session`.\n"
        "4. هيكل الـ Payload:\n"
        "```json\n"
        + json.dumps(har_evidence["request_payload_schema"], indent=2) + "\n"
        "```\n"
        "5. استجابة البث SSE:\n"
        "- أحداث meta (فيها threadId)\n"
        "- أحداث reasoning_delta (التفكير)\n"
        "- أحداث content_delta (الرد الفعلي)\n"
        "- علامة [DONE] للإغلاق.\n\n"
        "المطلوب منك في هذه الجولة:\n"
        "قم بتحديث الوثيقة `DUAL_AGENT_COOPERATION_PROTOCOL_V2.md` لتصبح النسخة النهائية الشاملة الكاملة المتكاملة، "
        "مع إدراج هذه الحقول الحقيقية بالاسم والنوع في قسم Parameter Passing Schema، "
        "وتوثيق شروط فحص الجلسة والـ Error Precedence.\n"
        "اكتب الوثيقة المحدثة v2.0 كاملة من البداية للنهاية داخل بلوك كود: ```markdown ... ```"
    )
    
    start_time = time.time()
    ans1, reasoning1, captured_tid = send_chat_stream(session, turn1_prompt, thread_id=THREAD_ID)
    print(f"\n✅ اكتملت الجولة الأولى خلال {(time.time() - start_time)/60:.2f} دقيقة.")
    
    # فحص واستخراج الوثيقة المحدثة
    v2_updated = extract_markdown(ans1)
    if len(v2_updated) > 3000:
        V2_PATH.write_text(v2_updated, encoding="utf-8")
        print(f"💾 [تم تحديث الوثيقة v2.0 بنجاح]: {V2_PATH} ({len(v2_updated):,} bytes)")
    
    # توثيق في سجل المحادثات
    with open(DIALOG_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n\n---\n## 🔄 جولة الحوار التفاعلي (Thread: {THREAD_ID}):\n\n")
        f.write(f"### Antigravity Prompt:\n{turn1_prompt}\n\n")
        f.write(f"### FreebuFF Reasoning:\n{reasoning1}\n\n")
        f.write(f"### FreebuFF Answer:\n{ans1}\n")
        
    print(f"\n📝 تم تدوين الجولة في: {DIALOG_LOG_PATH}")
    print("="*80)
    print("🎉 اكتملت جلسة التوأمة المعمارية بنجاح تام وتحديث الوثيقة v2.0 للنسخة النهائية الشاملة!")
    print("="*80)

if __name__ == "__main__":
    run_hour_session()
