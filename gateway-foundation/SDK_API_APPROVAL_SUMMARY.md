# Gateway SDK — وظائفه وردوده في الحد الأدنى المنفذ

**الحالة:** Gateway يطبق الآن Provider defaults وmodel overrides ويعرض الدعم الفعّال في Discovery. بقيت واجهة SDK عامة بلا قوائم Operations/Providers أو مخططات payload محلية؛ أُضيفت توضيحات سلوكية واختبار تكامل، لا واجهة خاصة بمزوّد أو عملية. يميز هذا المستند النتائج المنفذة عن وظائف Gateway المؤجلة مستقبلًا.

## الخلاصة التنفيذية

- SDK عميل async عام؛ لا توجد فيه دوال `generate_text()` أو `generate_image()` خاصة بكل Operation، ولا أسماء Providers/Models ثابتة ولا مخططات payload محلية. كل العمليات تمر عبر `execute()`، والخرج يظل JSON خامًا من Gateway.
- كل تنفيذ يحدد Provider واسم Model الأصلي معًا. تكرار الاسم عند Provider آخر يبقى اختيارًا منفصلًا؛ لا إعادة تسمية ولا Model IDs عالمية.
- Discovery المنفذ يُظهر لكل Model عمليات وقدراته **الفعّالة** بعد تطبيق Provider defaults والـoverrides. يحتفظ SDK بأشكال JSON كما يرسلها Gateway ولا يحسب التوريث.
- إشارة الاتصال الأولى تُستنتج من الطلب التشغيلي الصالح المار عبر `execute()`: نجاحه يؤكد اتصال ذلك الطلب في وقته. لا probe إضافي، ولا طلب مباشر من SDK إلى upstream، ولا تاريخ/عتبات/تحويل تلقائي بين Providers في البداية.
- حد الطلبات في الدقيقة ليس من وظائف SDK؛ يبقى سياسة Agent Core كما قرر المستخدم.

## 1. دورة حياة العميل وإعداده

```python
client = GatewayClient(
    base_url="https://gateway.internal",
    api_key="<server-side-secret>",
)
# Gateway(...) اسم مختصر للفئة نفسها
```

- `GatewayClient(...)` أو alias `Gateway(...)` ينشئ عميلًا؛ لا يرسل طلب شبكة عند الإنشاء.
- `api_key` مطلوب صراحةً أو من متغيرات البيئة؛ `base_url` يمكن تمريره أو أخذه من `GATEWAY_URL` (افتراضيه الحالي `http://127.0.0.1:8800`). يمكن ضبط `api_key_version`، `provider_routes` الانتقالية، `default_tenant_id`، و`default_timeout_ms`، أو تمرير `config=GatewayConfig(...)` بدل إعدادات الاتصال الفردية.
- `async with GatewayClient(...) as sdk` يعيد كائن العميل نفسه من `__aenter__`. الخروج من السياق أو `await sdk.close()` لا يعيد بيانات (`None`) ويغلق اتصال HTTP الذي أنشأه SDK؛ إذا مرر المستدعي `http_client` خارجيًا، لا يغلقه SDK.
- `GatewayConfig.from_env(...) -> GatewayConfig` ينشئ إعدادًا من الوسائط/البيئة؛ لا يتصل بـGateway. القيم الافتراضية الحالية: `GATEWAY_URL` أو `http://127.0.0.1:8800`، و`default_tenant_id="default_platform_tenant"`، و`default_timeout_ms=60000`.
- الإعدادات غير الصالحة أو خلط `config` مع إعدادات صريحة تسبب `ValueError` محليًا.

### اختيار Provider ومعلومات الاعتماد

افتراضيًا يرسل SDK اسم Provider العام في `X-Provider-Name`. فقط عند إعداد خريطة `provider_routes` القديمة يرسل `X-Route-Token` بدلًا منه؛ لا يرسلهما معًا، ولا يضع route token في URL أو جسم الطلب أو نتائج Discovery. سر Gateway يرسل في ترويسة خدمة خلفية موثوقة، وليس لمتصفح/تطبيق عميل.

## 2. الدوال العامة ونتائجها

