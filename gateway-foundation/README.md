# Gateway Foundation — مراجعة وتصميم مقترح

**الحالة:** نُفّذ الحد الأدنى لدعم Provider defaults وmodel overrides وعرض الدعم الفعّال في Gateway في هذا الفرع؛ تظل Streaming/Jobs/Assets والفيديو وAgent Core خارج التنفيذ.
**تاريخ المراجعة:** 2026-11-08.

هذا مجلد مستقل يوثق مراجعة العقد ونتيجة التنفيذ المقصود. ما زال `__gateway-service/gateway/contracts.py` مصدر عقد Gateway، وقد أضيف إليه دعم Operations/Capabilities على مستوى Model مع إبقاء SDK ناقلًا عامًا دون قوائم أو payload schemas خاصة. لم يبدأ Agent Core، ولا سجل ديناميكي، ولا probes نشطة لصحة Provider.

## الاتجاه المعتمد مبدئيًا

- **Operation:** وظيفة موحّدة يستطيع Gateway توجيهها وتنفيذها فعليًا.
- **Capability:** خاصية تقنية يعلنها Provider أو Model ولا تُنسب إليهما إلا بدليل تنفيذ واختبار.
- **Tool:** وظيفة أعلى مستوى يمكن تركيبها مستقبلًا من Operations وسياسات وخدمات متعددة.
- Gateway هو مصدر الحقيقة للعقود والاكتشاف والدعم الفعلي. SDK ناقل عام للبيانات ولا يملك قوائم موازية. Agent Core خارج نطاق هذه المرحلة.
- في المسار الأقل تعقيدًا، Provider يعلن الدعم الافتراضي إذا كان ينطبق على كل موديل، والاختلافات فقط تُكتب كـmodel overrides اختيارية؛ Discovery يعرض النتيجة الفعّالة لكل موديل.
- الكتالوج التشغيلي لا يعرض عملية لمجرد أنها فكرة؛ يلزمها عقد واضح وتنفيذ واختبار. يجوز أن تكون **مفردات** القدرات أوسع من دعم المزوّدين الفعلي، بشرط عدم إعلان الدعم بلا إثبات.
- Streaming وعمليات Jobs طويلة التنفيذ نمطان مختلفان. Asset Reference مفهوم نقل عام، وليس عملية خاصة بكل Provider. يمكن تثبيت semantics في الوثيقة وتأجيل التنفيذ حتى أول استخدام حقيقي.
- `tenant_id` الحالي سياق audit فقط، وليس هوية أو صلاحية أو عزلًا لكل مستأجر. الفيديو ليس ضمن الحد الأدنى المقترح ويمكن تأجيله.
- الصحة الأولية تُستنتج من الطلبات الفعلية الناجحة عبر SDK/Gateway؛ لا health probe صناعي. حد RPM واختيار Provider مسؤولية Agent Core، ولا يتصل SDK بـupstream مباشرةً.
- [`SDK_API_APPROVAL_SUMMARY.md`](SDK_API_APPROVAL_SUMMARY.md) — قائمة واجهات SDK العامة وأشكال الإرجاع المنفذة والحدود المؤجلة.
- إضافة Provider يدعم Operations موجودة لا تتطلب تعديل SDK أو Agent Core. إضافة Operation جديدة تتطلب تغيير عقد Gateway وتنفيذًا واختبارات.

## محتويات المجلد

- [`CURRENT_CONTRACT_REVIEW.md`](CURRENT_CONTRACT_REVIEW.md) — مراجعة قراءة فعلية للعقد والكود الحاليين، مع الفجوات المثبتة ومسارات المصدر.
- [`OPERATIONS_AND_PROVIDERS.md`](OPERATIONS_AND_PROVIDERS.md) — قائمة Operations الحالية، مصفوفة المزوّدين المسجلين، والعمليات المرشحة وقرارات الإدراج/التأجيل.
- [`GATEWAY_FOUNDATION_CONTRACT_DRAFT.md`](GATEWAY_FOUNDATION_CONTRACT_DRAFT.md) — العقد الهندسي المقترح: الدعم حسب Model، Discovery، Streaming، Jobs، Assets، الأمن والتوافق.
- [`SDK_EXAMPLES.md`](SDK_EXAMPLES.md) — مدخلات ومخرجات SDK الحالية، ثم أمثلة مستقبلية موسومة بوضوح بأنها غير منفذة.
- [`SDK_API_APPROVAL_SUMMARY.md`](SDK_API_APPROVAL_SUMMARY.md) — واجهات SDK العامة وأشكال الردود المنفذة والحدود المؤجلة.
- [`PROVIDER_ONBOARDING.md`](PROVIDER_ONBOARDING.md) — مسار إضافة Provider أو Operation، مع فصل الوضع الحالي عن المقترح.

## ما نُفّذ وما بقي لاحقًا

نُفّذ دعم Provider defaults والـmodel overrides الاختيارية، وإظهار عمليات/قدرات كل Model بعد حل الدعم الفعّال، والتحقق من أن العملية المعلنة للموديل يمكن توجيهها إلى handler. تكامل SDK بقي عامًا: لا قوائم أو مخططات محلية، و`list_models()` يمرر metadata الفعّالة كما يرسلها Gateway بينما `list_operations()` يعرض defaults Provider. أُضيفت توضيحات للـAPI واختبار تكامل SDK↔Gateway دون إضافة واجهة خاصة بمزوّد أو عملية. الصحة الأولية تبقى رصدية من نجاح الطلب الفعلي؛ لم نضف probe مستقلًا أو سجل قياس.

ما يزال اختيار القائمة النهائية للـOperations ودلالة `moderate_content` غير المدعومة حاليًا، وتعريف الصحة المتقدم، وعقد Streaming، ودورة Job، وتفاصيل Asset Reference، وسياسة `tenant_id` بعد مرحلة audit-only خارج هذا التنفيذ. حد RPM سياسة Agent Core؛ ضمانه عبر عدة نسخ خارج النطاق الحالي. الفيديو مؤجل، ولم يبدأ Agent Core.

**قاعدة الحوكمة:** أي توسعة لاحقة مثل Agent Core أو probes أو Streaming/Jobs/Assets أو تعديل السلوك الأمني تحتاج اعتمادًا ونطاقًا منفصلين. تُسلّم تغييرات هذا النطاق عبر مراجعة PR إلى `main` بعد اجتياز الاختبارات؛ لا يُدفع مباشرةً إلى `main`.