# 🌐 مزود Overchat AI — Gateway Provider Documentation

> **الإصدار:** v1.1.0  
> **التوافق الدستوري:** دستور بولا الهندسي v1.2 + معمارية البوابة الموحدة Gateway Contracts ADR-0008  
> **نوع المصادقة:** Platform Mode (بدون متصفح - Zero Browser عبر محاكاة OkHttp 4.12.0 بهوية جهاز عشوائية مؤقتة)

---

## 📋 نظرة عامة (Overview)

تم بناء ودمج مزود **Overchat AI** داخل بيئة **Gateway Service** ليعمل كمزود متعدد القدرات (Multimodal Provider) فائق السرعة والموثوقية، يتيح الوصول المباشر إلى أقوى نماذج الذكاء الاصطناعي العالمية مجاناً وبدون الحاجة لفتح متصفح حقيقي، مع دعم كامل للعمليات الثلاث الأساسية:
1. **توليد النصوص والمحادثات المتقدمة (Text Generation & Reasoning)**
2. **تحليل الصور والرؤية الحاسوبية (Multimodal Vision Analysis)**
3. **تحويل الصوت إلى نص (Speech-to-Text Audio Transcription)**

---

## 🏛️ البنية المعمارية ثلاثية الطبقات (3-Layer Architecture)

