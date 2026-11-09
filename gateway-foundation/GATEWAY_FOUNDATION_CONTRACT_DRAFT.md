# Gateway Foundation Contract — مسودة العقد الهندسي

**الحالة:** وثيقة تصميم تميّز الحد الأدنى المنفذ في Gateway بهذا الفرع (Provider defaults، model overrides، Discovery بالدعم الفعّال، وفحص عملية الموديل المعلن) عن الأجزاء المستقبلية غير المنفذة. لا تشمل Agent Core أو endpoints للـStreaming/Jobs/Assets.

## 1. الغرض والنطاق

تثبيت الحدود العامة قبل بدء Agent Core. المطلوب أن يكتشف أي مستهلك ما يعلنه Gateway فعلًا، وأن يبقى SDK عامًا، وأن تكون إضافة Provider جديد لعمليات قائمة محصورة في Gateway. هذه الوثيقة لا تنفذ Registry أو Streaming أو Jobs أو تخزين Assets، ولا تضيف JSON Schemas أو Agent Core.

### أقل بداية سليمة موصى بها

1. اعتماد تعريفات Operation/Capability/Tool وقاموس قدرات عام، مع فصل القاموس عن الدعم التشغيلي.
2. إبقاء دعم العمليات والقدرات على مستوى Provider كإعداد افتراضي عندما ينطبق على كل موديل، وإضافة override اختياري للموديلات الاستثنائية فقط. Gateway يعرض الدعم الفعّال لكل Model بعد حلّ التوريث.
3. توثيق أن `tenant_id` الحالي سياق audit فقط وليس حدّ أمان أو صلاحية.
4. إكمال Discovery shape وإظهار ما هو متاح فعلًا، مع حفظ الحقول الإضافية دون تسريب أسرار.
5. تثبيت semantics العامة لـStreaming وJobs وAsset Reference في العقد، لكن تأجيل endpoints والتخزين والتنفيذ إلى أول حاجة حقيقية لها. الفيديو مرشح لاحق، وليس شرطًا للحد الأدنى.
6. عدم إضافة SDK/Agent provider lists أو Plugin/Registry إضافية، وعدم بدء Agent Core.

## 2. التعريفات الرسمية

| المفهوم | التعريف والمسؤولية | مثال |
|---|---|---|
| **Operation** | وظيفة موحّدة يوجّهها Gateway وينفّذها Adapter حقيقي. لها semantics وrequest/result وأخطاء قابلة للاختبار. | `transcribe_audio` |
| **Capability** | خاصية تقنية موثقة، يمكن أن يعلنها قاموس المنصة، ويعلن Provider/Model دعمها فقط بعد إثبات التنفيذ. ليست تنفيذًا بحد ذاتها. | `audio.transcription` |
| **Tool** | وظيفة أعلى مستوى تُركّب مستقبلًا من Operations وسياسات وخدمات؛ اختيارها وتنفيذها مسؤولية طبقة أعلى، لا Adapter عادي للمزوّد. | `meeting_assistant` من التفريغ والتلخيص واستخراج المهام |

لا نرقّي كل فكرة إلى Operation. ولا نخلط استجابة الموديل التي تقترح Tool call بتنفيذ الأداة نفسها.

## 3. ثلاث طبقات للاسم والدعم

1. **قاموس المفردات:** تعريفات Capability عامة مع وصف ثابت. يمكن أن يتضمن `video.generation` قبل وجود Provider يدعمه. لا يعني ذلك توفرًا.
2. **تعريف التنفيذ:** ما يستطيع Provider/Model تنفيذه فعليًا. لا يذكر إلا دعمًا مثبتًا بAdapter واختبارات.
3. **الكتالوج التشغيلي المنشور:** مجموعة ما هو مسجل ومفعّل وموجّه ومسموح به في نشر Gateway المحدد. لا يعرض المرشحات المستقبلية ولا مزوّدًا خارج قائمة النشر.

قاعدة الدعم:

> لا يظهر `Operation` كدعم تشغيلي لمزوّد/موديل إلا إذا وُجد عقدها، وhandler فعلي، واختبارات نجاح/فشل وDiscovery. لا يكفي Enum أو Capability أو ملف metadata وحده.

