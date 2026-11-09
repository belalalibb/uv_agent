"""
================================================================================
🚀 CONTINUOUS GLM-5.3-FLASH OPTIMIZER (Autonomous Living Pipeline)
================================================================================
المطور: بروفيسور زيزو والمهندس بولا
المهمة: تشغيل حلقة شات مستمرة (30 دقيقة - 1 ساعة) في محادثة واحدة (Same Thread)
       باستخدام موديل GLM 5.3 Flash مع وضع التفكير الأقصى (Max Reasoning)
       لفحص وتطوير وتطهير مجلدي docs و tools وحفظ النتائج في gateway-zizo
================================================================================
"""

import os
import sys
import time
import json
import re
import requests
from pathlib import Path

# إعداد الترميز للطرفية في ويندوز
sys.stdout.reconfigure(encoding="utf-8")

# المسارات الأساسية
BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = BASE_DIR / "docs"
TOOLS_DIR = BASE_DIR / "tools"
OUTPUT_DIR = BASE_DIR / "gateway-zizo"
OUTPUT_DOCS_DIR = OUTPUT_DIR / "docs"
OUTPUT_TOOLS_DIR = OUTPUT_DIR / "tools"
COOKIE_FILE = BASE_DIR / "FREEBUFF_COOKIE.txt"

# إنشاء مجلدات المخرجات
OUTPUT_DOCS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE = OUTPUT_DIR / "PROGRESS_LOG.json"

# الرابط والموديل المعتمد (مطابق لملف الـ HAR الثاني 100%)
API_URL = "https://freebuff.com/api/chat/stream"
MODEL_NAME = "glm-5.3-flash"
REASONING_EFFORT = "max"

def get_cookie() -> str:
    """قراءة الكوكي من متغير البيئة أو الملف أو الطلب المباشر"""
    if os.environ.get("FREEBUFF_COOKIE"):
        return os.environ["FREEBUFF_COOKIE"].strip()
    if COOKIE_FILE.exists():
        cookie = COOKIE_FILE.read_text(encoding="utf-8").strip()
        if cookie:
            return cookie
    
    print("\n" + "="*80)
    print("⚠️ لم يتم العثور على كوكي FreebuFF!")
    print(f"👉 يرجى وضع الكوكي في الملف: {COOKIE_FILE}")
    print("   أو تعيين المتغير البيئي: FREEBUFF_COOKIE")
    print("="*80 + "\n")
    cookie_input = input("انسخ والصق الكوكي هنا (أو اضغط Enter لو حطيته في الملف): ").strip()
    if cookie_input:
        COOKIE_FILE.write_text(cookie_input, encoding="utf-8")
        return cookie_input
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    raise ValueError("❌ لا يمكن المتابعة بدون كوكي الجلسة!")

def clean_cookie(cookie: str) -> str:
    cookie = cookie.strip()
    # إذا تم لصق أمر cURL كامل بصيغة -b أو --cookie
    match_b = re.search(r"(?:-b|--cookie)\s+['\"]([^'\"]+)['\"]", cookie)
    if match_b:
        return match_b.group(1).strip()
    # إذا تم لصق أمر cURL كامل بصيغة -H 'cookie: ...'
    match_h = re.search(r"(?:-H|--header)\s+['\"]cookie:\s*([^'\"]+)['\"]", cookie, re.IGNORECASE)
    if match_h:
        return match_h.group(1).strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[7:].strip()
    # إزالة أي علامات اقتباس إضافية
    return cookie.strip("'\"")

