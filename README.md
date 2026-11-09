# Gateway SDK

مرحلة أولى انتقالية من SDK خفيف وغير مرتبط بقائمة عمليات ثابتة. يرسل العمليات والـ`payload` كـJSON عام، ويعيد الاستجابة كما وردت من Gateway دون تعريف نماذج ثابتة لكل عملية.

## التثبيت والتشغيل

```bash
pip install -e .
```

الإعدادات اللازمة للاتصال بـGateway:

- `GATEWAY_URL` — عنوان Gateway؛ الافتراضي محلي على `127.0.0.1:8800`.
- `GATEWAY_API_KEY` — مفتاح الاتصال؛ يقبله العميل باسم `api_key`.
- `ROUTE_TOKEN_<PROVIDER>` — **اختياري وانتقالي** للتوافق مع Gateway الأقدم. إذا وُجد، يرسل SDK رمز التوجيه في ترويسة `X-Route-Token`. وإلا يرسل اسم المزوّد في `X-Provider-Name`، ويتولى Gateway حله داخليًا. لا يظهر رمز التوجيه في عنوان URL أو جسم الطلب.

على خدمة Gateway، يحدد `GW_PROVIDER_ALLOWLIST` الـslugs الداخلية المسموح بها لمسار الاسم والكتالوج، وهو فارغ افتراضيًا (رفض افتراضي). لا يظهر المزوّد في الكتالوج ولا يُقبل بالاسم إلا إذا كان مسجّلًا ومفعّلًا وله أيضًا مدخل توجيه فعّال في `GW_ROUTE_MAP`؛ يبقى رمز التوجيه داخل Gateway ولا يحتاج SDK إلى إرساله عند اختيار الاسم. خلال فترة التوافق، يظل `X-Route-Token` القديم غير مقيّد بهذه القائمة، لكنه يتطلب سر Gateway ومدخلًا فعّالًا مطابقًا في خريطة التوجيه. القائمة تخص نشر Gateway كله، لا مستخدمًا بعينه. سر Gateway مخصص لخدمة خلفية موثوقة فقط؛ لا تضعه في متصفح أو تطبيق عميل نهائي. وإذا احتاجت تطبيقات إلى نطاقات اسم مختلفة، فاعزلها في عمليات نشر Gateway منفصلة.

يمكن تمرير `base_url` و`api_key` مباشرةً إلى العميل، أو قراءتهما من البيئة:

```python
import asyncio
import os

from gateway_sdk import GatewayClient


async def main() -> None:
    async with GatewayClient(
        base_url=os.environ["GATEWAY_URL"],
        api_key=os.environ["GATEWAY_API_KEY"],
    ) as gateway:
        providers = await gateway.discover()
        provider = await gateway.describe("groq")
        operations = await gateway.list_operations("groq")  # defaults على مستوى Provider
        models = await gateway.list_models("groq")          # كل Model وعملياته/قدراته الفعّالة

        result = await gateway.execute(
            provider="groq",
            operation="generate_text",
            model="...",
            payload={"messages": [{"role": "user", "content": "..."}]},
        )

        gateway_health = await gateway.check_gateway_health()
        provider_health = await gateway.check_provider_health("groq")


asyncio.run(main())
```

يعيد `list_models()` بيانات Gateway الخام لكل موديل، بما فيها `operations` و`capabilities` الفعّالتان بعد تطبيق Provider defaults والـmodel overrides. لا يحسب SDK التوريث ولا يعرّف مخططًا موازيًا؛ والحقول المستقبلية تظل متاحة للمستهلك. أما `list_operations()` فيعيد defaults على مستوى Provider فقط.

## حدود المرحلة الانتقالية

- `execute()` لا يقيّد `operation` بـ`Enum`، ولا يتحقق من حقول `payload` محليًا؛ يمررها إلى Gateway.
- `discover()` يقرأ الكتالوج الموثّق من Gateway (`GET /v1/providers`) عندما لا توجد خريطة محلية للرموز. إذا كانت `ROUTE_TOKEN_<PROVIDER>` مضبوطة، يستخدم مسار التوافق القديم ويكتشف تلك الأسماء فقط.
- يعيد `describe()` و`discover()` البيانات الخام من Gateway. `list_operations()` يعرض defaults الخاصة بالمزوّد، بينما يقدم `list_models()` الدعم الفعّال لكل موديل دون مخطط محلي.
- مخططات `Input Schema` و`Output Schema` غير متاحة من Gateway الحالي، لذلك لم يُضف العميل API تخمينيًا لها.
- `/healthz` يفحص حياة Gateway. فحص المزوّد الحالي قد يعيد `UNKNOWN` لأن Gateway لا ينفذ فحصًا فعليًا للمزوّد بعد.

في خدمة Gateway المستعادة، حلّ الاسم والكتالوج أصبحا مملوكين لـGateway. يبقى `X-Route-Token` مدعومًا للتوافق؛ لا يُحدّد موعد إيقافه قبل إعلان خطة انتقال صريحة.
