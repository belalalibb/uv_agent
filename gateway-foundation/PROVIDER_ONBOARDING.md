# Provider Onboarding — المسار الحالي وإضافة عملية جديدة

**الحالة:** يدعم Gateway Provider defaults وmodel overrides الاختيارية، ويكتشف حزم Providers تلقائيًا من مجلداتها عند التشغيل. إضافة Provider لعملية موجودة لا تتطلب تعديل SDK أو Agent Core أو قائمة مركزية في `app.py`.

## المبدأ

إضافة Provider يدعم Operations موجودة يجب ألا تتطلب تغيير SDK أو Agent Core. التغيير محصور في حزمة Provider داخل Gateway: Definition وAdapter واختبارات تثبت الدعم. يكتشف Gateway الحزمة تلقائيًا من مجلدها؛ الإضافة لا تعني أن كل Model للمزوّد يدعم كل ما يستطيع المزوّد فعله.

في المسار المنفذ، العمليات والقدرات الافتراضية تكون على مستوى Provider إذا انطبقت على كل موديل. الحقل الاختياري `model.support` يذكر الاستثناء فقط؛ المزوّد الذي لا يملك استثناءات لا يكرر بيانات الدعم على كل موديل.

إذا أعلن مزوّدان اسم Model متطابقًا، يظل لكل منهما سجل مستقل: الهوية المركبة هي اسم Provider العام مع اسم الموديل لدى ذلك Provider. لا نضيف alias أو canonical model mapping في أقل بداية.

### Tenant في أقل بداية

`tenant_id` الحالي سياق audit فقط، وليس تفويضًا أو عزلًا. لا تستخدمه إضافة Provider لاختيار credential أو إخفاء موديل أو فرض quota. إذا احتاجت التطبيقات نطاقات صلاحيات مختلفة، تستخدم نشر Gateway منفصل وفق السياسة الحالية؛ التفويض per-tenant يحتاج قرارًا أمنيًا مستقلًا.

## المسار الحالي المثبت في الكود

1. إنشاء Provider package وتعريف عام له، مع `display_name`, `definition_version`, `credential_mode`, الموديلات والـOperations/Capabilities الافتراضية.
2. أضف `model.support.operations` أو `model.support.capabilities` فقط للموديل الاستثنائي. البعد الغائب يرث Provider default؛ والبعد الموجود يستبدله كاملًا.
3. تنفيذ `adapter.py` و`HANDLERS` لكل عمليات Provider الافتراضية واتحادات model overrides؛ لا stubs ولا دعم بالاستنتاج.
4. ضع الحزمة المكتملة في `providers/<slug>/`؛ Gateway يكتشفها عند التشغيل ويُجري التحقق من Definition وHandler parity. لا تضف اسمها إلى قائمة في `app.py`.
5. لا يلزم إدخال لكل Provider في `GW_PROVIDER_ALLOWLIST` أو `GW_ROUTE_MAP` لمسار الاسم والكتالوج. تبقى `GW_ROUTE_MAP` اختيارية فقط لعملاء `X-Route-Token` الأقدم.
6. تشغيل اختبارات الوحدة والعقد والتكامل المحلي ومجموعة Provider المنفصلة حسب اعتمادياتها.
7. التحقق أن Discovery يعرض الدعم الفعّال للموديل والاسم العام فقط، لا الـslug أو route token أو upstream identity.

## تفاصيل تعريف Provider وModel المنفذة الآن