def send_chat_stream(session: requests.Session, prompt: str, thread_id: str | None = None) -> tuple[str, str, str | None]:
    """إرسال طلب شات مع دعم الـ SSE وحفظ الـ Thread ID ومحتوى التفكير"""
    headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://freebuff.com",
        "referer": "https://freebuff.com/chat" + (f"?t={thread_id}" if thread_id else ""),
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    }
    
    payload = {
        "threadId": thread_id,
        "content": prompt,
        "model": MODEL_NAME,
        "reasoningEffort": REASONING_EFFORT,
        "gravity": {
            "user_data": {
                "visitor_id": "gruid_bvofl0dwqzz02atp",
                "session_id": "gr_sess_r2x4tvotz9jcvfjt",
                "client_user_agent": headers["user-agent"],
            },
            "event_source_url": "https://freebuff.com/chat",
            "client_context": {
                "timezone": "Africa/Cairo",
                "screen": {"width": 1552, "height": 873, "color_depth": 24, "pixel_depth": 24},
                "viewport": {"width": 1301, "height": 709},
                "platform": "Windows",
            }
        },
        "images": [],
        "attachments": []
    }
    
    res = session.post(API_URL, json=payload, headers=headers, stream=True, timeout=120)
    if res.status_code != 200:
        raise RuntimeError(f"❌ فشل الاتصال بالسيرفر! كود الحالة: {res.status_code}, الرد: {res.text[:300]}")
    
    captured_thread_id = thread_id
    reasoning_chunks = []
    content_chunks = []
    
    print("\n🧠 [GLM-5.3-Flash Reasoning Stream]:")
    in_reasoning = True
    
    for raw_line in res.iter_lines(decode_unicode=False):
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("data: "):
            raw_data = line[6:].strip()
            if raw_data == "[DONE]" or raw_data == '{"type":"done"}':
                break
            try:
                event = json.loads(raw_data)
                ev_type = event.get("type")
                
                if ev_type == "meta":
                    if not captured_thread_id:
                        captured_thread_id = event.get("threadId")
                        print(f"🔗 [تم ربط المحادثة المستمرة Thread ID]: {captured_thread_id}")
                
                elif ev_type == "reasoning_delta":
                    text = event.get("text", "")
                    reasoning_chunks.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
                
                elif ev_type == "delta":
                    if in_reasoning:
                        print("\n\n💡 [GLM-5.3-Flash Final Answer Stream]:")
                        in_reasoning = False
                    text = event.get("text", "")
                    content_chunks.append(text)
                    sys.stdout.write(text)
                    sys.stdout.flush()
                
                elif ev_type == "title":
                    pass
            except json.JSONDecodeError:
                pass

    print("\n" + "-"*80)
    return "".join(content_chunks), "".join(reasoning_chunks), captured_thread_id

def extract_code_or_markdown(response_text: str, ext: str) -> str:
    """استخراج الكود أو التوثيق النظيف بالكامل وتفادي الاقتطاع عند البلوكات المتداخلة"""
    lang = "python" if ext == ".py" else "markdown"
    
    # البحث عن بداية البلوك اللغوي
    for fence in [f"````{lang}", f"```{lang}", "````", "```"]:
        start_idx = response_text.find(fence)
        if start_idx != -1:
            content_start = response_text.find("\n", start_idx)
            if content_start != -1:
                content_start += 1
                end_idx = response_text.rfind("```")
                if end_idx > content_start:
                    candidate = response_text[content_start:end_idx].strip()
                    # إزالة أي باك-تيكس متبقية في النهاية
                    candidate = re.sub(r"`+$", "", candidate).strip()
                    if len(candidate) > 200:
                        return candidate
                        
    return response_text.strip()

