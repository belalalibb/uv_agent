# SDK — أمثلة المدخلات والمخرجات

**تمييز مهم:** الجزء الأول يصف SDK وDiscovery المنفذين في هذا الفرع. الجزء الثاني يوضح استخدامًا مستقبليًا فقط، وليس وعدًا بأن عمليات الفيديو/البث/Jobs تعمل اليوم. تفاصيل الواجهات العامة والردود المنفذة والحدود المؤجلة في [`SDK_API_APPROVAL_SUMMARY.md`](SDK_API_APPROVAL_SUMMARY.md).

## 1. المسار الحالي المنفذ

### اكتشاف الكتالوج وتعريف Provider

```python
from gateway_sdk import GatewayClient

async with GatewayClient(
    base_url="https://gateway.internal",
    api_key="<server-side-gateway-secret>",
) as sdk:
    providers = await sdk.discover()
    groq = await sdk.describe("Groq")
    models = await sdk.list_models("Groq")
    operations = await sdk.list_operations("Groq")
```

بلا `provider_routes` محلية، `discover()` يستدعي `/v1/providers`. شكل Groq الحالي من العقد (القيم كما هي في تعريف Provider وملف model metadata):

```json
[
  {
    "name": "Groq",
    "description": {
      "display_name": "Groq",
      "credential_mode": "platform",
      "capabilities": {"chat": true, "reasoning": true, "code": true},
      "operations": ["generate_text"],
      "models": [
        {
          "name": "allam-2-7b",
          "context_window": 4096,
          "operations": ["generate_text"],
          "capabilities": {"chat": true, "reasoning": true, "code": true}
        },
        {
          "name": "llama-3.1-8b-instant",
          "context_window": 131072,
          "operations": ["generate_text"],
          "capabilities": {"chat": true, "reasoning": true, "code": true}
        }
      ],
      "definition_version": "1.0.0",
      "health_supported": false
    }
  }
]
```

مخرجات الدوال في هذا العقد:

```python
operations == ["generate_text"]
models == [
    {
        "name": "allam-2-7b",
        "context_window": 4096,
        "operations": ["generate_text"],
        "capabilities": {"chat": True, "reasoning": True, "code": True},
    },
    {
        "name": "llama-3.1-8b-instant",
        "context_window": 131072,
        "operations": ["generate_text"],
        "capabilities": {"chat": True, "reasoning": True, "code": True},
    },
]
```

كل Model موجود داخل مدخل Provider الخاص به. لو ظهر الاسم `model-x` عند مزوّدين، لا يدمجه SDK ولا يعتبرهما مكافئين؛ الاختيار يبقى باستخدام Provider واسم الموديل الأصلي كما هما. لا نحتاج إعادة تسمية أو Model IDs إضافية.

حقول الدعم الظاهرة هنا مصدرها الآن Provider defaults بعد حلّها لكل Model؛ لا يمرر Gateway تلقائيًا حقول `label` أو metadata خاصة غير موجودة في العقد العام. إضافة بيانات تعريف أخرى تحتاج توسيعًا صريحًا لعقد Discovery، وليس تعديلًا محليًا في SDK.

### تنفيذ عملية

```python
async with GatewayClient(
    base_url="https://gateway.internal",
    api_key="<server-side-gateway-secret>",
) as sdk:
    result = await sdk.execute(
        provider="Groq",
        operation="generate_text",
        model="llama-3.1-8b-instant",
        payload={"messages": [{"role": "user", "content": "Hello"}]},
        credential_mode="platform",
        tenant_id="tenant_opaque_123",
    )
```

SDK ينشئ Envelope قريبًا من التالي (مع `request_id` و`tenant_id` و`timeout_ms` افتراضية إن لم تُمرر):

```json
{
  "operation": "generate_text",
  "model": "llama-3.1-8b-instant",
  "request_id": "req_<generated-id>",
  "tenant_id": "tenant_opaque_123",
  "credential": {"mode": "platform"},
  "payload": {"messages": [{"role": "user", "content": "Hello"}]},
  "timeout_ms": 60000
}
```

استجابة النجاح الخام التي يعيدها SDK تكون بالشكل التالي؛ قيم الاستخدام والتأخير مجرد مثال:

```json
{
  "succeeded": true,
  "output": {"text": "Hello!", "finish_reason": "stop"},
  "usage": {"input_tokens": 1, "output_tokens": 2, "units": 1},
  "latency_ms": 420,
  "error": null
}
```

لا يحول SDK `output` إلى class خاص بالمزوّد أو العملية. على HTTP أو تنفيذ فاشل، يرفع `GatewaySDKError` ويحتفظ برد Gateway الخام في `exc.response`; ويستخدم `GatewayTransportError` لمشاكل الاتصال/timeout و`GatewayProtocolError` لرد غير JSON object.

`tenant_id` الذي تمرره في المثال يصل إلى Gateway وProviderContext كسياق audit فقط. لا يثبت هوية المستأجر ولا يغيّر السماح بالمزوّد أو الموديل، ولا يخلق عزلًا أو صلاحيات per-tenant. سر Gateway وقائمة المزوّدين المسموح بها يحددان نطاق النشر المشترك.

