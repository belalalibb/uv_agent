# 🐟 TinyFish AI Gateway Provider — Layer 1-3 Documentation

> **مزود منصة TinyFish AI Agent المدمج رسمياً داخل Gateway Service (Provider #14)**  
> **النمط المعماري:** Three-Layer Autonomous Provider with Auto-Refill Pool  
> **قانون العزل الصارم:** صفر استدعاءات لمجلد المزودين — ارتباط حصري ومستقل بـ `__دومينات مؤقته`.

---

## 🏛️ البنية المعمارية ثلاثية الطبقات (Three-Layer Architecture)

```
[Gateway Wire: POST /v1/execute]
           │
           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: definition.py & models_metadata.json          │
│ • Declaration: display_name="TinyFish AI"             │
│ • Credential Mode: PLATFORM (internal accounts pool)   │
│ • Operations: generate_text, analyze_vision            │
│ • Closed Capabilities: chat, reasoning, browser, vision│
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: adapter.py                                    │
│ • Strict Input Validation (messages, image_b64)        │
│ • Safe Error Normalization (12 Closed Categories)      │
│ • Zero Credential / Token / Internal Path Leakage      │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│ Layer 1: _core.py & accounts_tinyfish.json             │
│ • Zero-Browser Pure HTTP Engine (requests/httpx)       │
│ • FileLock Concurrency Protection on Accounts Pool     │
│ • Autonomous Clerk Signup Engine via Gmail Aliases     │
│ • Dynamic Integration with `__دومينات مؤقته`           │
└────────────────────────────────────────────────────────┘
```

---

## 📋 النماذج والعمليات المدعومة

### 1. النماذج المعتمدة بالأدلة القاطعة (`models_metadata.json`):
| النموذج | السياق (Context) | الوصف | التصنيف والقدرات |
|---------|-----------------|-------|-----------------|
| `mako` | 128,000 | نموذج TinyFish الافتراضي فائق السرعة لتصفح الويب واستخراج البيانات (V2 Mako) | محرك تصفح وإدراك أساسي |
| `eva` | 128,000 | المحرك الداخلي للوكيل المستقل لتنفيذ المهام (`model-owned-eva-amd`) | محرك التفكير والتوجيه الداخلي |
| `browser-agent` | 128,000 | وكيل تصفح الويب السحابي المستقل للمهام المركبة وتعدد الصفحات | وكيل تصفح شامل |
| `stealth-agent` | 128,000 | وكيل التصفح الخفي لتخطي أنظمة الحماية ومضادات البوتات مع البروكسي | حماية فائقة ومضاد بوتات |
| `tetra-engine` | 128,000 | البنية التحتية لتشغيل المتصفحات السحابية والتحكم بـ CDP (`tetra-anchor`) | محرك تحكم سحابي |
| `web-fetch` | 128,000 | محرك سحب النصوص وروابط الصفحات النظيفة وتصفية محددات CSS | استخراج محتوى سريع |
| `web-search` | 128,000 | محرك البحث الحي المصنف في الويب مع فلترة المواقع والتواريخ | بحث ويب متقدم |
| `web-monitor` | 128,000 | محرك الرادار السحابي لمراقبة تغيرات الأسعار والمخزون والإشعار الفوري | رادار وتنبيهات أسعار |

### 2. العمليات المدعومة (`operations`):
* `generate_text`: إرسال أسئلة أو مهام استخراج وتحليل عبر وكيل الويب الذكي.
* `analyze_vision`: تحليل الصور بدقة فائقة واستخراج التفاصيل والنصوص المرئية.

---

## 🔐 نظام إدارة الحسابات وطابور التزويد الفردي الصارم (Strict 1-Account FIFO Refill)

1. **طابور التزويد الفردي (Strict 1-Account Refill):**
   - مع كل استدعاء لدالة `ask()` يتم إدراج **حساب واحد فقط (`count=1`)** في طابور خلفي مستقل (`_ACCOUNT_REFILL_QUEUE`).
   - خيط العمل الخلفي ينشئ الحسابات **بالتتابع الصارم (واحد تلو الآخر)** لمنع حرق المزود أو التعرض للـ Rate Limit.
2. **ملف الحسابات المحلي:** `accounts_tinyfish.json` محمي بـ `FileLock` متزامن ضد أي تعارض أو Race Conditions بين العمليات المتزامنة.
3. **التجديد التلقائي (Zero-Browser Registration):**
   - يتصل بمكتبة `__دومينات مؤقته` ويستخدم مزودي `EmailnatorProvider` أو `TempNetProvider` للحصول على إيميل Dot-Gmail.
   - يستقبل كود التحقق OTP ويفعل الحساب ويستخرج مفتاح `sk-tinyfish-...` عبر Next.js Server Action ويحفظه في الخزان.
4. **متغيرات البيئة المتاحة:**
   - `GW_TINYFISH_API_KEY`: تعيين مفتاح ثابت اختياري لتجاوز خزان الحسابات.
   - `GW_TINYFISH_ACCOUNTS_FILE`: تحديد مسار مخصص لملف الحسابات.
   - `GW_TINYFISH_DISABLE_BG_REFILL`: تعطيل طابور التزويد الخلفي مؤقتاً عند الحاجة.

---

## 🛡️ الحصانة والعزل الهندسي (Strict Isolation Rule)
- المزود معزول تماماً ومكتفٍ بذاته داخل مجلد البوابة `__gateway-service`.
- لا يحتوي على أي استدعاءات لمجلد المزودين الخارجي.
- ارتباطه الخارجي الوحيد المسموح به هو مع مكتبة `__دومينات مؤقته` لتوليد بريد الجيميل المؤقت.
