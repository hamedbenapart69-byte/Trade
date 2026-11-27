# ثبت رسمی منابع قانون اساسی و مرجع اصلی پروژه

## مرجع حاکم فعلی

**مجموعه منابع حاکم: MASTER SOURCE V21.0 + V21.1 Binding Addendum؛ همراه با دو دستور راهبردی مالک**

- فایل منبع: `T1.md`
- نسخه: `MASTER SOURCE V21.0`
- SHA-256 فایل منبع بررسی‌شده: `6a03106a413a773d5b8905a5f413bfbd5e89f5be45e0ae456c9f7956d4be94a0`
- وضعیت پذیرش: **ACCEPTED**
- مکمل اجرایی: `V21_EXECUTION_PROTOCOL_ADDENDUM(1).md`
- SHA-256 مکمل: `ef3a46e7ea137dc9ebaf7f8a891eb002b84788074d95ca51ce613bfecc19d9e4`
- سند معماری پذیرفته‌شده: `CFSS_V21_Architecture_Design_V1_FA.md`
- SHA-256 سند معماری: `f2949775dea43e410f6c63feb8e67c345a06dac556d48e381ea6d75e74adb762`
- تاریخ پذیرش مالک: 2026-11-23
- وضعیت Stage 0: **OWNER ACCEPTED / DESIGN PASS**
- وضعیت Stage 1: **IN PROGRESS — NOT YET ACCEPTED**

فایل‌های منبع بالا در بستهٔ ورودی مالک در دسترس بوده و SHA-256 آن‌ها در محیط اجرا محاسبه شده است. در این Commit، بایت‌های کامل فایل‌های منبع هنوز به‌عنوان کپی مستقل در مخزن ثبت نشده‌اند؛ بنابراین `REPOSITORY_SOURCE_COPY=NOT_YET_COMMITTED`. این ثبت hash جایگزین نسخهٔ باینری/متنی قابل بازیابی نیست. ثبت نسخهٔ مستقل مخزنی در ادامهٔ Stage 1 باید بدون تغییر محتوای منبع انجام شود.

V21.0 مرجع پایه معماری است و V21.1 به‌عنوان Binding Master Source Addendum، الزامات داده، استقلال تأمین‌کننده و انتخاب universe را تکمیل می‌کند. دو سند M1 و Master Owner Mission نیز ورودی‌های راهبردی مالک هستند. هیچ‌یک از این منابع مجوز کاهش hard gateها، جعل داده یا اجرای سفارش ایجاد نمی‌کند.

## پنج سند منبع بررسی‌شده در این دوره

| سند | نقش حاکمیتی | SHA-256 |
|---|---|---|
| T1.md — MASTER SOURCE V21.0 | مرجع پایه | 6a03106a413a773d5b8905a5f413bfbd5e89f5be45e0ae456c9f7956d4be94a0 |
| V21_EXECUTION_PROTOCOL_ADDENDUM(1).md | مکمل اجرایی V21.0 | ef3a46e7ea137dc9ebaf7f8a891eb002b84788074d95ca51ce613bfecc19d9e4 |
| v.21pro(1).md — V21.1 Exchange-Independent Data Federation & Nine-Asset Production Universe | Binding Master Source Addendum؛ والد: V21.0 | b05fd41b48f162caf0a40e401a97d6a7be0fe7f345026f29c9dbd33c9e828fc0 |
| m1.md — Project Decision Intelligence Protocol | دستور راهبردی مالک؛ تحقیق مستقل و تصمیم‌سازی | 31e7645060309801ca94d2f80df2b7812928a6cb9d1e5f03d49de053184be8e2 |
| untitled.md — Master Owner Mission | دستور مأموریت مالک؛ هدف و مرز محصول | 3359994927025d3446e709c3f0816ff30d186742622a7cd0c631bf9d3943b5ac |

هر پنج فایل در محیط پروژه خوانده و SHA-256 آن‌ها محاسبه شد. بایت‌های مستقل این پنج فایل هنوز در مخزن commit نشده‌اند؛ بنابراین این ثبت hash به‌تنهایی آرشیو قابل بازیابی محسوب نمی‌شود. V21.1 برای حوزه‌های مشخص‌شده در سند، الزام‌آور و مکمل V21.0 است؛ M1 و Master Owner Mission جهت راهبردی می‌دهند اما hard gateهای V21.0/V21.1 را لغو نمی‌کنند.