### حالة الصحة

```python
gateway_health = await sdk.check_gateway_health()
# حاليًا: {"status": "ok"}

provider_health = await sdk.check_provider_health("Groq")
# حاليًا Gateway يجيب دائمًا: {"status": "UNKNOWN", "checked_at": None}
```

الـSDK الحالي لا يحتفظ بسجل صحة لكل Provider، و`check_provider_health()` لا ينفذ probe إلى upstream؛ نتيجته الحالية `UNKNOWN`. إشارة الاتصال الأولية المتفق عليها تُؤخذ من الطلب التشغيلي الصالح نفسه: نجاح `execute()` بـ`succeeded: true` يؤكد الاستجابة في وقتها، وAgent Core يسجل `latency_ms` أو الخطأ. لا probe صناعي ولا اتصال SDK مباشر بالمزوّد. خطأ طلب مثل `bad_request` أو `unsupported_capability` يعني أن ذلك الطلب فشل، وليس دليلًا كافيًا وحده على أن Provider مفصول؛ وتفاصيل health المتقدمة مؤجلة.

### توافق رموز المسار القديمة

استخدام `provider_routes` أو `ROUTE_TOKEN_<PROVIDER>` يحوّل الاختيار إلى `X-Route-Token`، كما يجعل `discover()` محصورًا بالأسماء المضبوطة محليًا. للحصول على كتالوج Gateway الكامل في المسار الجديد، لا تضبط خريطة legacy محلية. سر Gateway مخصص لخدمة خلفية موثوقة فقط.

## 2. الشكل المستهدف عند اعتماد العقد الجديد

الواجهة العامة لـ`execute()` يمكن أن تبقى كما هي: اسم Provider واسم Operation نصيان، والـpayload عام. مثال `generate_video` التالي **تصوري وغير قابل للتنفيذ حاليًا**؛ العملية غير موجودة في العقد الحالي:

```python
result = await sdk.execute(
    provider="Video Provider",
    operation="generate_video",
    model="video-model-from-discovery",
    payload={
        "prompt": "A short clip of waves at sunset",
        "duration_seconds": 8,
        "input_assets": [],
    },
)
```

في تصميم يدعم Jobs، استجابة القبول تكون غلاف مهمة عام، وليس جواب فيديو متزامنًا مزيفًا:

```json
{
  "accepted": true,
  "job": {
    "id": "job_opaque_id",
    "state": "queued",
    "status_url": "/v1/jobs/job_opaque_id",
    "result_url": null
  }
}
```

وبعد الاكتمال، النتيجة قد تشير إلى Asset بدل تضمين ملف فيديو ضخم داخل JSON:

```json
{
  "id": "job_opaque_id",
  "state": "succeeded",
  "result": {
    "assets": [
      {"asset_id": "asset_opaque_id", "media_type": "video/mp4", "size_bytes": 123456}
    ]
  }
}
```

هذه envelopes توضيحية للمراجعة فقط. أسماء المسارات، حقول الحالة، مدة الاحتفاظ، وما إذا كانت `execute()` نفسها سترجع accepted-job envelope ما زالت تحتاج اعتمادًا.

### الحقول المستقبلية غير المعروفة

SDK الحالي يقرأ JSON إلى `dict[str, Any]` ولا يعيد بناءه على Models محلية؛ لذلك أي حقل يصدره Gateway يصل كما هو. مثال مقصود للمستقبل:

```json
{
  "name": "Provider X",
  "description": {
    "models": [
      {
        "name": "model-x",
        "operations": [{"id": "generate_video", "modes": ["job"]}],
        "capabilities": ["video.generation"],
        "extensions": {"provider_metadata": {"new_field": "preserved"}}
      }
    ],
    "future_gateway_field": {"kept": true}
  }
}
```

لكي يصل هذا فعلًا، يجب أن تسمح طبقة Gateway بإصداره ضمن عقد Discovery مع الحفاظ على صرامة المدخلات الأمنية. SDK لا ينبغي أن يفلتره أو يرفضه أو يحتاج تحديثًا له.

## 3. حد اليوم وحد المستقبل

| العنصر | الآن | بعد اعتماد العقد والتنفيذ |
|---|---|---|
| أسماء Providers/Operations داخل SDK | لا قوائم ثابتة | تظل غير موجودة |
| إدخال Provider جديد | يحتاج تسجيلًا وإعداد نشر في Gateway | لا يغيّر SDK أو Agent Core إذا استخدم Operations قائمة |
| عملية جديدة | Gateway v1 يرفض اسمًا خارج Enum | واجهة SDK العامة تظل `operation: str`; Gateway/Adapter والعقد والاختبارات تتغير |
| Streaming | لا يوجد API عام بالـSDK/Gateway | طريقة تسليم مستقلة بعقد أحداث واضح؛ API method النهائي لم يُعتمد |
| Jobs | لا يوجد `job_id` أو polling/result/cancel | API عام مستقل عن كون العملية فيديو أو غيره |
| Asset Reference | لا يوجد شكل عام | نوع مرجعي مشترك بعد تحديد التخزين والصلاحيات |
