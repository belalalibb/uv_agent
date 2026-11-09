# مراجعة العقد الحالي واستخراج الفجوات

**نوع العمل:** مراجعة خط الأساس قبل إضافة دعم Model في هذا الفرع. البنود أدناه تصف العقد الذي فُحص أولًا بتاريخ 2026-11-08؛ تفاصيل الحد الأدنى الذي نُفذ لاحقًا موجودة في [`GATEWAY_FOUNDATION_CONTRACT_DRAFT.md`](GATEWAY_FOUNDATION_CONTRACT_DRAFT.md) و[`SDK_API_APPROVAL_SUMMARY.md`](SDK_API_APPROVAL_SUMMARY.md).

> **تنبيه الحالة:** العبارات التالية عن غياب دعم Model تصف لقطة ما قبل التنفيذ، وليست وصفًا للحالة الحالية. التنفيذ الحالي يعرّف `ModelSupportOverride`، ويعرض `operations` و`capabilities` الفعّالتين لكل Model، ويفرض Operations للموديل المعلن. SDK يمرر هذه البيانات دون قوائم أو مخططات محلية؛ التفاصيل الدقيقة في عقد الخدمة وملخص SDK المرتبطين أعلاه.

## الخلاصة التنفيذية

العقد الحالي يوفّر مسار تنفيذ JSON موحّدًا، قائمة Operations مغلقة، تعريف Provider على مستوى المزوّد، واكتشافًا عامًا للكتالوج. لكنه لا يقدّم بعد العلاقة بين كل Model وعملياته، ولا عقدًا عامًا للـStreaming أو Jobs أو Asset References. كما أن SDK يمرّر JSON خامًا، لكن Gateway نفسه يستخدم نماذج استجابة مغلقة؛ لذلك لا تكفي مرونة SDK وحدها لجعل معلومات مستقبلية غير معروفة قابلة للظهور من Gateway.

## ما كان يثبته تنفيذ خط الأساس عند المراجعة

### 1. Operations والعقد التنفيذي

في `__gateway-service/gateway/contracts.py`:

- `GatewayOperation` مجموعة مغلقة من ثماني قيم: `generate_text`, `generate_image`, `transcribe_audio`, `synthesize_speech`, `create_embeddings`, `rerank_documents`, `moderate_content`, `analyze_vision`.
- `run_provider_agent`, `upload_asset`, و`download_asset` مستثناة صراحةً من v1؛ تعريف Provider يحوي أيًا منها يُرفض.
- `RequestEnvelope.operation` من نوع `GatewayOperation`، أي أن تمرير SDK لأي نص لا يجعل العملية مقبولة تلقائيًا لدى Gateway.
- `payload` و`output` كائنان عامان (`dict[str, Any]`) في شكل التنفيذ؛ وتحتوي `docs/CONTRACT.md` كذلك على جداول وأمثلة حمولة لكل عملية. لا توجد نماذج مشتركة typed في SDK لكل عملية.
- خطأ تنفيذ العملية غير المدعومة من Provider يرجع في Envelope تنفيذ فاشل، عادةً HTTP 200 مع `unsupported_capability`، وليس دليلًا على أن العملية متاحة.

### 2. تعريفات Provider وModel وCapability

- `ProviderDefinition` يحوي `display_name`, `definition_version`, `credential_mode`, قاموس `capabilities: dict[str, bool]`, قائمة `operations`, قائمة `models`, و`health_supported`.
- مجموعة مفاتيح القدرات مغلقة حاليًا عند 14 قيمة مسطحة: `chat`, `reasoning`, `code`, `vision_input`, `image_generation`, `audio_input`, `audio_output`, `file_upload`, `browser`, `agent_module`, `embeddings`, `rerank`, `moderation`, `tool_use`.
- `DeclaredModel` لا يحمل إلا `name` و`context_window`. لا توجد قائمة عمليات أو قدرات على مستوى الموديل.
- بعض ملفات `models_metadata.json` تحتوي حقولًا مثل `label`, `dimensions`, وقدرات موديل؛ لكن تعريفات Provider الحالية تُسقط معظم هذه الحقول عند بناء `DeclaredModel`. مثال Groq يعرض للمستهلك اسم الموديل ونافذة السياق فقط، لا `label` أو قدرات الموديل من ملف المصدر.
- الدعم الحالي للقدرات على مستوى Provider فقط وبـboolean؛ لا يميّز العقد بوضوح بين «غير معلن» و«مدعوم» على مستوى كل Model.

### 3. Discovery وSecurity