| الدالة | المدخل الأساسي | النتيجة عند النجاح |
|---|---|---|
| `await sdk.discover()` | لا شيء | `list[dict]` لمزودي Gateway المسموحين. كل عنصر `{ "name": <public provider name>, "description": <manifest> }`. |
| `await sdk.describe(provider)` | اسم Provider العام | كائن manifest خام لـProvider، بلا غلاف إضافي. |
| `await sdk.list_models(provider)` | اسم Provider | قائمة كائنات Models كما يعرضها Gateway: `name`, `context_window`, وحقلا الدعم الفعّال `operations` و`capabilities`. |
| `await sdk.list_operations(provider)` | اسم Provider | قائمة Operations الافتراضية على مستوى Provider. لا تأخذ `model`؛ دعم Model المحدد يُقرأ من كائن ذلك الموديل في `list_models()`. |
| `await sdk.execute(...)` | Provider وOperation وModel وpayload عام، مع بيانات Envelope الاختيارية | كائن استجابة التنفيذ الخام من Gateway عند النجاح. لا يحوله SDK إلى class أو payload خاص بالعملية. |
| `await sdk.check_gateway_health()` | لا شيء | حاليًا `{ "status": "ok" }`؛ حياة عملية Gateway فقط. |
| `await sdk.check_provider_health(provider)` | اسم Provider | حاليًا `{ "status": "UNKNOWN", "checked_at": null }`؛ ليس فحصًا فعليًا للاتصال بالمزوّد. |
| `await sdk.close()` | لا شيء | `None`. |

عند إعداد `provider_routes` القديم، `discover()` لا يستعلم عن كامل كتالوج Gateway؛ يعيد فقط الأسماء المحلية المهيأة بالشكل نفسه `{name, description}`. من دون هذا الإعداد، يستخدم كتالوج Gateway العام المصرّح به.

### شكل Provider والكتالوج في Discovery المنفذ

يحافظ الرد على غلاف Gateway الحالي وحقول Provider الحالية، ويضيف حقول الدعم الفعّال لكل Model. المثال التالي هو **شكل الإرجاع من `sdk.discover()`** (SDK يفك الغلاف HTTP `{ "providers": [...] }`):

```json
[
  {
    "name": "Example Provider",
    "description": {
      "display_name": "Example Provider",
      "credential_mode": "platform",
      "capabilities": {"chat": true},
      "operations": ["generate_text"],
      "models": [
        {
          "name": "model-a",
          "context_window": 32000,
          "operations": ["generate_text"],
          "capabilities": {"chat": true}
        },
        {
          "name": "model-b",
          "context_window": null,
          "operations": ["generate_text", "analyze_vision"],
          "capabilities": {"chat": true, "vision_input": true}
        }
      ],
      "definition_version": "1.0.0",
      "health_supported": false
    }
  }
]
```

- `description.operations` و`description.capabilities` هما defaults Provider.
- `models[].operations` و`models[].capabilities` قيم فعّالة محسوبة لكل Model، وليستا صيغة override. في تعريف Provider الداخلي، غياب `model.support.<dimension>` يرث default ذلك البُعد؛ وجوده يستبدل القائمة/القاموس لذلك البُعد كله.
- Gateway يفرض عمليات الدعم الفعّالة للموديل المعلن. اسم Model غير مدرج لا يملك override معروفًا، لذلك يحافظ على التوافق الحالي ويستخدم Provider defaults؛ وقد يصنف الـAdapter/upstream الموديل على أنه غير متاح.
- عمليات Model هي أسماء Operations الحالية كسلاسل، والقدرات تتبع مفاتيح Gateway المنطقية الحالية. لا يضيف SDK قاموسًا موازيًا.
- `context_window` عدد صحيح أو `null` إذا لم يكن معروفًا. لا يوجد `canonical_model_id` ولا تطبيع لأسماء الموديلات.
- إذا تكرر `model-a` عند مزودين، يظهر في manifest كل Provider على حدة؛ على Agent Core اختيار `(provider, model)`.
- `describe(provider)` يعيد كائن `description` لهذا Provider. `list_models(provider)` يعيد مصفوفة `models` ذاتها. `list_operations(provider)` يبقى قائمة Provider الافتراضية، وليس بديلًا عن قراءة دعم Model المحدد.