يجوز أن يحتوي قاموس Capability على مفردات غير مدعومة حاليًا. الأفضل أن تكون Claims التشغيلية قائمة إيجابية: الموجود مُثبت الدعم؛ الغائب لم يُعلن، ولا يعني بالضرورة استحالة الدعم.

## 4. علاقة Provider وModel وOperation وCapability

### النمط المنفذ الأقل تعقيدًا

- Provider يعلن Operations وCapabilities الافتراضية التي يثبت أنها تنطبق على كل موديل من موديلاته.
- عند اختلاف موديل، يسمح حقل `support` اختياري على ذلك الموديل بتغيير الدعم لذلك الموديل وحده. لكل بُعد قاعدة واضحة: غياب `support.operations` يعني وراثة عمليات Provider؛ وجودها يستبدل القائمة كاملة. وبالمثل لـ`support.capabilities`. لا توجد صيغة add/remove ثانية.
- إذا كانت كل الموديلات متشابهة فلا يضيف المطوّر أي حقول دعم داخل تعريف كل Model؛ بذلك لا يزيد مسار إضافة Provider المعتاد تعقيدًا.
- Discovery يعرض **الدعم الفعّال المحسوب** لكل Model، حتى لا يحتاج SDK أو أي مستهلك لفهم الوراثة.
- Provider-level operations/capabilities لا تُعد وعدًا لكل Model إلا إذا أعلنها Provider كافتراضية لكل موديل. يجب أن تكون هذه الافتراضات مثبتة باختبارات؛ الاستثناءات تستخدم override.
- عند التنفيذ، يفرض Gateway دعم Operations الفعّال للموديل المعلن. اسم Model غير موجود في قائمة Discovery لا يكتسب override غير معلن؛ يحافظ Gateway مبدئيًا على سلوكه الحالي ويعامله وفق Provider defaults، ويترك لـAdapter/upstream تصنيف موديل غير موجود إذا لزم.
- كل Model يتعرف عليه ضمن Provider بعينه. إذا ظهر الاسم نفسه لدى Providerين فهما خياران مستقلان يختارهما المستهلك بالزوج الموجود أصلًا: `(provider public name, provider model name)`. لا نعيد تسمية الموديلات ولا نضيف Model IDs عالمية، ولا نستنتج التكافؤ أو السعر أو القدرات بين المزوّدين.
- العمليات الحالية كلها تطلب `model` في Envelope. أي عملية لا ترتبط بموديل تحتاج قرارًا صريحًا؛ لا نستخدم موديلًا وهميًا.

### مثال لتعريف Provider

هذا شكل تعريف داخلي توضيحي، وليس API أو JSON Schema منفذًا. يستخدم أسماء Operations ومفاتيح Capabilities الحالية؛ لا يضيف SDK قوائم أو أنواعًا محلية:

```yaml
provider:
  display_name: "Example Provider"
  operations: ["generate_text"]
  capabilities: {"chat": true}
  models:
    - name: "model-a" # يرث عمليات وقدرات Provider
    - name: "model-b"
      support:
        operations: ["generate_text", "analyze_vision"] # استبدال القائمة لهذا الموديل
        capabilities: {"chat": true, "vision_input": true}
```

### شكل Discovery المنفذ — إضافة دنيا على الشكل الحالي

يحافظ Gateway على غلاف `/v1/providers` وحقول Provider الحالية؛ وتحتوي كل Model على الدعم **الفعّال** بعد حل defaults/overrides. أسماء العمليات strings ومفاتيح capabilities من القاموس الحالي، دون `canonical_model_id` أو `modes` أو مخطط خاص بالـSDK:

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

القوس الخارجي هنا هو شكل إرجاع `sdk.discover()` بعد أن يفك SDK غلاف HTTP `{ "providers": [...] }`. `describe()` يعيد كائن `description` نفسه، و`list_models()` يعيد مصفوفة `models`، و`list_operations()` يبقى قائمة Provider الافتراضية ولا يأخذ Model؛ دعم Model المحدد واضح في `list_models()`.

