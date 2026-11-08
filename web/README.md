# انتشار داشبورد روی Cloudflare Pages

داشبورد کاملاً ایستا است: فقط `index.html`، `app.js` و `style.css`. هیچ Node.js، npm، bundler یا build command لازم نیست. داده‌ها از شاخهٔ جداگانهٔ `signals` مخزن عمومی خوانده می‌شوند.

## راهنمای ۱۰ گام
1. به [Cloudflare Sign up](https://dash.cloudflare.com/sign-up) بروید و حساب Cloudflare بسازید.
2. در داشبورد، **Workers & Pages → Create application → Pages → Connect to Git** را انتخاب کنید.
3. GitHub را متصل و دسترسی مخزن را تأیید کنید.
4. مخزن `hamedbenapart69-byte/Trade` را انتخاب کنید.
5. شاخهٔ انتشار را `main` قرار دهید؛ شاخهٔ `signals` فقط داده است و نباید شاخهٔ سایت باشد.
6. تنظیمات را دقیقاً وارد کنید: **Framework preset: None**، **Build command: خالی**، **Build output directory: web**. Root directory خالی باشد.
7. **Save and Deploy** را بزنید و صبر کنید تا Cloudflare وضعیت Deployment را موفق اعلام کند.
8. آدرس واقعی پروژه با قالب `https://<project-name>.pages.dev` را از داشبورد بردارید و باز کنید؛ نام دامنه از قبل قابل حدس نیست.
9. اگر داده بارگذاری نشد، متن خطا در خود صفحه نمایش داده می‌شود. در مرورگر دسکتاپ، Developer Tools → Console و Network را بررسی و وضعیت HTTP فایل‌های `signals.json` و `history.csv` را کنترل کنید.
10. آدرس واقعی `pages.dev` را ثبت و دسترسی از ایران را با اینترنت و VPN مورد استفادهٔ خود آزمایش کنید. دسترسی از ایران تا انجام این آزمون تأییدشده نیست.

## آدرس‌های داده
- [signals.json](https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/signals.json)
- [history.csv](https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/history.csv)

اگر GitHub raw از شبکهٔ کاربر در دسترس نباشد یا CORS/محدودیت شبکه مانع شود، رابط پیام «داده در دسترس نیست، لطفاً بعداً امتحان کنید» را نشان می‌دهد. این وضعیت به‌معنی خرابی محاسبهٔ سیگنال نیست.

## معیار تحویل
Deploy موفق به‌تنهایی PASS نهایی نیست. باید URL واقعی باز شود، دادهٔ آخرین اسکن و سابقه دیده شود و دسترسی از شبکهٔ مورد استفادهٔ مدیر بررسی شود. در نبود سیگنال واجد شرایط، صفحه باید `NO_QUALIFIED_SETUP` را نشان دهد و نباید سیگنال نمونه یا ساختگی نمایش دهد.
