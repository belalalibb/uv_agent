# 🚀 AI Gateway Client SDK (External Platform Wrapper)

حزمة عميل برمجية متكاملة (Client SDK / Wrapper) مصممة خصيصاً للمنصات الخارجية للتواصل المنظم والآمن مع **AI Gateway Service** مع التحكم الكامل في كافة العقود المتاحة (`CONTRACT.md` / `ADR-0008`).

---

## 🌟 أبرز مميزات العميل

1. **دعم كامل لجميع نقاط الاتصال (5 Endpoints):**
   - `GET /healthz`: فحص صحة العملية (Process Liveness).
   - `GET /v1/describe`: استكشاف مواصفات المزود وقدراته وموديلاته المعلنة.
   - `GET /v1/models`: استرجاع قائمة الموديلات المتاحة.
   - `GET /v1/health`: فحص حالة المزود.
   - `POST /v1/execute`: استدعاء العمليات الموحدة.

2. **دعم مخصص للعمليات الـ 8 المعتمدة بدوال مكتوبة (Strictly Typed):**
   - `generate_text(...)`
   - `generate_image(...)`
   - `transcribe_audio(...)`
   - `synthesize_speech(...)`
   - `create_embeddings(...)`
   - `rerank_documents(...)`
   - `moderate_content(...)`
   - `analyze_vision(...)`

3. **تحويل الأخطاء الـ 12 إلى استثناءات Python قوية (Typed Exceptions):**
   - مثل `RateLimitedError` (تحتوي على `retry_after_ms` و `retryable`).
   - `QuotaExceededError`, `ModelUnavailableError`, `ProviderUnavailableError`.
   - `RouteNotFoundError` (معالجة ذكية لردود الـ 404 المبهمة).

4. **تجاوز جمود الجيت واي عبر التوجيه الذكي (Smart Routing & Fallback):**
   - بما أن الجيت واي يطبق قاعدة "Zero Retries" وتوجيه 1:1 صارم، يوفر هذا العميل `SmartRouter` يتيح للمنصة الخارجية تحديد سلاسل تبديل تلقائي (Fallback Groups):
     إذا انشغل أو تعطل المزود الأول (`groq`) يتم التحويل تلقائياً وسلساً للمزود البديل (`syntx` أو `youmind`).

5. **دعم الوضعين المتزامن وغير المتزامن (Async & Sync):**
   - `GatewayClient` لتطبيقات FastAPI و asyncio الحديثة.
   - `SyncGatewayClient` لتطبيقات Django أو Flask أو الاسكربتات المباشرة.

---

## 📁 هيكلية المجلد

```
external_platform_client/
├── client/
│   ├── __init__.py         # واجهات التصدير الموحدة
│   ├── client.py           # العميل الرئيسي (GatewayClient & SyncGatewayClient)
│   ├── config.py           # قراءة الإعدادات ومتغيرات البيئة
│   ├── models.py           # نماذج البيانات Pydantic (المدخلات والمخرجات)
│   ├── exceptions.py       # الاستثناءات الـ 12 المشتقة من تصنيفات العقد
│   └── routes.py           # مدير التوجيه الذكي والتبديل التلقائي (Smart Fallback)
├── examples/
│   ├── 01_quickstart.py          # فحص الصحة والاستكشاف
│   ├── 02_chat_completion.py     # توليد النصوص وتتبع التوكنز
│   ├── 03_multimodal_vision.py   # تحليل الصور والرؤية المتعددة
│   ├── 04_embeddings_and_search.py # التضمين المتجهي وإعادة الترتيب
│   ├── 05_smart_fallback.py      # التبديل التلقائي عند التعطل
│   └── 06_error_handling.py      # التعامل الاحترافي مع الأخطاء
├── .env.example            # نموذج متغيرات البيئة
├── requirements.txt        # الاعتماديات (httpx, pydantic)
└── README.md               # التوثيق الشامل (هذا الملف)
```

---

## ⚡ التثبيت والبدء السريع

### 1. تثبيت الاعتماديات
```bash
pip install -r requirements.txt
```

### 2. إعداد مفاتيح الاتصال
قم بنسخ ملف `.env.example` إلى `.env` أو مرر الإعدادات برمجياً:
```python
from client import GatewayClient, GatewayConfig, SmartRouter

config = GatewayConfig(
    base_url="http://127.0.0.1:8800",
    gateway_secret="live-demo-secret-key-bolla-zizo",
    secret_version=1,
)

# تعيين أسماء مستعارة سهلة لتوكنات المسار
router = SmartRouter({
    "groq": "rtk_groq_production",
    "syntx": "rtk_syntx_production_live_session",
})
```

---

## 💻 أمثلة برمجية

### 1) محادثة نصية بسيطة (Chat Completion)
```python
import asyncio
from client import GatewayClient, ChatMessage

async def main():
    async with GatewayClient() as client:
        result = await client.generate_text(
            route_token="groq",
            model="llama-3.3-70b-versatile",
            messages=[
                ChatMessage(role="user", content="اشرح لي نظرية النسبية في جملة واحدة.")
            ],
            temperature=0.7,
        )

        print("الرد:", result.output.text)
        print("استهلاك التوكنز:", result.usage.input_tokens, "in /", result.usage.output_tokens, "out")
        print("زمن الاستجابة:", result.latency_ms, "ms")

asyncio.run(main())
```

---

### 2) التوجيه الذكي والتبديل التلقائي (Smart Router Failover)
```python
from client import GatewayClient, SmartRouter

router = SmartRouter({
    "groq": "rtk_groq_production",
    "syntx": "rtk_syntx_production_live_session",
})

# إنشاء مجموعة تبديل تلقائي
router.register_group(
    group_name="fast_chat",
    primary="groq",        # المحاولة الأولى
    fallbacks=["syntx"],   # البديل التلقائي إذا كان الأول مضغوطاً (Rate Limited)
)

async with GatewayClient(router=router) as client:
    # نمرر اسم المجموعة مباشرة كـ route_token
    result = await client.generate_text(
        route_token="fast_chat",
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": "مرحبا"}],
    )
    print("نجح الطلب مع ضمان استمرارية الخدمة:", result.output.text)
```

---

### 3) فحص قدرات وموديلات المزود (Discovery)
```python
async with GatewayClient() as client:
    manifest = await client.describe(route_token="syntx")
    print("اسم المزود:", manifest.display_name)
    print("العمليات المدعومة:", manifest.operations)
    print("الموديلات المتاحة:", len(manifest.models))
```

---

### 4) معالجة الأخطاء المخصصة (Error Handling)
```python
from client import GatewayClient, RateLimitedError, QuotaExceededError, GatewayError

try:
    await client.generate_text(...)
except RateLimitedError as e:
    print(f"المزود مضغوط مؤقتاً، أعد المحاولة بعد {e.retry_after_ms} مللي ثانية")
except QuotaExceededError as e:
    print("انتهت كوتا هذا المزود، يجب التبديل لمزود آخر")
except GatewayError as e:
    print(f"خطأ عام: [{e.category}] {e.message}")
```

---

## 🧪 تشغيل الأمثلة الجاهزة

يمكنك تشغيل أي من الأمثلة الستة التوضيحية داخل مجلد `examples/`:
```bash
python examples/01_quickstart.py
python examples/02_chat_completion.py
python examples/03_multimodal_vision.py
python examples/04_embeddings_and_search.py
python examples/05_smart_fallback.py
python examples/06_error_handling.py
```

