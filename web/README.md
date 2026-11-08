# داشبورد سیگنال فیوچرز — Cloudflare Pages

وب‌اپ کاملاً ایستا است: HTML، CSS و JavaScript ساده؛ بدون npm، build، React یا bundler.

## منبع داده
- JSON: https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/signals.json
- CSV: https://raw.githubusercontent.com/hamedbenapart69-byte/Trade/signals/history.csv

داده‌ها از شاخه مستقل signals خوانده می‌شوند؛ بنابراین با هر تغییر داده نیازی به Deploy مجدد وب‌اپ نیست.

## راهنمای ۱۰ گام Deploy
1. وارد https://dash.cloudflare.com/ شو و حساب بساز یا وارد شو.
2. از داشبورد Workers & Pages را باز کن.
3. Create application را انتخاب کن.
4. گزینه Pages را انتخاب کن.
5. روی Connect to Git بزن.
6. GitHub را مجاز کن و مخزن hamedbenapart69-byte/Trade را انتخاب کن.
7. شاخه Production را main بگذار. اگر تغییرات وب هنوز به main نرسیده‌اند، PR مرحله اول باید Merge شود؛ شاخه stage-1-data-layer-v1 فقط برای Preview مناسب است.
8. Framework preset را None بگذار، Build command را خالی و Build output directory را web وارد کن.
9. Save and Deploy را بزن و پایان Deploy را صبر کن.
10. آدرس واقعی *.pages.dev را باز کن؛ زمان تولید، منبع داده، تعداد نمادها و کارت‌های سیگنال باید نمایش داده شوند. سپس در GitHub Variables متغیر DASHBOARD_URL را با همین آدرس بساز.

## مدیریت خطا
اگر JSON به‌علت 404، خطای شبکه یا محتوای نامعتبر بارگذاری نشود، پیام «داده در دسترس نیست، لطفاً بعداً امتحان کنید» نمایش داده می‌شود. اگر فقط CSV در دسترس نباشد، سیگنال‌ها باقی می‌مانند و جدول تاریخچه پیام جداگانه می‌دهد.

## آزمون
هر دو URL بالا را جداگانه باز کن؛ سپس در مرورگر DevTools → Network پاسخ HTTP 200 را بررسی کن. دسترسی از ایران باید با اینترنت خودت آزمایش شود؛ نتیجه GitHub Actions جایگزین آن نیست.

Cloudflare فقط شاخه انتخاب‌شده را منتشر می‌کند. شاخه signals داده است و نباید شاخه وب‌اپ باشد.