- حقلا `operations` و`capabilities` على Provider يحددان defaults. نظيراهما على كل Model في **Discovery** قيم فعّالة محسوبة، حتى لا يحسب المستهلك التوريث.
- في تعريف Provider، غياب `support.operations` أو `support.capabilities` يرث default البعد؛ وجود البعد يستبدل قائمة/قاموس ذلك البعد بالكامل.
- يحتفظ `context_window` بسلوكه الحالي: عدد صحيح أو `null` إذا لم يُعرف.
- يتبع `capabilities` مفاتيح Gateway الحالية (مثل `chat` و`vision_input`) وقيمًا منطقية؛ لا نغيّر مفرداتها ضمن أقل بداية.
- يظل الكتالوج مقيدًا بالمزوّدين المسموحين في النشر. لا يعرض slugs داخلية أو route tokens أو upstream identities. ظهور الاسم نفسه عند Provider آخر يبقى مدخلًا منفصلًا، ولا يلزم أي معرف عالمي.

## 5. Operation vocabulary المرشح

القائمة الحالية وحالة كل اسم موجودة في [`OPERATIONS_AND_PROVIDERS.md`](OPERATIONS_AND_PROVIDERS.md). مبدئيًا:

- نبقي عمليات النص والصورة والرؤية والصوت والتضمينات والترتيب والإشراف الموجودة، مع عدم مساواة وجودها في Enum بتوفرها عند كل Provider.
- نحسم `moderate_content`: لا Provider مسجل يعلنها حاليًا، لذلك يجب تنفيذها واختبارها قبل أي إعلان تشغيلي، أو إبقاؤها خارج الكتالوج النشط في العقد المنقح.
- لا نحتاج `generate_video` في أقل بداية سليمة؛ تُؤجل لمرحلة لاحقة إذا ظهرت حاجة منتج واضحة، وعندها تستخدم عقد Job/Asset العام بدل تصميم خاص بالفيديو.
- نضيف `generate_audio` فقط إذا كان توليد الموسيقى/المؤثرات استخدامًا مطلوبًا؛ فهي ليست مرادفًا لـ`synthesize_speech`.
- Streaming نمط تنفيذ لعمليات مثل `generate_text`، وليس Operation مستقلة.
- `tool_calling` Capability/شكل خرج، لا Operation لتنفيذ النظام.
- تبقى فكرة Operation في هذه الوثيقة مرشحًا فقط إلى أن تُستوفى شروط التفعيل؛ لا تدخل الكتالوج التشغيلي لمجرد التخطيط.

## 6. Streaming ليس Job

### Streaming

Streaming قناة تسلّم أجزاء النتيجة خلال تنفيذ الطلب نفسه. ليست مهمة معلقة بعد إغلاق القناة.

يلزم العقد أن يحدد، قبل التفعيل:

- معنى أحداث البداية والجزء/التحديث والإنهاء والخطأ والإلغاء.
- ترتيبًا قابلًا للتحقق، ونهاية واحدة واضحة؛ لا أجزاء بعد الحدث النهائي.
- شكل delta محايدًا عن Provider، ومعلومات usage/finish في النهاية عند توفرها.
- سلوك انقطاع الاتصال والإلغاء، وهل يستطيع Gateway إيقاف upstream فعلًا أم يوقف نقل النتيجة فقط.
- Binding نقل أولي بقرار منفصل. يمكن اعتماد SSE لواجهة HTTP إذا وافق المستخدم، لكن semantics للأحداث تظل منفصلة عن Provider ولا يُفترض تعدد تقنيات النقل بلا حاجة.

مثال أحداث توضيحي، لا يحدد transport النهائي:

```json
{"type": "started", "request_id": "req_...", "sequence": 0}
{"type": "delta", "request_id": "req_...", "sequence": 1, "data": {"text": "Hello"}}
{"type": "completed", "request_id": "req_...", "sequence": 2, "usage": {"units": 1}, "finish_reason": "stop"}
```

`error` حدث نهائي بديل عن `completed` عند الفشل. الإلغاء ليس إكمالًا ناجحًا.

### Jobs طويلة التنفيذ

