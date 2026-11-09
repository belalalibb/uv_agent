#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Send Local Provider Code to External Architect Agent for Review
==============================================================
Sends generated provider code from Antigravity IDE to FreebuFF GLM 5.3 Flash
for architectural review and concrete implementation of stream_text/generate_text.
"""

import sys
import json
from pathlib import Path
import requests

GATEWAY_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GATEWAY_DIR))
from tools.continuous_glm_optimizer import get_cookie, clean_cookie, send_chat_stream

session = requests.Session()
session.headers.update({"Cookie": clean_cookie(get_cookie())})
THREAD_ID = "2aab03f7-2e00-4537-9418-e5bd9e5af6d6"

adapter_file = GATEWAY_DIR / "providers" / "freebuff" / "adapter.py"
adapter_code = adapter_file.read_text(encoding="utf-8")

prompt = f"""تحية معمارية طيبة يا زميلي، وفق بروتوكول DUAL_AGENT_COOPERATION_PROTOCOL_V2.md وخطة العمل التتابعية (Phase R):
أرسل لك ملفات الكود التي قمت بتوليدها محلياً في Antigravity IDE لمزود `freebuff` لمراجعتها وتدقيقها معمارياً كـ Architect Agent:

1. كود `adapter.py`:
```python
{adapter_code}
```

المطلوب منك في تقرير المراجعة المعمارية:
1. فحص توافق `adapter.py` مع عقود البوابة الموحدة (`handle_generate_text` و `handle_stream_text`).
2. كتابة التطبيق الهندسي النموذجي لدالتي `generate_text` و `stream_text` داخل `_core.py` مع:
   - قراءة الكوكيز من متغير البيئة `FREEBUFF_COOKIE` أو ملف `FREEBUFF_COOKIE.txt`.
   - معالجة تدفق SSE لأحداث `meta` (واستخراج threadId) و `reasoning_delta` و `delta` و `[DONE]`.
   - خريطة الأخطاء الموحدة `UpstreamFailure` (AUTH_INVALID, RATE_LIMIT, UPSTREAM_ERROR, TIMEOUT).
3. قدّم الكود المكتمل النظيف والمحكم داخل بلوك كود python لنعتمده ونختبره فوراً في التيرمينال!"""

print(f"📡 جاري إرسال الكود للوكيل الخارجي (حجم البرومبت: {len(prompt)} حرف)...")
ans, reasoning, tid = send_chat_stream(session, prompt, thread_id=THREAD_ID)
print(f"\n✅ تم استلام الرد المعماري بالكامل (الطول: {len(ans)} حرف).")

log_path = GATEWAY_DIR / "docs" / "DUAL_AGENT_DIALOG_LOG.md"
with open(log_path, "a", encoding="utf-8") as f:
    f.write(f"\n\n---\n## 🔄 جولة مراجعة كود المزود محلياً (Thread: {THREAD_ID}):\n\n")
    f.write(f"### Antigravity Prompt:\n{prompt}\n\n")
    f.write(f"### FreebuFF Reasoning:\n{reasoning}\n\n")
    f.write(f"### FreebuFF Answer:\n{ans}\n")
print(f"💾 تم حفظ تفاصيل الحوار والكود في: {log_path}")

# حفظ الرد المستلم أيضاً في ملف مستقل للسهولة
review_output_file = GATEWAY_DIR / "docs" / "FREEBUFF_PROVIDER_ARCHITECT_REVIEW.md"
review_output_file.write_text(ans, encoding="utf-8")
print(f"📄 تم حفظ وثيقة المراجعة في: {review_output_file}")