```
                       ┌───────────────────────────────────────────────┐
                       │           Gateway Router / Client             │
                       └──────────────────────┬────────────────────────┘
                                              │ ProviderContext
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ الطبقة 3: الإعلان والعقد الموحد (definition.py)                                              │
│ - تعريف القدرات المغلقة: chat, reasoning, code, vision_input, audio_input, file_upload      │
│ - قائمة النماذج الـ 8 النشطة من models_metadata.json                                        │
│ - العمليات المعتمدة: generate_text, analyze_vision, transcribe_audio                         │
└─────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ الطبقة 2: محول البوابة والعزل (adapter.py)                                                  │
│ - التدقيق الصارم للمدخلات (Payload Schema Validation)                                       │
│ - عزل تام للرموز والمفاتيح (Zero Leakage)                                                   │
│ - ربط الـ HANDLERS بالعمليات المقابلة وترجمة الأخطاء إلى 12 فئة قياسية (ErrorCategory)      │
└─────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                              │
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ الطبقة 1: المحرك الداخلي المستقل (_core.py)                                                 │
│ - بروتوكول Zero-Browser HTTP عبر مكتبة httpx مع ترويسات تطبيق أندرويد OkHttp 4.12.0          │
│ - تسجيل مستخدم مجهول تلقائي عبر /v1/auth/me وإنشاء هوية جهاز مؤقتة                           │
│ - تدفق الردود عبر SSE Buffer مقاوم لتقطيع أحرف UTF-8 متعددة البايت                          │
│ - رفع المرفقات والصور إلى Amazon S3 عبر /v1/chat/upload ثم تضمينها بالطلب                    │
│ - تحويل الصوت إلى نص بدقة عالية عبر نقطة /v1/transcript                                     │
│ - التبديل التلقائي والاحتياطي الذكي (Graceful Model Fallback)                               │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 العمليات المدعومة والقدرات (Supported Operations)

### 1️⃣ توليد النصوص والتفكير المنطقي (`generate_text`)
- **العملية:** `GatewayOperation.GENERATE_TEXT`
- **الوظيفة:** إجراء محادثات نصية تفاعلية وتوليد كود وبرمجة وتفكير منطقي مع دعم البحث المباشر في الويب (`web_search`).
- **المعاملات:**
  * `messages`: قائمة الرسائل `[{"role": "user", "content": "..."}]`.
  * `temperature`: درجة الإبداع (اختياري).
  * `web_search`: تفعيل البحث الحي على الإنترنت (افتراضي: `True`).

### 2️⃣ تحليل وفحص الصور (`analyze_vision`)
- **العملية:** `GatewayOperation.ANALYZE_VISION`
- **الوظيفة:** استقبال الصورة بصيغة Base64، رفعها مباشرة وبشكل آمن إلى سيرفرات S3 الخاصة بالمزود، وتمرير رابطها ضمن حمولة الطلب لتحليل محتواها بدقة بواسطة `gpt-6-luna`.
- **المعاملات:**
  * `image_b64`: كود الصورة مشفر Base64.
  * `instruction`: الأمر أو السؤال الموجه للنموذج حول الصورة.
  * `image_format`: صيغة الصورة (`png`, `jpeg`, `webp`, إلخ).

### 3️⃣ تحويل التسجيلات الصوتية إلى نص (`transcribe_audio`)
- **العملية:** `GatewayOperation.TRANSCRIBE_AUDIO`
- **الوظيفة:** تفريغ المقاطع الصوتية إلى نص عربي أو إنجليزي بدقة استثنائية عبر نموذج Whisper الخاص بـ Overchat.
- **المعاملات:**
  * `audio_b64`: كود الملف الصوتي مشفر Base64.
  * `audio_format`: امتداد الملف الصوتي (`ogg`, `mp3`, `wav`, `m4a`).
- **المخرجات:**
  * `text`: النص المستخرج بدقة.
  * `language`: اللغة المكتشفة تلقائياً (مثل `ar`, `en`).

---

## 🧠 قائمة النماذج المجانية المتاحة (Model Suite)

جميع النماذج التالية مفحوصة ومتاحة مجاناً بدون الحاجة لحساب مدفوع:

| اسم النموذج في الـ Gateway | المعرف الأصلي في Overchat | نوع التخصص | سياق النافذة (Context) |
|-----------------------------|---------------------------|------------|------------------------|
| `gpt-6-luna` 🌟 | `gpt-6-luna` (persona: `gpt-5-6-luna`) | Flagship & Multimodal Vision | 128,000 |
| `gpt-5.6-luna` | `gpt-5.6-luna` (persona: `gpt-5-6-luna`) | Deep Reasoning & Intelligence | 128,000 |
| `gemini-3.8-flash` | `google/gemini-3.8-flash` | High-Speed Multimodal Flash | 128,000 |
| `claude-4.5-haiku` | `claude-haiku-4-5-20251001` | Anthropic Fast Intelligence | 128,000 |
| `deepseek-v3.2` | `deepseek/deepseek-non-thinking-v3.2-exp` | Advanced Coding & Architecture | 128,000 |
| `gpt-5-mini` | `openai/gpt-5-mini` | Efficient Smart Assistant | 128,000 |
| `gpt-5-nano` | `openai/gpt-5-nano` | Ultra-fast Chat Engine | 128,000 |
| `gpt-4.1-nano` | `openai/gpt-4.1-nano` | Lightweight General Purpose | 128,000 |

---

## 🔒 الأمان وحماية الأصول (Security & Invariants)

1. **الامتثال لـ Gateway Invariant #6:** توجد ملفات المرساة التشفيرية (`.anchor`) لجميع الملفات الأساسية (`_core.py.anchor`, `adapter.py.anchor`, `definition.py.anchor`, `models_metadata.json.anchor`).
2. **الامتثال لـ Gateway Invariant #2 (Zero Leakage):** حظر ظهور أو تسريب أي معرفات أجهزة أو مسارات ملفات أو رموز اتصال في نواتج الاستجابة أو رسائل الأخطاء.
3. **الامتثال لـ Gateway Invariant #1 (Hermetic Isolation):** دعم كامل للـ `MockTransport` لتمكين بيئات الاختبار الآلي المستقلة من العمل بدون إنترنت.

---

## 🧪 حزم الاختبار والتحقق (Testing & Verification)

### اختبارات الوحدة المنعزلة (Unit Tests):
```bash
pytest tests/providers/test_overchat.py -v
pytest tests/test_provider_contract.py -k overchat -v
```

### الاختبار الميداني الحي (Live End-to-End Test):
يقوم هذا الاختبار بفحص العمليات الحية الثلاث (نص مع لونا، نص مع جيميني، تحليل صورة حقيقية، تفريغ تسجيل صوتي حقيقي):
```bash
python test_live_overchat.py
```