def run_continuous_optimization():
    print("="*80)
    print("🚀 بدء تشغيل سكربت التحسين المستمر بموديل GLM 5.3 Flash (Max Reasoning)")
    print(f"🎯 الهدف: تطوير مجلدي docs و tools وحفظ النتائج في {OUTPUT_DIR}")
    print("="*80)
    
    cookie_str = clean_cookie(get_cookie())
    session = requests.Session()
    session.headers.update({"Cookie": cookie_str})
    
    # 1. فحص الجلسة والتأكد من الصلاحية
    print("\n📡 [1/3] فحص صحة جلسة FreebuFF عبر GET /api/auth/session...")
    check_res = session.get("https://freebuff.com/api/auth/session", timeout=15)
    if check_res.status_code == 200 and check_res.json().get("user"):
        user = check_res.json()["user"]
        print(f"✅ الجلسة نشطة ومصادق عليها بنجاح! المستخدم: {user.get('name')} ({user.get('email')})")
    else:
        print(f"⚠️ تحذير: الرد من /api/auth/session هو: {check_res.status_code} - {check_res.text[:200]}")
    
    # 2. تجهيز قائمة الملفات
    files_to_process = []
    for f in sorted(DOCS_DIR.glob("*.md")):
        files_to_process.append(("docs", f))
    for f in sorted(TOOLS_DIR.glob("*.py")):
        if f.name != "continuous_glm_optimizer.py":
            files_to_process.append(("tools", f))
            
    print(f"\n📂 [2/3] تم رصد {len(files_to_process)} ملفات مستهدفة للتطوير والتطهير:")
    for cat, fp in files_to_process:
        print(f"   • [{cat.upper()}] {fp.name} ({fp.stat().st_size:,} bytes)")
        
    # 3. إطلاق حلقة العمل المستمرة (Same Thread Session)
    print("\n🔥 [3/3] إطلاق الدورة المستمرة في نفس الثريد (Same Conversation Loop)...")
    active_thread_id = None
    start_time = time.time()
    
    # أول برومبت: تأسيس السياق المرجعي للثريد
    init_prompt = (
        "أنت كبير مهندسي المعمارية ومستشار النظم في مشروع Gateway Service.\n"
        "سنبدأ الآن جلسة عمل استشارية هندسية عميقة ومستمرة في هذه المحادثة لمراجعة وتطوير "
        "وتطهير كافة وثائق وأدوات المنظومة لرفعها إلى أعلى درجات النضج المؤسسي والـ Enterprise Quality.\n"
        "في كل خطوة سأرسل لك ملفاً كاملاً، والمطلوب منك تحليله بعمق، استخراج نقاط الضعف، "
        "وإعادة كتابته وتطويره بالكامل ليكون نموذجياً وصارماً مع الحفاظ على التوافق مع باقي المنظومة.\n"
        "أكد جاهزيتك التامة لنبدأ فوراً بالملف الأول."
    )
    
    print("\n" + "="*80)
    print("📢 إرسال برومبت التأسيس والتهيئة المعمارية للثريد...")
    ans, reasoning, active_thread_id = send_chat_stream(session, init_prompt, active_thread_id)
    print(f"\n✅ تم تأسيس الثريد بنجاح! Thread ID = {active_thread_id}")
    time.sleep(3)
    
    # معالجة الملفات ملفاً وراء ملف
    for idx, (cat, file_path) in enumerate(files_to_process, 1):
        rel_name = file_path.name
        out_sub = OUTPUT_DOCS_DIR if cat == "docs" else OUTPUT_TOOLS_DIR
        out_path = out_sub / rel_name
        
        # تخطي الملفات المكتملة بالفعل بحجم صالح
        if out_path.exists() and out_path.stat().st_size > 2000:
            print(f"\n⏭️ [تم التخطي]: ملف [{cat.upper()}] {rel_name} مطور ومحفوظ بالفعل ({out_path.stat().st_size:,} bytes)")
            continue
            
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        print("\n" + "="*80)
        print(f"🚀 [المهمة {idx}/{len(files_to_process)}]: تطوير ملف [{cat.upper()}] {rel_name} ({file_path.stat().st_size:,} bytes)")
        print("="*80)
        
        # سقف أقصى لحجم المحتوى لتفادي حظر Cloudflare WAF على البايلود الضخم
        safe_content = content[:8500] if len(content) > 8500 else content
        
        prompt = (
            f"الملف المستهدف: `{cat}/{rel_name}`\n"
            f"المسار: `{file_path}`\n\n"
            "المطلوب منك في هذه المحادثة:\n"
            "1. قم بإجراء تدقيق معماري عميق (Comprehensive Architectural Audit) للملف التالي.\n"
            "2. قم بتطويره، تحسينه، تنظيفه، وإزالة أي كود أو توثيق ركيك أو غير مكتمل.\n"
            "3. أعد كتابة محتوى الملف بالكامل بشكله النهائي المتكامل دون اختصار أو Placeholders.\n"
            f"4. ضع الملف النهائي كاملاً داخل بلوك كود: ```{'python' if file_path.suffix == '.py' else 'markdown'}\n\n"
            f"--- محتوى الملف الأصلي ---\n\n{safe_content}"
        )
        
        try:
            answer, reasoning, active_thread_id = send_chat_stream(session, prompt, active_thread_id)
        except Exception as err:
            print(f"⚠️ تنبيه: تعذر الإرسال في الثريد الحالي ({err})! جاري المحاولة بثريد جديد نقي...")
            time.sleep(5)
            active_thread_id = None
            answer, reasoning, active_thread_id = send_chat_stream(session, prompt, active_thread_id)
        
        # استخراج الكود وحفظه في مجلد gateway-zizo
        enhanced_content = extract_code_or_markdown(answer, file_path.suffix)
        
        out_path.write_text(enhanced_content, encoding="utf-8")
        print(f"\n💾 [تم الحفظ بنجاح]: تم حفظ الملف المطور في: {out_path} ({len(enhanced_content):,} bytes)")
        
        elapsed = time.time() - start_time
        print(f"⏱️ الوقت المنقضي: {elapsed/60:.1f} دقيقة.")
        
        # حفظ حالة التقدم اللحظية
        progress_data = {
            "thread_id": active_thread_id,
            "completed_count": idx,
            "total_files": len(files_to_process),
            "last_completed_file": f"{cat}/{rel_name}",
            "elapsed_minutes": round(elapsed / 60, 2),
            "status": "RUNNING" if idx < len(files_to_process) else "COMPLETED",
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S")
        }
        PROGRESS_FILE.write_text(json.dumps(progress_data, ensure_ascii=False, indent=2), encoding="utf-8")
        
        # استراحة قصيرة بين كل ملف لضمان استقرار الشبكة وتفادي التدافع
        print("⏳ استراحة 10 ثوانٍ قبل الملف التالي للحفاظ على ثبات الدورة...")
        time.sleep(10)
        
    print("\n" + "="*80)
    total_elapsed = time.time() - start_time
    print(f"🎉 اكتملت دورة التحسين المستمر بنجاح تام خلال {total_elapsed/60:.1f} دقيقة!")
    print(f"📂 كافة الملفات المطورة تم حفظها في مجلد: {OUTPUT_DIR}")
    print("="*80)

if __name__ == "__main__":
    run_continuous_optimization()