Job طلب قُبل ويستمر بعد إرسال الرد الأولي. يختلف عن Streaming حتى لو أمكن أن يستخدم الاثنان في عملية واحدة مستقبلًا.

المتطلبات العامة لأي Job API:

- إنشاء Job وإرجاع معرّف opaque وحالة أولية.
- الاستعلام عن الحالة، واسترجاع النتيجة بعد النجاح، وإلغاء اختياري فقط إذا كان upstream يدعمه.
- حالات مرشحة: `accepted`, `queued`, `running`, `succeeded`, `failed`, `cancelled`؛ تحديد الانتقالات والحالات النهائية قبل التنفيذ.
- عدم اعتبار `job_id` سرًا أو وسيلة تفويض؛ كل status/result/cancel يحتاج مصادقة Gateway وتحققًا من scope النشر والطلب.
- تعريف الاحتفاظ بالنتائج وانتهاء الصلاحية، وأخطاء polling، وسلوك إلغاء لا يقدر Gateway على إيقافه upstream.

مسارات مثل `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/result`, و`POST /v1/jobs/{id}/cancel` أمثلة تصميمية فقط. لا يوجد أي منها في الكود الحالي.

## 7. Asset Reference

العمليات متعددة الوسائط تحتاج مرجعًا موحدًا بدل تدفق Provider-specific أو تمرير أسرار روابط مباشرة.

شكل توضيحي:

```json
{
  "asset_id": "asset_opaque_id",
  "media_type": "video/mp4",
  "size_bytes": 123456,
  "filename": "clip.mp4"
}
```

متطلبات العقد قبل التنفيذ:

- مرجع opaque لا يكشف مسار تخزين داخليًا أو credential أو رابطًا دائمًا موقعًا.
- يُستخدم في الإدخال والإخراج، مع MIME/حجم وبيانات اختيارية متفق عليها.
- تحديد جهة إصدار المرجع وحفظ البايتات وكيفية وصول Adapter إليها، النطاق الأمني، الانتهاء، حدود الحجم، والحذف.
- عدم خلط Asset Reference مع `upload_asset` أو `download_asset` كـProvider Operations؛ هاتان العمليتان مستثناتان حاليًا. إن احتاج النظام خدمة نقل أصول، تُعتمد كمسؤولية Gateway عامة منفصلة.

## 8. Discovery وSDK وحقول المستقبل

- الكتالوج يصف الدعم المسموح في نشر Gateway الحالي، لا كل مزوّد مسجل عالميًا.
- `describe`/`discover` يعيدان البيانات العامة التي يعرفها Gateway، ومنها الموديلات ودعم العمليات/القدرات الموثق.
- SDK يظل JSON client عامًا: لا Enums للمزوّدين أو العمليات، ولا تنقيح محلي للحمولة أو حقول النتيجة. الحقول غير المعروفة تصل كما هي للمستدعي.
- نماذج رد Gateway مغلقة `extra="forbid"`. حقلا الدعم الفعّالان `operations` و`capabilities` معلنان صراحةً الآن في `DiscoveredModel` ومختبران؛ لا يحتاجان `extensions` تخمينيًا. أما أي حقل Discovery مستقبلي جديد فيتطلب إضافته صراحةً إلى عقد Gateway واختباراته. SDK يمرر الحقول التي تصله خامًا، لكنه لا يستطيع جعل Gateway يصدر حقولًا لا يعرفها. تبقى `RequestEnvelope` strict لتفادي تجاوز حدود الأمان.
- يجب ألا يحاول SDK تعداد مجلدات Providers محليًا أو تجاوز حالة التعطيل. Gateway يكتشف حزم `providers/` ويعرض المفعّل منها؛ مسار `X-Route-Token` القديم يبقى متاحًا عبر `GW_ROUTE_MAP` الاختيارية حتى قرار إيقاف معلن.

## 9. الإصدارات والتوافق

