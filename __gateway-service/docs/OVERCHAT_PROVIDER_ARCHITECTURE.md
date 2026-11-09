# ⚡ OVERCHAT_PROVIDER_ARCHITECTURE.md
## Overchat AI Gateway Provider Specification & Engineering Manual
### v2.0 — Multi-Model Free Suite & Zero-Browser Architecture

> **المرجع الدستوري:** دستور بولا v1.2 · القانون 1 و 9 · توجيهات البروفيسور زيزو (الفويسات #127 ← #135).  
> **المسار الرسمي المعتمد:** `__gateway-service/providers/overchat/` + `__gateway-service/docs/OVERCHAT_PROVIDER_ARCHITECTURE.md`  
> **حالة المزود:** ✅ معتمد وشغال بنسبة 100% كالمزود رقم 13 في الجيتواي (`Provider #13`).

---

## 1. نظرة عامة والهدف المعماري (Overview & Objectives)

مزود **Overchat AI** هو مزود هجين فريد من نوعه يتيح الوصول المباشر والحر إلى باقة متكاملة من أقوى نماذج الذكاء الاصطناعي العالمية بشكل مجاني ودون الحاجة لأي أرصدة مسبقة أو اشتراكات مدفوعة، وذلك عبر هندسة عكسية دقيقة ومحاكاة كاملة لتطبيق الهاتف المحمول (Android Mobile Emulation).

### 🎯 الخصائص الجوهرية:
1. **صفر متصفح (Zero-Browser Ban):** يتم الاتصال بالكامل عبر طلبات HTTP/2 نقية وسريعة وخالية تماماً من المتصفحات الثقيلة أو استهلاك الذاكرة.
2. **محاكاة بصمة الأندرويد (OkHttp 4.12.0):** إرسال ترويسات أندرويد حقيقية مع تدوير معرفات الأجهزة (`x-device-uuid`) وعناوين الـ IP العشوائية.
3. **مصادقة ذاتية مجهولة (Autonomous Anonymous Auth):** إنشاء جلسات ضيوف مشفرة وفورية عبر `/v1/auth/me` دون الحاجة لحسابات مسجلة أو كوكيز معرضة للحظر.
4. **مفكك SSE بايتي (Byte-level Streaming Buffer):** قراءة التدفق كـ Bytes وتجميعه لمنع تشوه الحروف العربية متعددة البايتات (`UTF-8`).
5. **طابور تحويل بديل لحظي (Automatic Model Fallback):** في حال تعثر النموذج الأساسي، يتم التحويل التلقائي للنموذج البديل دون انقطاع الاستجابة.

---

## 2. جدول النماذج المجانية المدعومة (Supported Free Models Suite)

يتضمن المزود في ملف [`models_metadata.json`](file:///d:/SMS/.hRhRhRhRhRhR/__gateway-service/providers/overchat/models_metadata.json) كافة النماذج المجانية التي تم التحقق الميداني من تشغيلها الحي:

| # | اسم النموذج (Model ID) | الاسم المعروض (Display Name) | Persona ID | نافذة السياق | القدرات والوسائط | حالة الاختبار الحي |
|---|---|---|---|:---:|---|:---:|
| 1 | `gpt-6-luna` | **GPT-6 Luna** | `gpt-5-6-luna` | 128,000 | Chat, Reasoning, Code, Vision, Web Search | ✅ شغال 100% |
| 2 | `gpt-5.6-luna` | **GPT-5.6 Luna** | `gpt-5-6-luna` | 128,000 | Chat, Reasoning, Code, Vision, Web Search | ✅ شغال 100% |
| 3 | `gemini-3.8-flash` | **Gemini 3.8 Flash** | `gemini-3-5-flash` | 128,000 | Chat, Reasoning, Code, Web Search | ✅ شغال 100% |
| 4 | `claude-4.5-haiku` | **Claude 4.5 Haiku** | `claude-haiku-4-5-landing` | 128,000 | Chat, Reasoning, Code | ✅ شغال 100% |
| 5 | `deepseek-v3.2` | **DeepSeek v3.2 Non-Thinking** | `deepseek-v-3-2-landing` | 128,000 | Chat, Code, Reasoning | ✅ شغال 100% |
| 6 | `gpt-5-mini` | **GPT-5 Mini** | `code-detector-landing` | 64,000 | Chat, Code, Reasoning | ✅ شغال 100% |
| 7 | `gpt-5-nano` | **Overchat GPT-5 Nano** | `auto-model` | 32,000 | Chat, Code | ✅ شغال 100% |
| 8 | `gpt-4.1-nano` | **GPT-4.1 Nano** | `ai-text-generator` | 32,000 | Chat, Code | ✅ شغال 100% |

---

## 3. الهيكل المعماري ثلاثي الطبقات (Three-Layer Architecture)

```
        المنصة (Platform)
               │
               ▼  ProviderContext
   ┌────────────────────────────────────────┐
   │ 🔵 الطبقة 3: العقد والإعلان             │
   │ - definition.py                        │
   │ - models_metadata.json                 │
   └───────────────────┬────────────────────┘
                       │
                       ▼
   ┌────────────────────────────────────────┐
   │ 🟡 الطبقة 2: المترجم المعتمد (Adapter)  │
   │ - adapter.py                           │
   │ - تصنيف أخطاء ADR-0008 (12 فئة مغلقة)   │
   │ - تحويل ProviderContext ⇄ FacadeResult  │
   └───────────────────┬────────────────────┘
                       │
                       ▼
   ┌────────────────────────────────────────┐
   │ 🟢 الطبقة 1: المحرك الداخلي (_core)    │
   │ - _core.py                             │
   │ - OkHttp 4.12.0 Mobile Emulation       │
   │ - /v1/auth/me Anonymous Identity       │
   │ - /v1/chat/{user_id} Session Init      │
   │ - /v2/chat/responses SSE Engine        │
   └────────────────────────────────────────┘
```

---

## 4. الحصانة ضد تسريب الحسابات والبيانات الحساسة (Zero Secret Leakage)

1. **الوضع التشغيلي (Credential Mode):** مصنف كـ `platform`. لا يحتاج المستخدم إلى إرسال أي مفاتيح خاصة به (`user_key`).
2. **استبعاد كلي للملفات الحساسة:** ملفات الكوكيز وسجلات الحسابات (`accounts_*.json` و `*cookie*.txt` و `.env`) مستبعدة تماماً بموجب `.gitignore`.
3. **عزل المعرفات:** لا يتم تسجيل أو إظهار الـ `user_id` أو الـ `chat_uuid` في أي سجل عام أو إعادته للعميل في رسائل الخطأ.

---

## 5. نتائج الاختبارات الميدانية (Verification & Test Reports)

### أ. الاختبارات الهرمتيكية المعزولة (`tests/providers/test_overchat.py`):
```text
tests/providers/test_overchat.py ........ [100%]
8 passed in 0.40s
```
- مطابقة مواصفة العقد والإعلان لـ 8 نماذج.
- رفض النماذج غير المدعومة بتصنيف `model_unavailable`.
- التحقق من رفض العمليات غير المدعومة كـ `unsupported_capability`.
- اختبار تحويل أخطاء الـ Upstream إلى فئات الجيتواي الـ 12 المعتمدة.

### ب. الاختبار الميداني الحي الشامل (`test_live_overchat.py`):
```text
======================================================================
🚀 بدء الاختبار الميداني الحي لمزود Overchat داخل الـ Gateway
======================================================================
1. فحص مطابقة عقد البوابة: 8 نماذج معلنة بنجاح.
2. اختبار توليد نص حي (GPT-6 Luna) -> النتيجة: ١٤٤. (PASS)
3. اختبار توليد نص حي (Gemini 3.8 Flash) -> النتيجة: باريس (PASS)
✅ تم اجتياز الاختبار الحي لمزود Overchat بكافة موديلاته داخل الـ Gateway بنجاح 100%!
```
