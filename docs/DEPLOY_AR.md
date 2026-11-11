# دليل نشر «حكايتي» خطوة بخطوة (بدون برمجة)

التكلفة الشهرية التقريبية: **~7$ فقط** (خادم Render) + تكلفة الاستخدام الفعلي للذكاء الاصطناعي لكل كتاب.
باقي الخدمات مجانية: Netlify (الواجهة)، MongoDB Atlas M0 (قاعدة البيانات)، Cloudflare R2 (الملفات، 10GB مجاناً).

## 1) الخدمات التي تنشئ لها حساباً
| الخدمة | الغرض | ماذا تأخذ منها |
|---|---|---|
| MongoDB Atlas (M0 مجاني) | قاعدة البيانات | رابط الاتصال `MONGO_URL` (اسمح بالوصول من أي IP: 0.0.0.0/0) |
| Cloudflare R2 | تخزين الصور والملفات | اسم الـBucket + `S3_ENDPOINT_URL` + مفتاحا الوصول |
| Anthropic Console | كتابة القصص | `ANTHROPIC_API_KEY` |
| fal.ai | رسم الصور بوجه الطفل | `FAL_KEY` |
| Chargily (اختياري) | الدفع الإلكتروني | `CHARGILY_SECRET_KEY` — بدونه يعمل الدفع عند الاستلام فقط |

## 2) الخادم على Render
1. New → **Blueprint** → اختر مستودع GitHub → سيقرأ ملف `render.yaml` تلقائياً.
2. أدخل قيم المتغيرات المطلوبة (جدول 4). اختر خطة **Starter** (الخطة المجانية تنام فتتوقف معالجة الطلبات).
3. بعد النشر افتح `https://اسم-خدمتك.onrender.com/api/health` — يجب أن ترى `mongo: ok` و `storage: ok`.

## 3) الواجهة على Netlify
1. Add new site → Import from Git → اختر نفس المستودع (الإعدادات تُقرأ من `netlify.toml`).
2. في Site settings → Environment variables أضف: `REACT_APP_BACKEND_URL` = رابط خادم Render (بدون `/` في النهاية).
3. Deploy. ثم ارجع إلى Render وضع رابط Netlify في `FRONTEND_URL` و`CORS_ORIGINS`، ورابط Render في `BACKEND_PUBLIC_URL`.

## 4) متغيرات البيئة في Render
| المتغير | القيمة |
|---|---|
| MONGO_URL | رابط Atlas |
| DB_NAME | hikayati |
| JWT_SECRET | يُولَّد تلقائياً |
| ADMIN_EMAIL / ADMIN_PASSWORD | بريدك وكلمة سر قوية جديدة (≥ 12 حرفاً) |
| FRONTEND_URL / CORS_ORIGINS | رابط Netlify |
| BACKEND_PUBLIC_URL | رابط Render |
| ANTHROPIC_API_KEY / FAL_KEY | مفاتيحك |
| STORAGE_BACKEND | s3 |
| S3_BUCKET / S3_ENDPOINT_URL / S3_REGION=auto | من Cloudflare R2 |
| AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY | مفاتيح R2 |
| CHARGILY_SECRET_KEY | اختياري (للدفع الإلكتروني) |
| PAYMENT_MOCK | اتركه فارغاً في الإنتاج (للتجارب فقط: true) |

## 5) قائمة فحص قبل استقبال الزبائن
- [ ] جرّب طلباً كاملاً بصورة حقيقية وراجع الـPDF للطباعة.
- [ ] غيّر كلمة سر الأدمن، ولا تستخدم كلمات قديمة سبق نشرها.
- [ ] اجعل مستودع GitHub **خاصاً** إذا لم ترد نشر الكود.
- [ ] راجع صفحتي الخصوصية والشروط مع محامٍ (بيانات أطفال وصورهم).
- [ ] ضع تنبيه Telegram (`ALERT_TELEGRAM_*`) لتعرف بفشل أي طلب فوراً.
- [ ] راقب تكلفة fal وAnthropic من لوحتيهما في الأسابيع الأولى.