1. **Provider Definition:** الاسم العام وطريقة الاعتماد وإصدار التعريف، مع عمليات/قدرات افتراضية صادقة، بلا أسماء داخلية على الحد العام.
2. **Model Definitions:** أسماء الموديلات وبياناتها العامة. لا تتكرر بيانات الدعم إذا كانت جميع الموديلات تتبع defaults Provider.
3. **Optional model overrides:** يضاف `model.support.operations` أو `model.support.capabilities` فقط للموديل المختلف؛ الحقل الموجود يستبدل default لذلك البعد، والغائب يرثه.
4. **Adapter Implementation:** handler فعلي لكل Operation ضمن defaults أو أي override؛ لا stubs ولا دعم بالاستنتاج.
5. **Capability claims:** استخدام مفاتيح Capability الحالية فقط عند ثبوت الدعم واختباره.
6. **Gateway Discovery & Routing:** يكتشف Gateway مجلدات Providers المكتملة تلقائيًا، ويتجاهل المجلدات ذات البادئة `_` أو `.`. لا يوجد تسجيل يدوي مركزي أو تسجيل ذاتي من العميل. خريطة التوجيه اختيارية لرموز `X-Route-Token` القديمة فقط.
7. **Tests & Discovery Verification:** parity بين التعريف والـhandlers، اختبار نجاح وفشل لكل Operation، اختبار الموديلات والـoverrides، واختبار أن الكتالوج يعرض الدعم الفعلي ولا يسرّب معلومات داخلية.
8. **No consumer edits:** لا إضافة alias أو Provider name أو Operation enum أو payload schema إلى SDK، ولا branch خاص بالمزوّد في Agent Core.

## مثال تعريف توضيحي

التعريف الفعلي في `definition.py` هو Python mapping يُتحقق منه إلى `ProviderDefinition`:

```python
DEFINITION = {
    "display_name": "Example Public Provider",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "operations": ["generate_text"],
    "capabilities": {"chat": True},
    "models": [
        {"name": "example-text-model", "context_window": 32_000},
        {
            "name": "example-vision-model",
            "context_window": 64_000,
            "support": {
                "operations": ["generate_text", "analyze_vision"],
                "capabilities": {"chat": True, "vision_input": True},
            },
        },
    ],
    "health_supported": False,
}
```

Gateway يعرض قيم الدعم الفعّالة في Discovery، ويفرض قائمة العمليات الفعّالة للموديل المعلن عند التنفيذ. حقول Capabilities هي metadata وصفية في v1؛ gate التنفيذ على مستوى الموديل يطبق Operations. يجب أن يكون لكل Operation في defaults أو overrides handler واختبار ناجح. الفيديو مؤجل، ولا يظهر `generate_video` في التشغيل الحالي أو في أقل بداية.

## عند إضافة Operation جديدة

إضافة Operation تختلف عن إضافة Provider:

1. توثيق semantics عامة للمدخلات والمخرجات والأخطاء ونمط التنفيذ.
2. قرار قبول Operation في عقد Gateway؛ إذا لم يوجد Adapter/Provider منفذ، تبقى خارج الكتالوج التشغيلي.
3. إضافة تنفيذ Gateway وAdapter مناسب، مع اختبارات عقد وتكامل.
4. نشرها لكل Model يدعمها فقط؛ لا تعميم على كل الموديلات.
5. تحديث Discovery/دليل المهندس ومثال SDK.
6. **لا تتغير واجهة SDK** ما دامت تنفذ Operation كنص وترجع JSON عامًا. قد تُضاف API transport methods للبث أو Jobs بعد اعتماد عقودها، لا لكل Operation على حدة.

## معيار قبول Provider جديد

- [ ] تعريف Provider/Models لا يعلن دعمًا غير مثبت.
- [ ] كل Model يرث دعم Provider بوضوح أو يملك override مختبرًا؛ لا يدّعي دعمًا غير معلوم.
- [ ] handler parity صحيح لكل عملية معلنة.
- [ ] أخطاء upstream تُحوّل إلى أخطاء Gateway الآمنة المعتمدة.
- [ ] لا أسرار أو route tokens أو slugs في output أو logs أو Discovery.
- [ ] Name-based catalog/selection يعمل من Definition المكتشفة دون خريطة أو allowlist لكل Provider؛ المزود المعطّل فقط يُخفى.
- [ ] مسار `X-Route-Token` القديم لا يتأثر إلا بقرار توافق منفصل.
- [ ] اختبارات Provider والعقد والتكامل المحلي ناجحة؛ المتطلبات الخارجية مصنفة منفصلة.
- [ ] لا تعديل خاص بالمزوّد في SDK أو Agent Core.

## حدود الأتمتة

الأتمتة المنفذة محدودة وواضحة: فحص مجلدات Providers عند بدء Gateway، مع التحقق من التعريفات وhandler parity. لا توجد واجهة تسجيل HTTP أو تسجيل ذاتي من العميل؛ والعمليات والقدرات تظل ضمن العقد المشترك لا Registry إضافية خاصة بالمستهلك.