- المسارات الحالية: `GET /v1/providers`, `GET /v1/describe`, `GET /v1/models`, `GET /v1/health`, `POST /v1/execute`, و`GET /healthz`.
- `/v1/providers` يعرض كل Provider مكتشف ومفعّل من مجلدات `providers/` دون الحاجة إلى `GW_ROUTE_MAP` أو allowlist لكل Provider. لا تُكشف slugs الداخلية أو route tokens.
- اختيار `X-Provider-Name` يحل الاسم العام من تعريفات الحزم المكتشفة ويتطلب سر Gateway فقط؛ `X-Route-Token` القديم مسار منفصل يتطلب سر Gateway وربطًا نشطًا في `GW_ROUTE_MAP` الاختيارية. لا يقبل الطلب محددي اختيار معًا. القيمة غير الفارغة القديمة لـ`GW_PROVIDER_ALLOWLIST` مرفوضة عند بدء الخدمة.
- هذه حدود نشر Gateway؛ سر Gateway لخدمة خلفية موثوقة وليس لمتصفح أو تطبيق عميل. كل حامل للسر يشارك صلاحيات كل Providers المكتشفة والمفعّلة في النشر؛ لا يوجد تفويض لكل مستخدم في v1.
- `tenant_id` مطلوب في RequestEnvelope، وله قيمة افتراضية `default_platform_tenant` في SDK، ويمرره Gateway إلى ProviderContext. التعليق التعاقدي الحالي يصفه صراحةً بأنه evidence/audit فقط؛ لا توجد هوية tenant موثوقة أو صلاحيات/عزل per-tenant. لا ينبغي اعتباره authorization؛ سر Gateway مشترك على مستوى النشر ويتيح Providers المكتشفة والمفعّلة.

### 4. Streaming وJobs وAssets

- واجهات Gateway الحالية ترجع JSON؛ لا يوجد endpoint أو شكل Events عام للبث، ولا `StreamingResponse` في واجهة التنفيذ.
- قد تستخدم بعض Adapters اتصالات stream أو polling داخليًا مع upstream، لكن العميل يرى استجابة Gateway النهائية فقط؛ ذلك ليس عقد Streaming أو Job للمستهلك.
- لا توجد حالة Job عامة، أو `job_id`, أو واجهات status/result/cancel.
- لا يوجد شكل `Asset Reference` مشترك. `payload` عام، و`upload_asset` و`download_asset` خارج v1؛ تعامل بعض Adapters مع المرفقات داخليًا لا يساوي دعمًا موحدًا عند حد Gateway.

### 5. SDK الحالي

في `gateway_sdk/`:

- SDK async ويصدّر `GatewayClient`/`Gateway` و`GatewayConfig` واستثناءات النقل والبروتوكول وGateway.
- `discover()` يقرأ كتالوج Gateway عند عدم ضبط `provider_routes`. وجود خريطة legacy محلية يجعل الاكتشاف محصورًا بالأسماء المضبوطة ويستخدم `X-Route-Token` للتوافق.
- `describe()` يرجع manifest خامًا؛ `list_models()` يرجع قائمة الموديلات؛ `list_operations()` يرجع قائمة عمليات Provider، لا عمليات كل Model.
- `execute()` يأخذ Provider وModel كلًا على حدة؛ لذلك تطابق اسم Model عند Providerين لا يسبب تصادمًا في المسار الحالي. لا يوجد alias/canonical-model mapping عالمي، ولا نحتاج إضافته: اختيار SDK يحدد Provider واسم الموديل معًا.
- `execute()` يقبل اسم Operation كنص و`payload` عامًا، ويرجع JSON الخام عند النجاح. Gateway يظل صاحب التحقق والتنفيذ؛ وأخطاء التنفيذ تتحول إلى `GatewaySDKError` حتى عند Envelope فاشل بحالة HTTP 200.
- SDK لا يفلتر حقول JSON غير المعروفة بعد وصولها؛ لكن نماذج Gateway الحالية مشتقة من `ContractModel(extra="forbid")`، كما أن Projection الاكتشاف لا يحتوي حقولًا إضافية. إذن حفظ الحقول في SDK قائم جزئيًا، أما تمريرها من Gateway فيحتاج قرار عقد وتنفيذ.

### 6. إضافة Provider في خط الأساس

- `ProviderRegistry.discover_packages()` يمسح مجلدات Providers تلقائيًا، ويتجاهل `_example` و`_template` وسائر المجلدات ذات البادئة `_`/`.`؛ يتحقق من `definition.py` ويختبر parity مع `adapter.py`. لا توجد قائمة Providers ثابتة في `app.py`.
- يلزم إضافة حزمة Provider مكتملة واختبارها فقط. لا يلزم تحديث SDK أو إعداد `GW_ROUTE_MAP`/`GW_PROVIDER_ALLOWLIST` لمسار الاسم؛ الخريطة اختيارية للتوافق القديم مع `X-Route-Token`.
- اكتشاف مجلدات Providers صار جزءًا من تركيب التطبيق الفعلي؛ أي مجلد Provider مكتمل وغير محجوب يُسجل تلقائيًا عند بدء Gateway.

## مصفوفة المزوّدين المسجلين حاليًا

الأعداد أدناه عدد أسماء الموديلات في ملفات metadata المحلية وقت المراجعة. العمليات والقدرات هي ما تعلنه ملفات `definition.py` حاليًا، وليست وعدًا بأن كل Model يدعمها.

