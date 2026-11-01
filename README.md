# ORAK-AI

منصة ويب عربية أولية لمساعد ذكاء اصطناعي، بواجهة محادثة عربية وخلفية Cloudflare Worker.

## المحرك الحالي

تستخدم النسخة الأولى Cloudflare Workers AI عبر binding باسم `AI`، والنموذج الافتراضي `@cf/meta/llama-3.1-8b-instruct`. لا يحتاج هذا الربط إلى وضع مفتاح مزود نموذج داخل ملفات المشروع.

## النشر التلقائي

1. افتحي إعدادات المستودع في GitHub: Settings → Secrets and variables → Actions.
2. أضيفي Repository secrets بالاسمين:
   - `CLOUDFLARE_API_TOKEN`: رمز API من Cloudflare بصلاحية نشر Workers.
   - `CLOUDFLARE_ACCOUNT_ID`: معرّف الحساب من Cloudflare.
3. بعد إضافتهما، أي تحديث على فرع `main` يشغّل GitHub Actions وينشر المشروع إلى Worker باسم `withered-wind-d7c9`.
4. يمكن تشغيل النشر يدوياً من تبويب Actions ثم Deploy ORAK AI to Cloudflare Workers ثم Run workflow.

## تشغيل محلي

1. ثبّتي Node.js.
2. شغّلي `npm install`.
3. شغّلي `npm run dev`.

## نقاط مهمة

- لا ترفعي API tokens أو كلمات مرور إلى GitHub.
- يجب أن تكون خدمة Workers AI متاحة ومفعّلة في حساب Cloudflare؛ وقد تخضع للاستهلاك والحدود أو الفوترة حسب خطة الحساب.
- النموذج الحالي Llama 3.1 8B؛ الصوت والرؤية والذاكرة الدائمة والوكلاء لم تُفعّل بعد.


## ORAK Voice Lab

بدأ تأسيس مختبر الأصوات المستقل. راجعي [voice-lab/README.md](voice-lab/README.md) للتصميم، وإعداد البيانات، وتشغيل واجهة الصوت الأولية.