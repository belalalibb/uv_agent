# 🐟 TinyFish AI Provider — Architectural Specification & Engineering Reference
## Universal Gateway Integration (Provider #14) — Autonomous Web Agent & Multimodal Vision

- **تاريخ التوثيق:** 2026-09-26
- **المؤلف / المهندس:** Antigravity AI Engineering
- **المستوى الدستوري:** متوافق 100% مع دستور بولا v1.2 وثلاثية الطبقات (ADR-0008)
- **الموقع التشغيلي:** `__gateway-service/providers/tinyfish/`

---

## 1. 🏛️ النظرة المعمارية العامة (Architectural Overview)

يمثل مزود **TinyFish AI** المزود رقم **14** داخل بوابة خدمات الذكاء الاصطناعي (`__gateway-service`).
يختلف TinyFish عن المزودين التقليديين (مثل Groq أو Syntx) بأنه **بنية تحتية متكاملة لوكلاء الويب السحابيين المستقلين (Autonomous Web Agent & Cloud Browser Platform)**، حيث يجمع بين:
1. **محرك التفكير المعرفي والاستدلال (Cognitive Reasoning Engine):** تحليل الأسئلة والأهداف الموجهة وتوليد الإجابات المنطقية واستخراج البيانات.
2. **وكيل التنقل والتصفح الذاتي (Autonomous Navigation Agent):** القدرة على تشغيل متصفح سحابي كامل، التفاعل مع عناصر الـ DOM، ملء الاستمارات، واستخراج المحتوى المعقد.
3. **تحليل الرؤية الحاسوبية متعددة الوسائط (Multimodal Vision Analysis):** فحص الصور المرفقة بدقة فائقة واستخراج البيانات منها.

```
                  [Platform Request: POST /v1/execute]
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 3: Canonical Contract (definition.py & models_metadata.json)     │
│ • display_name: "TinyFish AI"                                          │
│ • credential_mode: PLATFORM (خزان حسابات داخلي معزول)                  │
│ • operations: generate_text, analyze_vision                            │
│ • 8 Approved Models: mako, eva, browser-agent, stealth-agent, etc.     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 2: Facade Adapter (adapter.py)                                   │
│ • Input Validation: messages, max_tokens, temperature, vision payload  │
│ • Safe Error Normalization: التحويل القاطع لـ 12 فئة أخطاء معتمدة      │
│ • Zero Leakage: حظر تام لتسريب المفاتيح، الجلسات، أو مسارات الملفات     │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Core Subsystem (_core.py & accounts_tinyfish.json)            │
│ • Zero-Browser Pure HTTP Engine (requests / httpx)                     │
│ • Concurrency Control: FileLock متزامن بمهلة 15 ثانية على ملف الخزان   │
│ • Dynamic Account Factory: توليد حسابات Clerk عبر Gmail Aliases        │
│ • Decoupled Isolation: اعتماد حصري على مكتبة `__دومينات مؤقته`         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 🔍 التشريح الجنائي للنماذج ومحركات التشغيل (Model & Engine Forensics)

بناءً على الفحص الميداني العميق لملفات الـ HAR (`agent.tinyfish............ai.har` و `agent.tinyfish..........1.........ai.har`)، حزم الـ JavaScript في Next.js، واستجابات PostHog Feature Flags، والتوثيق الرسمي عبر `llms-full.txt`، تم استكشاف بنية النماذج الحقيقية لـ TinyFish:

### أ. محرك الإدراك والتصفح الأساسي: **Mako** (Public Flagship Engine)
- **المسمى الرسمي في الواجهة:** Mako ("An agent that drives the browser to complete a task — now powered by Mako").
- **الدور الهندسي:** نموذج مدرّب ومخصص لإدراك عناصر صفحات الويب، تقليم شجرة الـ DOM، وتنفيذ الأفعال التفاعلية على المواقع.

### ب. محرك التفكير والاستدلال الداخلي: **EVA** (`model-owned-eva-amd`)
- **المسمى الكودي الداخلي:** EVA.
- **الإسناد في الـ HAR (Entry 763):**
  ```json
  "agentSource": "eva",
  "routingModelName": "model-owned-eva-amd",
  "goal": "انت موديل اي بصراحه؟؟؟"
  ```
- **الإسناد في PostHog Feature Flags (Entry 1401):**
  ```json
  "eva_model_routing_rollout": {
    "enabled": true,
    "variant": "model-owned-eva-amd"
  }
  ```
- **الإسناد في التوثيق الرسمي (`llms-full.txt` L550):**
  > *"needs a shorter or longer step budget than EVA's default. Non-beta API requests that include max_steps return 403 FORBIDDEN; requests without the field are unaffected."*

### ج. بنية المتصفحات السحابية: **Tetra Infrastructure** (`tetra-anchor`)
- **محرك المتصفح:** Tetra Browser Runtime.
- **عنوان البث المباشر المكتشف في الـ HAR (Entry 742 / 763):**
  `https://ip-54-183-135-146.tetra-data.production.tinyfish.io/.../stream/0`
- **إعدادات المتصفح:** Preset `BASIC` و `STEALTH` لتجاوز الكشف ومضادات البوتات.

---

## 3. 📋 كتالوج النماذج المعتمدة بالأدلة القاطعة (`models_metadata.json`)

تم تسكين النماذج الـ 8 الحقيقية المثبتة بالأدلة القاطعة من ملفات الـ HAR ومواصفات المنصة:

| معرف النموذج (Model ID) | نافذة السياق | تصنيف الوظيفة | الاستخدام الأمثل |
|-------------------------|-------------|---------------|-----------------|
| `mako` | 128,000 | Flagship Web Agent | تصفح الويب، تنفيذ الإجراءات التفاعلية، واستخراج البيانات الميدانية (الموديل المعلن V2) |
| `eva` | 128,000 | Core Reasoning Engine | الاستدلال المعرفي المباشر وتنفيذ المهام (`model-owned-eva-amd`) |
| `browser-agent` | 128,000 | Autonomous Cloud Agent | المهام المتعددة الخطوات عبر المتصفح السحابي |
| `stealth-agent` | 128,000 | Anti-Detection Agent | تصفح المواقع المحمية بأنظمة مضادات البوتات مع توجيه البروكسي السكني (`stealth`) |
| `tetra-engine` | 128,000 | Cloud CDP Infrastructure | التحكم المباشر في بيئة المتصفح السحابي الافتراضي (`tetra-anchor`) |
| `web-fetch` | 128,000 | Web Fetch Extractor | سحب نصوص وروابط صفحات الويب النظيفة بصيغ Markdown/HTML مع تصفية محددات CSS |
| `web-search` | 128,000 | Structured Web Search | محرك بحث حي ومصنف مع فلاتر المواقع والبلدان والتواريخ |
| `web-monitor` | 128,000 | Web & Price Monitor | رادار سحابي آلي لمراقبة تغيرات الأسعار والمخزون وإطلاق إشعارات التيليجرام والويب هوك |

> **⚠️ تنبيه دستوري (Bolla Law #8):** لا توجد أي نماذج خارجية باسم `gemini-2.5-flash` أو `gpt-4o` أو `claude-3-5-sonnet` داخل منصة TinyFish الأصلية؛ المنصة ليست موجه LLMs ولا توفر اختيار نماذج في الـ API أو الواجهة، بل تعتمد حصرياً على محركها الذاتي EVA/Mako.

---

## 4. 🌐 واجهات البرمجة المكتشفة لمنصة TinyFish (HAR Forensics & APIs)

من خلال فحص ترافيك الـ HAR ومواصفات OpenAPI المسحوبة حياً من خوادم المنصة:
1. **Automation / Agent API (`/v1/automation`):**
   - المسارات: `/v1/automation/run` (تزامني)، `/v1/automation/run-sse` (بث مباشر للأحداث)، `/v1/automation/run-async` (غير متزامن)، و `/v1/automation/run-batch`.
   - إدارة الخزائن والمصادقة التلقائية لكلمات المرور عبر `/v1/vault`.
2. **Persistent Cloud Monitor API (`/v1/monitors`):**
   - تسجيل مراقبات سحابية دورية مجدولة (`schedule_cron`) لمتابعة تغيرات الأسعار أو المخزون دون تشغيل محلي.
   - إرسال التنبيهات والأحداث تلقائياً إلى روابط الويب هوك (`webhook_url`).
3. **Browser Context Profiles API (`/v1/profiles`):**
   - إنشاء ملفات تعريف ارتباط متصفح دائمة (`POST /profiles`) تدعم تثبيت جلسات الدخول والبروكسي السكني المخصص (`proxyCountryCode`).
4. **Remote Browser API (`/v1/openapi/browser`):**
   - إنشاء جلسات تصفح سحابية مستقلة عبر بروتوكول Chrome DevTools Protocol (`cdp_url`) واستخدامها مع Playwright و Puppeteer.
   - مسبار التسخين اللحظي للمتصفحات السحابية عبر نبضات القلب (`POST /api/playground/warm-browser/heartbeat`).
5. **Fetch & Search APIs (`/playground/fetch` & `/playground/search`):**
   - سحب نصوص المواقع بصيغ `markdown` أو `html` وسحب نتائج البحث الحي بدقة فائقة.

---

## 5. 🔒 الحوكمة والأمان، طابور التزويد الفردي، وقانون العزل التام

1. **طابور إنشاء الحسابات المتتابع الصارم (Strict 1-Account FIFO Queue Refill):**
   - مع كل استدعاء لدالة `ask()` في البوابة، يتم تلقائياً إدراج **حساب واحد فقط (`count=1`)** داخل طابور الخلفية المتتابع الصارم (`_ACCOUNT_REFILL_QUEUE`).
   - خيط العمل الخلفي (`_sequential_account_worker`) ينشئ الحسابات **بالتتابع الصارم (حساب تلو الآخر)** مع مهلة أمان زمنية (`pacing delay`) لحماية المنصة من الحرق أو تجاوز الكوتا.
2. **الصفر-متصفح (Zero-Browser Mandate):** تسجيل الحسابات واستدعاء الـ APIs يتم عبر نداءات HTTP خالصة (`curl_cffi` / `requests` / `httpx`) دون فتح أي متصفح مرئي أو خفي محلياً.
3. **العزل التام بالبرهان الرياضي والتشغيلي (Strict Decoupling Proof):**
   - أثبت مسبار الفحص الجنائي الشامل `test_all_providers_isolation.py` أن مجلد `__gateway-service` معزول بنسبة 100% عن `مجلد المزودين` (0 violations عبر كافة المزودين الـ 14).
   - الارتباط الخارجي الوحيد المسموح به هو مع مكتبة `__دومينات مؤقته` لتوليد بريد الجيميل المؤقت واستقبال أكواد الـ OTP.
4. **حماية التزامن (Concurrency Safety):** يُحظر التعديل المتزامن على ملف الحسابات `accounts_tinyfish.json` بفضل قفل `FileLock` متزامن.
5. **منع تسريب البيانات:** تُحول كافة الاستجابات والأخطاء إلى إحدى الفئات الـ 12 المعيارية في `gateway.contracts.ErrorCategory`، ويُمنع منعاً باتاً ظهور أي مسار داخلي أو مفتاح API في نصوص الأخطاء.