| الاسم العام | Models | Operations المعلنة | Capabilities الإيجابية المعلنة حاليًا |
|---|---:|---|---|
| DeepAI | 14 | `generate_text`, `analyze_vision`, `transcribe_audio` | `chat`, `vision_input`, `audio_input`, `file_upload`, `reasoning`, `code` |
| Freebuff AI | 1 | `generate_text` | `chat`, `reasoning`, `code` |
| Groq | 2 | `generate_text` | `chat`, `reasoning`, `code` |
| IvyCraft AI | 3 | `generate_text`, `generate_image`, `synthesize_speech` | `chat`, `reasoning`, `code`, `image_generation`, `audio_output`, `audio_input`, `file_upload` |
| LlamaCoder Together AI | 16 | `generate_text`, `analyze_vision` | `chat`, `vision_input`, `file_upload`, `reasoning`, `code` |
| NoteGPT AI | 3 | `generate_text`, `synthesize_speech` | `chat`, `reasoning`, `code`, `audio_output` |
| Overchat AI | 8 | `generate_text`, `analyze_vision`, `transcribe_audio` | `chat`, `reasoning`, `code`, `vision_input`, `audio_input`, `file_upload` |
| Parallel AI | 5 | `generate_text` | `chat`, `reasoning`, `code`, `agent_module`, `tool_use` |
| RunPod Console Assistant | 3 | `generate_text`, `analyze_vision` | `chat`, `reasoning`, `code`, `vision_input`, `file_upload` |
| Syntx AI | 28 | `generate_text`, `analyze_vision` | `chat`, `vision_input`, `reasoning`, `code`, `browser` |
| TinyFish AI | 8 | `generate_text`, `analyze_vision` | `chat`, `reasoning`, `browser`, `vision_input`, `tool_use`, `agent_module` |
| Upstage AI | 4 | `generate_text`, `analyze_vision` | `chat`, `reasoning`, `code`, `vision_input`, `browser`, `tool_use`, `file_upload`, `agent_module` |
| Voyage AI | 9 | `create_embeddings`, `rerank_documents` | `embeddings`, `rerank`, `code`, `vision_input`, `file_upload` |
| YouMind AI | 8 | `generate_text` | `chat`, `reasoning`, `code` |

الـunion الفعلي لعمليات هذه التعريفات يحتوي سبع عمليات فقط؛ `moderate_content` موجود في Enum والوثيقة الحالية، لكن لا يظهر في تعريف أي من المزوّدين الأربعة عشر وقت المراجعة. هذه فجوة بين مفردات العقد والدعم التشغيلي، وليست ادعاءً بأن moderation يعمل.

## الفجوات التي رصدها خط الأساس وحالتها بعد التحديث

1. **أُغلقت في هذا الفرع:** دعم Provider defaults مع model overrides اختيارية، وعرض الدعم الفعّال لكل Model في Discovery.
2. **أُغلقت في هذا الفرع:** Runtime يفرض قائمة Operations الفعّالة للموديل المعلن؛ اسم غير مدرج يستخدم Provider defaults حفاظًا على التوافق.
3. **خارج هذا التحديث:** لا إضافة Operation جديدة؛ `moderate_content` لا يعلنه أي Provider مسجل. الفيديو مؤجل.
4. **مؤجلة:** عقد Streaming وJobs عامة، بما فيها الحالة والنتيجة والإلغاء.
5. **مؤجلة:** Asset Reference وآلية الملكية والوصول وانتهاء الصلاحية.
6. **أُغلقت لدعم Model الحالي:** حقلا `operations` و`capabilities` معلنان صراحةً في Discovery. ما زال أي حقل Discovery مستقبلي يحتاج تغيير عقد Gateway؛ SDK يمرر ما يتلقاه ولا يتحكم بما يصدره الخادم.
7. **أُغلقت في التنفيذ:** Provider onboarding يصف الاكتشاف التلقائي من مجلدات الحزم؛ لا حاجة لقائمة مركزية أو إدخالات إعداد لكل Provider.
8. **كما هو:** `health_supported` لا يطلق probe حاليًا؛ `project_health()` يرجع `UNKNOWN`.
9. **كما هو:** `tenant_id` سياق audit فقط؛ لا يوجد تفويض أو عزل لكل tenant داخل نشر Gateway مشترك.
10. **مؤجل بلا حاجة مثبتة:** اسم Model المتكرر يظل مرتبطًا بكل Provider؛ لا معرّف عالمي.

## مصادر المراجعة

- `__gateway-service/gateway/contracts.py`
- `__gateway-service/gateway/routes.py`
- `__gateway-service/gateway/discovery.py`
- `__gateway-service/gateway/provider_registry.py`
- `__gateway-service/gateway/route_registry.py`
- `__gateway-service/app.py`
- `__gateway-service/docs/CONTRACT.md` و`__gateway-service/docs/ONBOARDING.md`
- `gateway_sdk/client.py`, `gateway_sdk/discovery.py`, `gateway_sdk/execution.py`, `gateway_sdk/models.py`
- `__gateway-service/providers/*/definition.py` و`models_metadata.json`