- إصدار مسار API يحدد شكل النقل؛ `definition_version` يصف تعريف Provider. لا نخلط الإصدارين.
- إضافة حقل Discovery اختياري أو Capability جديدة لا تغيّر معنى الحقول السابقة؛ SDK قديم يتجاهلها أو يعيدها خامًا.
- تغيير semantics أو كسر shape موجود يحتاج إصدار/تفاوضًا صريحًا؛ لا يُبدّل بصمت داخل v1.
- أسماء Operations وCapabilities مستقرة؛ الإزالة أو إعادة التسمية تحتاج سياسة deprecation واختبارات توافق.
- الاكتشاف المنفذ محدود بفحص مجلدات Provider عند التشغيل عبر `ProviderRegistry`؛ لا تُضاف واجهة تسجيل HTTP أو طبقة Registry ثانية، ولا يجري تسجيل ذاتي من العميل.

## 10. الأمن والصدق

- Gateway secret خدمة خلفية موثوقة وليس credential لمتصفح/عميل نهائي.
- لا تظهر route tokens أو slugs أو upstream identity في Discovery أو SDK outputs أو الأخطاء.
- Capability/Operation تُعلن فقط حيث ثبت التنفيذ؛ عدم وجود Claim يعني لا تعتمد عليه طبقة أعلى.
- عمليات النظام ليست مسؤولية Adapter Provider؛ Tool مستقبلية لتنفيذ أوامر تحتاج عزلًا وسياسات منفصلة.
- لا يدعي Gateway دعم streaming cancellation أو job cancellation ما لم يستطيع فرضه أو يصف بدقة أن الإلغاء محلي للنقل فقط.

### Tenant context — الحد الحالي والمقترح

- `tenant_id` موجود حاليًا في Envelope وSDK، والافتراضي `default_platform_tenant`. العقد الحالي يصفه صراحةً بأنه سياق evidence/audit فقط؛ ProviderContext يمرره لكن Facade لا يجوز أن يتخذ عليه قرارات.
- لذلك `tenant_id` الحالي **ليس هوية موثوقة ولا حد صلاحيات**: لا يثبت من يرسل الطلب، ولا يقيّد Provider/Model، ولا يفرض quota أو عزل أسرار/ملفات. من يملك سر Gateway يتشارك صلاحيات جميع Providers المكتشفة والمفعّلة في ذلك النشر.
- أقل بداية سليمة: إبقاؤه معرفًا opaque للسياق/التدقيق، ويفضل ألا يتضمن بيانات شخصية. يمرره backend موثوق بقيمة مستقرة؛ لا يستخدمه Gateway للمصادقة أو تفويض العملية.
- إذا احتاجت تطبيقات إلى نطاقات Provider مختلفة، فالسياسة الحالية هي نشر Gateway منفصل لكل نطاق. لا ندّعي عزلًا per-tenant داخل نشر مشترك.
- تفويض متعدد المستأجرين مستقبلًا يحتاج هوية موثوقة من طبقة المصادقة وربط صلاحيات/موارد بهذه الهوية؛ لا يكفي إضافة `tenant_id` في الجسم. هذا مشروع أمني مستقل ولا يدخل أقل بداية.

### إشارة الاتصال الأولية وحد الطلبات — سياسة Agent Core لاحقًا