## 3. تنفيذ أي Operation

التوقيع العام الحالي يبقى واحدًا لكل العمليات:

```python
result = await sdk.execute(
    provider="Groq",
    operation="generate_text",
    model="llama-3.1-8b-instant",
    payload={"messages": [{"role": "user", "content": "Hello"}]},
    request_id=None,
    tenant_id=None,
    credential_mode="platform",
    credential_value=None,
    timeout_ms=None,
)
```

`provider`, `operation`, `model`, و`payload` مطلوبة (وسائط مسماة). الـSDK يتحقق محليًا أن `operation` نص غير فارغ؛ Gateway هو الذي يتحقق أن العملية في عقده وأن Provider يعلن دعمها.

### Envelope المرسل إلى Gateway

عند ترك الاختيارات الافتراضية كما هي، يرسل SDK جسمًا بهذا الشكل؛ `request_id` يتولد تلقائيًا، و`tenant_id` افتراضي، والـpayload يمر عامًّا:

```json
{
  "operation": "generate_text",
  "model": "llama-3.1-8b-instant",
  "request_id": "req_<32 lowercase hex characters>",
  "tenant_id": "default_platform_tenant",
  "credential": {"mode": "platform"},
  "payload": {"messages": [{"role": "user", "content": "Hello"}]},
  "timeout_ms": 60000
}
```

إذا مرر المستدعي `request_id`, `tenant_id`, `timeout_ms` أو `credential_mode="user_key"` و`credential_value`، يستخدم SDK هذه القيم حسب عقد Gateway. `tenant_id` سياق audit فقط حاليًا؛ ليس إثبات هوية أو صلاحية أو حدًا للـRPM. لا يرسل SDK إعادة محاولات تلقائية.

### استجابة نجاح التنفيذ — ما يرجع من `execute()`

```json
{
  "succeeded": true,
  "output": {"text": "Hello!", "finish_reason": "stop"},
  "usage": {"input_tokens": 1, "output_tokens": 2, "units": 1},
  "latency_ms": 420,
  "error": null
}
```

شكل الغلاف ثابت لكل Operation. `output` كائن JSON عام تطبّعه طبقة Gateway/Adapter؛ SDK لا يفرض أن يكون نصًا أو صورة أو Audio ولا يعيد تشكيله. `usage` قد يكون `null`، وداخله `input_tokens` و`output_tokens` قد يكونان `null` و`units` عددًا. `latency_ms` زمن Gateway الذي يصل في الرد، وليس health score أو تاريخًا محفوظًا في SDK. الحقول تعاد كما يرسلها Gateway.

تستخدم العمليات الثماني الموجودة حاليًا الغلاف نفسه: `generate_text`, `generate_image`, `transcribe_audio`, `synthesize_speech`, `create_embeddings`, `rerank_documents`, `moderate_content`, `analyze_vision`. وجود العملية في عقد Gateway لا يعني أن كل Provider يدعمها؛ Discovery وتعريف Provider هما المرجع. لا يعلن أي Provider مسجل `moderate_content` حاليًا. `run_provider_agent`, `upload_asset`, و`download_asset` مستثناة من Gateway v1؛ ولا توجد في v1 طريقة SDK مستقلة لـ`generate_video` أو Streaming أو Jobs أو Asset upload/download.

### الفشل — استثناء، وليس كائنًا عاديًا يعيده `execute()`

قد يرجع Gateway على السلك فشل تنفيذ بهذا الشكل، حتى مع HTTP 200:

```json
{
  "succeeded": false,
  "output": null,
  "usage": null,
  "latency_ms": 37,
  "error": {
    "category": "provider_unavailable",
    "retryable": false,
    "message": "Provider could not complete the request",
    "retry_after_ms": null,
    "provider_code": null
  }
}
```

لكن SDK الحالي يترجم `succeeded: false` إلى `GatewaySDKError` بدل إرجاع هذا الكائن. الاستثناء يحوي `category`, `retryable`, `retry_after_ms`, `provider_code`, `http_status`, و`response` (جسم Gateway الخام كاملًا). في فشل التنفيذ الذي وصل HTTP 200 تكون `http_status == 200`.