## تقدم و سازگاری منابع

- در موضوعات داده، provider independence، universe نه‌دارایی و معیارهای انتخاب، V21.1 به‌عنوان addendum الزام‌آور V21.0 اعمال می‌شود.
- M1 و Master Owner Mission هر دو ورودی معتبر مالک‌اند؛ تفسیر آن‌ها نباید با محدودیت‌های صریح C++ production، Telegram-only، zero-cost، manual-trade-only یا معیارهای آماری تعارض پیدا کند.

1. V21.0 بر هر متن متعارض V18.2 و اسناد قدیمی‌تر تقدم دارد.
2. محدودیت‌های سازگار V18.2 می‌توانند به‌عنوان سابقه یا کنترل تکمیلی حفظ شوند، اما Stageها و استراتژی‌های V18.2 به‌صورت خودکار مجوز فعال‌سازی در V21 محسوب نمی‌شوند.
3. LRT، NMT و VTM طبق بخش 2 سند V21 **REJECTED** هستند. بازاستفاده، تغییر نام یا تغییر جزئی پارامتر آن‌ها مجاز نیست؛ هر پژوهش آینده باید سازوکار، فرضیه، داده و اعتبارسنجی بنیاداً متفاوت و مستند داشته باشد.
4. وضعیت PASS تاریخی Stage 1 تا 5 در V18.2 فقط شواهد تاریخی همان دامنه است و به‌تنهایی PASS هیچ Stage در V21 را اثبات نمی‌کند.
5. فایل‌های تاریخی برای audit حفظ می‌شوند، اما اجرای منطق ردشده مجاز نیست. در PR حاکمیتی `governance-lock-v21`، workflowهای مشخص‌شده با کنترل job-level دائمی قرنطینه و با CI guard محافظت می‌شوند؛ این تغییر فقط پس از merge به main مؤثر خواهد شد.
6. هزینه‌های 0.04% commission و 0.02% slippage تا زمان ثبت تفسیر صریح one-way یا round-trip، برای آزمون‌های وابسته **OPEN** باقی می‌مانند؛ هیچ بک‌تستی نباید تفسیر مطلوب را بی‌صدا انتخاب کند.

## قیود عملیاتی حاکم V21

- زبان تولیدی: C++؛ Python فقط برای research/analysis/auxiliary/validation مجاز است.
- کانال انحصاری تحویل کاربر: Telegram.
- داده: فقط منابع عمومی؛ هیچ اتصال حساب صرافی، کلید خصوصی معامله یا سفارش‌گذاری مجاز نیست.
- هزینه: صفر؛ سرویس پولی و paid trial ممنوع.
- هر Stage باید L1 Data، L2 Compute و L3 Delivery را با شواهد مستقل بگذراند.
- داده و خروجی غیرواقعی باید صریحاً REAL / PROXY / UNAVAILABLE / DEGRADED برچسب بخورد.
- معیارهای آماری V21 نباید برای تولید سیگنال کاهش یابند.
- Stage بعدی فقط پس از PASS مستند و تأیید مالک آغاز می‌شود.

## منابع تاریخی و آرشیوشده V19.0

**وضعیت: ARCHIVED / SUPERSEDED BY V21.0 — NOT CONTROLLING**

- فایل اصلی: `UNIFIED_CRYPTO_FUTURES_SYSTEM_V19.0_MASTER.md`
- SHA-256 بایت‌های اصلی: `96dbd3bc5fe672a09f3f7bd680e40549c24a3df1b9da4ed0abc044498a3191bf`
- نسخهٔ لفظ‌به‌لفظ حفظ‌شده: `docs/archive/superseded/UNIFIED_CRYPTO_FUTURES_SYSTEM_V19.0_MASTER.md`
- مسیر قبلی در `docs/constitution/` اکنون فقط یادداشت ارجاع به آرشیو است.
- V19.0 از تاریخ پذیرش V21 در 2026-11-23 هیچ اختیار حاکمی ندارد.