- اختيار Agent Core بحسب صحة Provider وحد RPM سياسة للمستهلك الأعلى، وليستا Operation أو Capability. لا نضيف لهما Provider/Model IDs جديدة.
- في البداية تكون إشارة الاتصال **رصدية من الطلبات العادية** المارة عبر `sdk.execute()` ثم Gateway: نتيجة `succeeded: true` مع `latency_ms` تؤكد أن ذلك الطلب وصل وعاد بنجاح في ذلك الوقت. لا نطلق طلب ping إضافيًا ولا نرسل طلبًا من SDK مباشرةً إلى upstream.
- يسجل Agent Core النجاح أو فشل الطلب كما هو. الخطأ التشغيلي يعني أن الطلب الأخير فشل، لكنه لا يثبت وحده أن Provider مفصول؛ مثل `bad_request`, `unsupported_capability` أو `content_rejected`. لا توجد في هذه البداية نافذة تاريخية أو thresholds أو failover تلقائي.
- إذا لم يُرسل طلب صالح بعد، فالصحة غير معروفة. ولأن `sdk.check_provider_health(provider)` الحالي لا يأخذ model/operation/payload ولا يفعل أكثر من `GET /v1/health`، فإنه يرجع حاليًا `{ "status": "UNKNOWN", "checked_at": null }`؛ لا يستخدمه Agent Core كإثبات اتصال في هذه البداية. `check_gateway_health()` يفحص Gateway process فقط ويرجع `{ "status": "ok" }`.
- إذا طُلب لاحقًا فحص نشط مستقل، يلزم اعتماد طلب آمن ومحدد يمكن تنفيذه عبر Gateway، مع تقرير تكلفته وأثره؛ لا يمكن عمل ping عام محايد لكل Provider بلا عقد/مدخلات.
- حد RPM ينفذه Agent Core على الطلبات المارة به؛ أما ضمان حد مشترك عبر عدة نسخ أو كل عملاء Gateway فيحتاج مناقشة منفصلة عن هذا العقد.
- مفتاح الاختيار والقياس هو اسم Provider العام الذي يستخدمه SDK، لا اسم Model. تغيير اسم Provider العام يُعامل كتغيير API له ترحيل؛ لا نحتاج تعديل أسماء الموديلات أو إضافة معرفات لها.

## 11. حالة التنفيذ ومعايير القبول

**منفذ في هذا الفرع:**

1. دلالة Provider defaults و`support` الاختياري لكل Model؛ البعد الغائب يرث والبعد الموجود يستبدل كامل البعد.
2. Discovery يخرج `operations` و`capabilities` الفعّالتين لكل Model، وRuntime يفرض Operations للموديل المعلن.
3. SDK يظل عامًا ويرجع بيانات Gateway دون قوائم Providers/Operations أو مخططات payload محلية؛ إضافة Provider أو Operation لا تحتاج فرعًا خاصًا في SDK.
4. التسجيل الإنتاجي تلقائي من مجلدات Provider المكتملة؛ عند بدء الخدمة تُفحص `definition.py` وتُتحقق Handler parity. لا يحتاج مسار الاسم إلى قائمة مركزية أو إعداد توجيه لكل Provider.
5. إشارة الصحة الأولية رصدية من نتيجة طلب `execute()` حقيقي؛ لا probe مستقل.

**مؤجل عمدًا:**

- إضافة Operation جديدة أو دعم تشغيلي لـ`moderate_content`؛ لا يعلن أي Provider مسجل العملية حاليًا.
- Streaming وJobs وAsset Reference، والفيديو.
- Agent Core، وحدود RPM داخله، وأي Dynamic Registry أو JSON Schemas.
- سياسة حقول Discovery إضافية غير المعلنة حاليًا؛ حقول Model support المعروفة مضافة صراحةً إلى عقد Gateway.

## 12. مسائل مستقبلية مفتوحة

- ما Use Cases التي تبرر تنفيذ Operation جديدة؟ الفيديو وتوليد الصوت والبحث على الويب مؤجلة حتى حاجة منتج واضحة.
- هل ومتى يُنفذ Provider حقيقي لـ`moderate_content`؟ يبقى غير معلن تشغيليًا حتى ذلك الحين.
- ما سياسة `tenant_id` طويلة الأمد إذا احتجنا صلاحيات مختلفة داخل Gateway واحد؟ الآن يظل audit context فقط.
- التعريف التفصيلي لصحة Provider والتاريخ/thresholds مؤجل؛ أي active probe يحتاج قرارًا مستقلًا.
- حد RPM سياسة Agent Core مستقبلًا؛ ضمانه عبر نسخ متعددة أو كل عملاء Gateway خارج نطاق SDK.
- ما أول binding للبث، وما الحد الأدنى من event types؟
- هل Jobs ذات نتيجة نهائية فقط أم تدعم progress events؟ وما retention/cancel semantics؟
- أين تُخزّن Assets ومن يصدر `asset_id` وكيف يصل Adapter إلى bytes؟
- ما سياسة التوافق المناسبة لحقول Discovery عامة جديدة؟
- كيف يُمثل Provider لا يستطيع حصر الموديلات مسبقًا من دون ادعاء دعم عام غير قابل للاختبار؟
