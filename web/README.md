# انتشار داشبورد Futures روی Cloudflare Pages

داشبورد در مسیر `web/futures/` قرار دارد تا صفحهٔ اصلی قدیمی مخزن در `web/` دست‌نخورده بماند. این مسیر فقط HTML/CSS/JavaScript است و build step ندارد. داده‌ها از شاخهٔ جداگانهٔ `signals` خوانده می‌شوند.

## راهنمای ۱۰ گام
1. به [Cloudflare Sign up](https://dash.cloudflare.com/sign-up) بروید و حساب Cloudflare بسازید.
2. از داشبورد، **Workers & Pages → Create application → Pages → Connect to Git** را انتخاب کنید.
3. حساب GitHub را متصل و دسترسی مخزن را تأیید کنید.
4. مخزن `hamedbenapart69-byte/Trade` را انتخاب کنید.
5. پس از ادغام PR شماره ۲۶، شاخهٔ انتشار را `main` انتخاب کنید؛ شاخهٔ `signals` شاخهٔ داده است و نباید شاخهٔ سایت باشد.
6. تنظیمات را این‌طور وارد کنید: **Framework preset: None**، **Root directory: /**، **Build command: خالی**، **Build output directory: web/futures**.
7. **Save and Deploy** را بزنید و منتظر وضعیت موفق Deployment بمانید.
8. URL واقعی `https://<project-name>.pages.dev` را از داشبورد بردارید و باز کنید. نام پروژه را حدس نزنید.
9. در صفحه باید وضعیت اسکن و سیگنال‌ها دیده شود. اگر فایل JSON یا CSV دریافت نشد، پیام خطای روشن نمایش داده می‌شود. در مرورگر دسکتاپ، Developer Tools → Network/Console را برای درخواست‌های `signals.json` و `history.csv` بررسی کنید.
10. URL واقعی را در GitHub Repository Variables با نام `DASHBOARD_URL` ثبت کنید و دسترسی URL را از شبکهٔ واقعی خود در ایران آزمایش کنید. تا قبل از این آزمایش، دسترسی از ایران تأییدشده نیست.

## منابع داده
- [signals.json](https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/signals.json)
- [history.csv](https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/history.csv)

## پذیرش
Cloudflare Deploy به‌تنهایی PASS نیست. باید URL واقعی باز شود، دادهٔ واقعی از شاخهٔ `signals` بارگذاری شود و دسترسی از شبکهٔ هدف بررسی شود. در نبود فرصت معتبر، صفحه باید وضعیت `NO_QUALIFIED_SETUP` را نشان دهد؛ هیچ معاملهٔ نمونه‌ای در رابط قرار داده نشده است.