- `GatewayTransportError`: timeout أو تعذر إكمال الاتصال بـGateway؛ لا يوجد رد Gateway موثوق.
- `GatewayProtocolError`: جسم الرد ليس JSON صالحًا أو ليس JSON object؛ يحتفظ بـ`http_status` إن وصل HTTP response.
- `GatewaySDKError`: أخطاء Gateway/HTTP، ومنها 400 envelope/selectors، 401 مصادقة، 404 route/provider غير متاح، و500 خطأ داخلي معقم. فشل 500 في تنفيذ Adapter يظل محتواه الخام محفوظًا في `response`.
- `ProviderNotConfiguredError` نوع قديم مُصدّر للتوافق؛ لا يستخدمه المسار الحالي المعتاد.
- أخطاء الوسائط/الإعداد المحلية مثل اسم Provider أو Operation فارغ تسبب `ValueError`.

## 4. الصحة الأولية كما اتُفق عليها

1. `check_gateway_health()` يفحص Gateway فقط، ونتيجته الحالية الدقيقة `{ "status": "ok" }`.
2. `check_provider_health(provider)` يطلب `/v1/health` ويرجع حاليًا `{ "status": "UNKNOWN", "checked_at": null }`؛ هذه الواجهة لا ترسل request إلى Provider، ولا يمكنها وحدها تأكيد اتصاله.
3. إشارة البداية التي نوصي بها هي من **طلب التشغيل الحقيقي**: إذا نجح الطلب الصالح عبر `execute()` ورجع `succeeded: true`، يسجل Agent Core أن هذا Provider أجاب بنجاح في ذلك الوقت، مستفيدًا من `latency_ms`. إذا فشل الطلب، يسجل الفشل وسببه؛ الخطأ الوظيفي مثل `bad_request` أو `unsupported_capability` لا يثبت وحده أن Provider مفصول. قبل أول طلب صالح تكون الحالة غير معروفة.
4. لا يضيف هذا SDK health probe اصطناعيًا، أو سجلًا/عتبات لصحة Provider، ولا يرسل SDK اتصالًا مباشرًا إلى upstream. لا توجد عملية عامة مجانية وآمنة يمكن استخدامها كـping لكل Provider بلا عقد إضافي. يمكن تثبيت تعريف صحي أدق لاحقًا.
5. لا يُضيف SDK وظيفة RPM؛ Agent Core يفرض الحد الذي يحدده المستخدم لكل Provider.

**حد الصحة الحالي:** الاستدلال من نجاح طلب فعلي عادي هو إشارة الاتصال الأولية. إذا أُريد probe منفصل بمجرد اسم Provider، فالعقد لا يملك عملية عامة/Model/حمولة ping؛ يلزم قرار منفصل عن نوع الطلب وتكلفته وكيف ينفذه Gateway.

## 5. ما يبقى خارج SDK عمدًا

- لا دوال منفصلة لكل Provider أو Operation، ولا Capabilities أو payload models محلية.
- لا إعادة تسمية أو ID عالمي للموديل؛ اختيار كل مزوّد/موديل زوج مستقل.
- لا تحقق tenant أو عزل tenant أو quota في SDK؛ `tenant_id` الحالية audit context.
- لا rate limiter أو اختيار Provider داخلي في SDK؛ Agent Core هو من يختار ويطبق سياسة الحد.
- لا Streaming/Jobs/Assets في أقل بداية؛ تظل معانيها المستقبلية في وثيقة العقد فقط حتى اعتماد تنفيذها.

**حدود ما نُفّذ:** دعم Model وDiscovery وفحص العملية المعلنة مطبق في Gateway. تكامل SDK يظل عامًا؛ يمرر الموديلات والحقول غير المعروفة دون تطبيع أو مخطط محلي، وتثبت اختبارات التكامل تدفق القيم الفعّالة والتنفيذ/الرفض. لا توجد دوال أو قوائم خاصة بمزوّد أو عملية. الصحة المتقدمة وAgent Core وStreaming/Jobs/Assets والفيديو ما زالت خارج التنفيذ.