## منابع تاریخی V18.2

**وضعیت: ARCHIVED / HISTORICAL / SUPERSEDED BY V21.0 — NOT CONTROLLING**

- فایل: `UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER-1(1).md`
- نسخه: `V18.2`
- SHA-256 فایل منبع بررسی‌شده: `e4e39fc1aec1924f93d9a480fadf6b2ad315388ebb5718ed9765ad89477b6a24`
- پذیرش قبلی: دستور مالک با عنوان «V18.2 MASTER SOURCE ACCEPTED — INITIATE C++ STAGE 1».
- Errata تاریخی: [V18.2 Owner Acceptance and Errata](V18.2_OWNER_ACCEPTANCE_AND_ERRATA.md)

این پذیرش تاریخی با پذیرش V21 در 2026-11-23 از نظر مرجع حاکم جایگزین شده است. رکورد آرشیو: `docs/archive/superseded/V18.2_ARCHIVE_RECORD.md`. SHA-256 بالا متعلق به بایت‌های فایل اصلی مالک است؛ در ابتدای این تغییر، کپی بایت‌به‌بایت آن در مخزن موجود نبود و این محدودیت صریحاً حفظ می‌شود. سابقه حذف نمی‌شود.

## منابع تاریخی V9.0 و V9.1

| نسخه | نام فایل | صفحات PDF | SHA-256 | وضعیت |
|---|---|---:|---|---|
| V9.0 | `rules 1(2).pdf` | 54 | `1dbdbcca127bd368b025a554b205970b7221fe22f68139908402c8d04f1db2f3` | Historical source |
| V9.1 | `rules 1.1(1).pdf` | 55 | `862307dbc8cae72bfac03de24686f52c0a28d170afe26a69d4e27f22a21cf0a8` | Historical source |

این دو PDF نباید پیش از داشتن نسخهٔ آرشیوی قابل بازیابی و تأیید hash حذف شوند. ثبت hash به‌تنهایی نسخهٔ پشتیبان باینری محسوب نمی‌شود.

## محدودیت‌های منبعی باز

- فایل اصلی V10.0 در بستهٔ فعلی در دسترس نیست؛ crosswalk بندبه‌بند آن همچنان **OPEN / NOT VERIFIED** است.
- بایت‌های کامل منبع V18.1 برای diff مستقیم در بستهٔ فعلی در دسترس نیستند؛ diff خط‌به‌خط V18.1 همچنان **OPEN / NOT VERIFIED** است.
- نسخهٔ مستقل V21 و Addendum هنوز در این مخزن commit نشده‌اند؛ تا ثبت و hash-check نسخه‌های مخزنی، پیوند منبع مخزنی مستقل **OPEN** است.
- این محدودیت‌ها به‌عنوان واقعیت ثبت شده‌اند و با حدس پر نمی‌شوند.

## دامنهٔ Stage 0

- بررسی منبع V21 و Addendum: **PASS — CONTENT/HASH VERIFIED**.
- پذیرش معماری V21 توسط مالک: **PASS — 2026-11-23**.
- پذیرش سند CFSS-V21-ARCH-DESIGN-V1: **PASS — 2026-11-23**.
- تبدیل V21 به مرجع حاکم در Source Register: **RECORDED ON THIS BRANCH; PENDING PR REVIEW/MERGE**.
- ثبت نسخهٔ مستقل فایل‌های V21 در مخزن: **OPEN**.
- این PASSها به معنی PASS شدن Stage 1، صحت تمام کدهای موجود یا سودآوری نیستند.

## سابقهٔ قبلی V9 و V18.2

- PR #81 در `main` با commit `5dcb05e39f8164d805cf32d7b72c421b44cf075a` ادغام شده بود.
- PASS اولیهٔ Stage 0 در سال 2026-11-11 فقط ثبت منابع V9 بود.
- V18.2 بعداً مرجع پذیرفته‌شده شد؛ اکنون V21.0 با پذیرش صریح مالک جایگزین آن به‌عنوان مرجع حاکم شده است.
