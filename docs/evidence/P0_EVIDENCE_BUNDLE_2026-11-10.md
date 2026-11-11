# بسته شواهد P0 — 2026-11-10

## حکم نهایی

**P0 = PARTIAL / NOT FULL PASS**

زیرساخت قرنطینه موتور یک‌ساعته، دادهٔ تاریخی ۱۵ دقیقه‌ای، Deduplication، Manifest، Sanity Check بک‌تست و آزمون Mock تلگرام شواهد موفق دارند. با این حال، تحویل زندهٔ تلگرام به کانال آزمایشی و وضعیت Production در Cloudflare هنوز به‌صورت مستقل تأیید نشده‌اند؛ بنابراین مجوز ورود به P1 صادر نمی‌شود.

## 1. شواهد دادهٔ 15m و Deduplication

- Workflow Run موفق: [42894604222](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894604222)
- Branch اجرا: `p0-stage1b-run-20261110`
- Workflow commit: `2225977e30616c969a4c2564bd05e68db4d84e46`
- Stage1b engine/data-adapter commit: `666d47f28c430985d7caa09a6a549c5d2a3dd403`
- منبع دادهٔ قبل از نرمال‌سازی: `7b4cee7c6f5ebbe83cfe6271ed487d7ac37dee82`
- Commit نهایی شاخهٔ `market-data`: [24bd456](https://github.com/hamedbenapart69-byte/Trade/commit/24bd4562a8e8f79d9af5743e936edf6892c838e5)

### نتیجهٔ واقعی

| معیار | نتیجه |
|---|---:|
| نمادهای Universe | 27 |
| نمادهای کامل | 27/27 |
| نمادهای تازه | 27/27 |
| کندل هر نماد | 70,080 |
| مجموع ردیف‌های baseline | 1,892,160 |
| فایل‌های فعال baseline | 27 |
| Snapshotهای قدیمی خارج‌شده از مسیر فعال | 54 |
| نماد فاقد baseline معتبر | 0 |
| وضعیت Data Gate | PASS |

بازهٔ baseline: از 2024-11-10 تا آخرین کندل ذخیره‌شدهٔ 2026-11-09 ساعت 23:45 UTC. در زمان اجرای بررسی زنده، آخرین کندل بسته‌شده تا 2026-11-10T20:15:00Z بررسی شد؛ سن داده برای هر 27 نماد 7.77 دقیقه بود.

### Manifest

- فایل: [datasets/stage1b/manifest.json](https://github.com/hamedbenapart69-byte/Trade/blob/market-data/datasets/stage1b/manifest.json)
- Aggregate SHA-256:

```
2f9db1456664408aa65cd24a7263ea90334daa5dd3a79ff544c2f7cd8333fc7b
```

- تعداد فایل‌های Manifest: 27
- تعداد baseline: 27
- تعداد live-tail پایدارشده در این Manifest: 0
- هش هر فایل Parquet در Manifest ثبت شده است.
- هش Aggregate از فهرست مرتب‌شدهٔ metadata و SHA-256 فایل‌ها به‌صورت مستقل دوباره محاسبه شد و دقیقاً با مقدار ثبت‌شده تطبیق داشت.
- نسخه‌های خام از تاریخچهٔ Git قابل بازیابی‌اند؛ هیچ force-push یا بازنویسی تاریخچه انجام نشده است.

**محدودیت دامنهٔ Manifest:** هش بالا فقط baselineهای پایدار را پوشش می‌دهد. دادهٔ همان روز برای کنترل تازگی به‌صورت ephemeral استفاده شد و در این Run به‌عنوان live-tail پایدار در Manifest ثبت نشد. بنابراین نباید این Manifest را هش دادهٔ زندهٔ همان روز تلقی کرد.

### کیفیت منبع

- تاریخچهٔ baseline از Binance Vision Klines.
- 25 نماد در بررسی زنده از OKX Public Swap Candles.
- HOTUSDT از MEXC Futures 15m.
- 1000PEPEUSDT از OKX Spot با مقیاس‌دهی proxy.
- CVD واقعی در دسترس نبود: منبع CVD با برچسب PROXY/UNAVAILABLE ثبت شده است؛ دادهٔ واقعی aggTrades/CVD تأیید نشده است.

### مرز اجرای P0

در Manifest مقدار `signal_engine_executed=false` ثبت شده است. این Run فقط نگهداری و اعتبارسنجی داده را اجرا کرد؛ موتور LRT 15m، تولید سیگنال و انتشار به شاخهٔ signals اجرا نشد.

## 2. قرنطینهٔ موتور 1h

- [PR #55 — قرنطینهٔ موتور قدیمی](https://github.com/hamedbenapart69-byte/Trade/pull/55)
- [PR #57 — Fail-Closed Guard](https://github.com/hamedbenapart69-byte/Trade/pull/57)
- [PR #58 — وضعیت داشبورد و system_status.json](https://github.com/hamedbenapart69-byte/Trade/pull/58)

مقادیر نهایی در `signal_autopilot/config.json` و `web/futures/system_status.json`:

- `lifecycle = LEGACY_RESEARCH_ONLY`
- `production_enabled = false`
- `market_scan_enabled = false`
- `dashboard_signal_publication_enabled = false`
- `telegram_signal_delivery_enabled = false`
- `output_state = NO_QUALIFIED_SETUP`
- `reason = LEGACY_ENGINE_QUARANTINED`

معنای NO_QUALIFIED_SETUP در این وضعیت: موتور قرنطینه است و ارزیابی زندهٔ بازار انجام نشده؛ این عبارت ادعای اسکن تازه یا نبود فرصت در بازار نیست.

### شواهد اجرا

- CI: [42890125098](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42890125098)
- Pytest: [42890125150](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42890125150)
- تست مستقیم Fail-Closed در CI: `LEGACY_FAIL_CLOSED_SMOKE=PASS`
- Fetch، Notify و Publish در تست قرنطینه فراخوانی نمی‌شوند.

Activepieces Flow با شناسهٔ `NCvKO88RZXnkgF8irzz2N` در وضعیت DISABLED و Published است. آخرین اجرای مشاهده‌شده در 2026-11-10T04:30:01Z و قبل از تأیید وضعیت غیرفعال بوده است؛ اجرای جدیدی پس از آن در فهرست Runهای بررسی‌شده دیده نشد.

## 3. Sanity Check موتور بک‌تست

- [PR #62](https://github.com/hamedbenapart69-byte/Trade/pull/62)
- CI: [42894044246](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894044246)
- Pytest: [42894044286](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894044286)
- Walk-Forward: [42894044292](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894044292)

شش آزمون مصنوعی موفق:

| سناریو | نتیجهٔ واقعی | وضعیت |
|---|---|---|
| سیگنال در بسته‌شدن کندل و ورود در کندل بعد | ورود در Next-Bar Open | PASS |
| برخورد هم‌زمان SL و TP | فرض محافظه‌کارانهٔ SL-first | PASS |
| TP1 و TP2 | خروج 50/50 | PASS |
| برخورد SL در آخرین کندل | کندل پایانی بررسی می‌شود | PASS |
| Fee و Slippage | تفکیک و اعمال هزینه؛ Spread/Funding با UNAVAILABLE | PASS |
| یک معاملهٔ Stop در مدل ریسک 1٪ | MaxDD proxy برابر 1.08٪ | PASS |

### تفسیر بک‌تست تاریخی

نتیجهٔ Walk-Forward اجراشده:

- Trades: 53,043
- Win Rate: 42.54%
- Profit Factor: 0.9043
- Expectancy: -0.0578R
- MaxDD گزارش‌شده: 100%

تحلیل Artifact نشان داد Equity مدل مرکب به حدود `5.93e-16` برابر مقدار اولیه رسیده است؛ بنابراین MaxDD=100% با انباشت معاملات دارای امید ریاضی منفی سازگار است. این عدد **Trade-sequence proxy** است، نه MaxDD پرتفوی هم‌زمان و قابل‌معامله.

Gate همچنان BLOCKED است: Funding history ناقص، DSR/PBO و مقایسهٔ Baseline پیاده‌سازی/تأیید نشده‌اند. این نتیجه PASS استراتژی محسوب نمی‌شود.

## 4. Telegram

- [PR #63 — Mock و مقصد تست ایزوله](https://github.com/hamedbenapart69-byte/Trade/pull/63)
- CI: [42894263350](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894263350)
- Pytest: [42894260103](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42894260103)

پنج تست Mock موفق‌اند:
- فرمت وضعیت LEGACY_RESEARCH_ONLY و NO_QUALIFIED_SETUP
- رد وضعیت قرنطینهٔ نامعتبر
- ارسال فقط به `TELEGRAM_TEST_CHAT_ID`
- Skip در نبود Test Chat ID
- اعتبارسنجی قالب پیام عادی با شبکهٔ Mock

هیچ پیام واقعی در این مرحله ارسال نشده است. `TELEGRAM_TEST_CHAT_ID` و اجرای واقعی ارسال تأیید نشده‌اند. تابع تست به کانال اصلی fallback نمی‌کند.

- [PR #69](https://github.com/hamedbenapart69-byte/Trade/pull/69) یک Workflow دستی با `workflow_dispatch` اضافه کرده است تا پیام وضعیت فقط به `TELEGRAM_TEST_CHAT_ID` ارسال شود.
- این Workflow نه schedule دارد و نه push trigger؛ اگر Secret تست تنظیم نشده باشد، بدون ارسال پیام Skip می‌کند.
- CI و Pytest مربوط به PR #69 هر دو PASS شدند. اجرای زنده هنوز انجام نشده است؛ برای آن باید Secret مخصوص کانال تست تنظیم و Workflow به‌صورت دستی اجرا شود.

## 5. Cloudflare Pages

Cloudflare Pages Git integration برای چند PR Preview پاسخ موفق ثبت کرده است. نمونهٔ آخرین Preview:

- [Preview URL](https://bb602d46.trade-3vn.pages.dev)
- [Branch Preview](https://fix-p0-restore-stage1b-manua.trade-3vn.pages.dev)
- PR #67: [Restore manual-only workflow](https://github.com/hamedbenapart69-byte/Trade/pull/67)

وضعیت Preview در گزارش Cloudflare Bot: Deploy successful.

**Production deployment تأیید نشده است.** دسترسی مستقیم به پنل/API Cloudflare در این اجرا در اختیار نبود و URL اصلی Production از این مسیر قابل راستی‌آزمایی نشد.

## 6. بازگردانی Trigger موقت

- [PR #64](https://github.com/hamedbenapart69-byte/Trade/pull/64) و [PR #65](https://github.com/hamedbenapart69-byte/Trade/pull/65): Trigger موقت محدود به شاخهٔ P0.
- [PR #66](https://github.com/hamedbenapart69-byte/Trade/pull/66): PR اجرای موقت، پس از ثبت شواهد بسته شد و Merge نشد.
- [PR #67](https://github.com/hamedbenapart69-byte/Trade/pull/67): Trigger موقت حذف و workflow به `workflow_dispatch` بازگردانده شد.

وضعیت فعلی `.github/workflows/stage1b-scheduled.yml` در main: فقط workflow_dispatch؛ بدون push و بدون schedule.

یک اجرای تکراری دیگر، Run شمارهٔ 42894833208، در مرحلهٔ تست قرارداد Workflow متوقف شد؛ علت آن فعال‌بودن Trigger موقت در آن لحظه بود. مرحلهٔ نگهداری داده Skip شد و این Run داده‌ای را تغییر نداد. اجرای موفق و Commit داده همان Run شمارهٔ 42894604222 است.

## 7. تفکیک مسیرهای سیگنال

- موتور یک‌ساعته: قرنطینه و بدون اسکن/ارسال/انتشار.
- یک Workflow جداگانهٔ Stage 1b در شاخهٔ `stage1b-lrt15m` هنوز زمان‌بندی 4 ساعته دارد؛ کد آن صراحتاً فقط وضعیت WATCHLIST را می‌پذیرد و سیگنال BUY_NOW/SELL_NOW تولید نمی‌کند. این مسیر با موتور 1h و Workflow داده‌ای P0 متفاوت است.
- آخرین Artifact بررسی‌شدهٔ این مسیر: [Run 42862851234](https://github.com/hamedbenapart69-byte/Trade/actions/runs/42862851234). نتیجه: 27 نماد بررسی‌شده، 0 مورد WATCHLIST، `telegram_signals_sent=0`، `calibration=UNCALIBRATED` و سیاست `WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW`.
- در آن اجرا هیچ پیام سیگنال 15m به تلگرام ارسال نشد. این گزارش، تحویل زندهٔ پیام وضعیت قرنطینهٔ موتور 1h را اثبات نمی‌کند.
- اجرای موفق P0 داده‌ای، موتور LRT را اجرا نکرد.

## SLRP — P0

- **Objective:** تثبیت قرنطینهٔ 1h، یکتاسازی امن 15m، تولید Manifest واقعی، اعتبارسنجی بک‌تست و تفکیک Mock/Live.
- **Acceptance:** 27/27 نماد، 70,080 کندل برای هر نماد، 1,892,160 ردیف، 27 baseline، SHA-256 معتبر، Data Gate=PASS، اجرای موتور=FALSE.
- **v1:** Full-backfill تکراری و Snapshotهای تاریخ‌دار؛ شکست در مدیریت Push و ایجاد 54 فایل فعال.
- **Diagnosis:** D1 Data (Snapshotهای تکراری و فقدان Manifest)، D3 Implementation (Race در Push و نبود اجرای افزایشی).
- **v2:** Rolling baseline + tail، Deduplication، data-only، اعتبارسنجی OHLCV و Manifest؛ PASS برای معیارهای داده.
- **v3:** ساخته نشد؛ طبق R11 پس از PASS نسخهٔ v2 ساخته نمی‌شود.
- **Escalation:** تأیید Production Cloudflare و یک ارسال واقعی به Test Chat تلگرام؛ تا آن زمان Delivery کامل نیست.
- **Budget:** یک اجرای واقعی data-only موفق؛ اجرای تکراری بعدی قبل از نگهداری داده متوقف شد. هیچ سرویس پولی یا سفارش معاملاتی استفاده نشد.

## تصمیم مرحله‌ای

**P0 از نظر داده و قرنطینه PASS است؛ P0 کلی به‌دلیل دو شاهد Live/Production باقی‌مانده PARTIAL است.**

P1 آغاز نشده است. هیچ موتور 15m جدیدی در این مرحله اجرا یا فعال نشده و این بسته به‌معنای تأیید عملکرد معاملاتی نیست.


---

# الحاقیهٔ ممیزی P0 — 2026-11-11

## مبنای ممیزی

- مخزن: `hamedbenapart69-byte/Trade`
- شاخهٔ مبنا: `main`
- SHA مبنای ممیزی: `3941d8b77b3172f0b3fe3372ba96521d580e3432`
- شاخهٔ ثبت شواهد: `audit/p0-evidence-and-constitution-register-2026-11-11`
- این الحاقیه فقط شواهد خواندنی و نتایج API را ثبت می‌کند؛ هیچ Production deploy، انتشار Activepieces یا پیام تلگرام انجام نشده است.

## 1. Branch governance و کنترل دسترسی

### Ruleset موجود main

Ruleset فعال با نام `protect-main` و شناسهٔ `26948778` خوانده شد.

قوانین قابل مشاهده:
- جلوگیری از حذف شاخه
- جلوگیری از force-push
- Required status checks با contextهای `test`، `pytest` و `Push`
- الزام Linear history

نواقص:
- قانون Require Pull Request وجود ندارد.
- قانون Required Approvals وجود ندارد.
- `current_user_can_bypass=always` ثبت شده است.
- چند bypass actor از نوع RepositoryRole و Integration با حالت `always` ثبت شده‌اند.
- Ruleset فقط `refs/heads/main` را پوشش می‌دهد؛ `stage1b-lrt15m` در این Ruleset نیست.

### تلاش API

- GET فهرست Rulesets موفق بود و Ruleset بالا را برگرداند.
- GET جزئیات Ruleset موفق بود.
- GET شاخه‌های `main` و `stage1b-lrt15m` از Branch Protection API با HTTP 403 و پیام `Resource not accessible by integration` رد شد.
- اتصال GitHub در این محیط فقط ابزار خواندن Ruleset/Branch Protection را ارائه می‌کند؛ ابزار نوشتن/ایجاد/به‌روزرسانی Ruleset در فهرست عملیات متصل موجود نیست.
- هیچ تغییر محافظتی ثبت نشده است. این مورد **INFRASTRUCTURE_PERMISSION_BLOCKED** است، نه PASS.

## 2. بررسی PRها و CI

تمام Check Runهای موجود روی آخرین SHA مشاهده‌شده برای هر PR در زمان ممیزی `completed / success` بودند:

| PR | Head SHA | Checkها | وضعیت |
|---:|---|---|---|
| 73 | `ad799fd8ba1822a935d19179dca3db95aabd7975` | test ×2، Cloudflare Pages | PASS |
| 74 | `93822b25aa47f1c1448fbbf8bd7928a05c6fce6a` | test ×2، Cloudflare Pages | PASS |
| 76 | `66ddb4b710468982598258f63ae7d74ea38d2e98` | test ×2، Cloudflare Pages | PASS |
| 77 | `e4a3996b62fb67673fd79f26385a348937634e42` | test ×2، Cloudflare Pages | PASS |
| 78 | `991dd55c1170e24cded79a957cd79ea7d2c60920` | test ×2، Cloudflare Pages | PASS |
| 79 | `4142a47bc8587ba0682edbf515a6601588fadaaf` | test ×2، pytest، Cloudflare Pages | PASS |
| 80 | `27ff2b600b61509a24e1a5b3d20e482b30c445f4` | test ×2، Cloudflare Pages | PASS |

سبز بودن Checkها به‌تنهایی مجوز ادغام امنیتی نیست. همهٔ PRهای بالا در زمان بررسی باز بودند.

### یافتهٔ P0 در PR #73

PR #73 فقط مجوز Workflow را از `contents: write` به `contents: read` کاهش داده و نوشتن مستقیم state را به Artifact تبدیل کرده است. بااین‌حال، در همان Workflow کد `stage1b-lrt15m` همچنان با Environment زیر اجرا می‌شود:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

بنابراین کد شاخهٔ اسکن‌کننده هنوز به Secret تلگرام دسترسی دارد. اگر کد این شاخه تغییر مخرب داشته باشد، می‌تواند Secret را افشا کند. این PR به‌تنهایی جداسازی Secret را کامل نمی‌کند و **P0 PASS نیست**.

### یافته‌های PR #74

- Writer از `workflow_run` اجرا می‌شود و فقط artifact را به‌عنوان داده می‌خواند؛ فایل artifact اجرا نمی‌شود.
- شرط موفقیت و same-repository وجود دارد.
- اعتبارسنجی JSON شامل schema_version، ساختار دو دیکشنری، سقف تعداد، اندازهٔ ۲MB و timestamp است.
- شرط صریح `head_branch == stage1b-lrt15m` در Job دیده نشد؛ Trigger branch filter آن را محدود می‌کند، اما guard صریح داخل Job بهتر است.
- این PR همچنان وابسته به حفاظت واقعی شاخهٔ پیش‌فرض و جداسازی کامل Secret تلگرام از کد غیرقابل‌اعتماد است.

### یافته‌های PR #78

- Collector فقط `contents: read` دارد و checkout آن `persist-credentials: false` است.
- Writer جداگانه از `workflow_run` و شاخهٔ `main` اجرا می‌شود.
- Artifact از نظر symlink و سقف 100MB بررسی می‌شود.
- ابزار merge از `main` دریافت می‌شود و push با rebase و بدون force انجام می‌شود.
- Checkهای CI و Preview موفق‌اند. اجرای واقعی collector و persistence پس از ادغام هنوز اثبات نشده است.

### یافته‌های PR #79

- Collector فقط از `workflow_dispatch` روی main اجرا می‌شود و کد adapter شاخهٔ `stage1b-lrt15m` را با `persist-credentials: false` و مجوز read-only دریافت می‌کند.
- Writer فقط اجرای موفق همان مخزن و `head_branch == main` را می‌پذیرد.
- Validator از main اجرا می‌شود و مسیرها، symlink، اندازه، SHA-256 فایل‌ها، Aggregate Hash، 27 baseline، تعداد ردیف‌ها، OHLCV، ترتیب و یکتایی timestamp و provenance را بررسی می‌کند.
- این PR نسبت به Collector/Writer قبلی مرز اعتماد بهتری دارد؛ بااین‌حال اجرای واقعی Writer و persistence پس از ادغام هنوز انجام/اثبات نشده است.

### PRهای #76، #77 و #80

- #76 فقط هشدار تازگی گزارش داشبورد را اضافه می‌کند؛ Preview و CI موفق‌اند.
- #77 فایل گزارش روزانه را به Artifact اضافه می‌کند؛ اما Workflow مقصد همان کد شاخهٔ اسکن را اجرا می‌کند و Secret تلگرام همچنان در همان Job موجود است.
- #80 فقط diagnostics و traceability را افزایش می‌دهد؛ منطق تصمیم و آستانه‌ها را تغییر نمی‌دهد. بااین‌حال روی شاخهٔ اسکن‌کننده قرار می‌گیرد و تا رفع جداسازی Secret و Branch Governance نباید به‌عنوان پایان P0 تلقی شود.

**تصمیم ادغام:** هیچ‌یک از PRهای #73، #74، #76، #77، #78، #79 و #80 در این ممیزی ادغام نشدند. ادغام PRهای مقصد main می‌تواند Cloudflare Production را از طریق Git integration منتشر کند؛ Production deploy جداگانه مجاز نشده است. ادغام PRهای امنیتی نیز تا رفع نقص Secret و کنترل شاخه متوقف است.

## 3. Activepieces Dashboard Read API

Flow:
- نام: `Crypto Dashboard Read API — Read Only`
- Flow ID: `6oyZxg1YLVu0OpGzuDY8r`
- وضعیت: ENABLED و Published
- Trigger: `@activepieces/piece-webhook/catch_webhook`
- مقدار واقعی تنظیمات Trigger: `authType=none`

این Flow چندین جدول دادهٔ داخلی شامل تصمیم‌ها، سیگنال‌ها، تحلیل روزانه، نامزدها، DEX، خبرها، FRED و مشتقات را می‌خواند. پاسخ دارای CORS محدود به دامنهٔ Bool است؛ CORS احراز هویت محسوب نمی‌شود.

پیکربندی رسمی Trigger گزینه‌های None، Basic Auth، Header Auth و HMAC را ارائه می‌کند. بااین‌حال، تغییر امن مستلزم وجود Secret سمت سرور برای مصرف‌کننده است. قرار دادن Secret در JavaScript مرورگر قابل قبول نیست. اتصال فعلی ابزار Activepieces امکان ایجاد Secret امن در Cloudflare/Bool و تحویل آن به یک proxy سمت سرور را در اختیار این اجرا قرار نداد.

- هیچ تغییر Trigger یا Publish انجام نشد تا داشبورد موجود ناخواسته از کار نیفتد.
- آزمون رد درخواست بدون هدر و موفقیت با هدر معتبر اجرا نشده است.
- آسیب‌پذیری همچنان **OPEN / HIGH** است.

## 4. اسناد V9.0 و V9.1

دو فایل منبع در محیط اجرای این ممیزی قابل دسترسی محلی بودند:

| سند | صفحات | SHA-256 |
|---|---:|---|
| `rules 1.pdf` — Master Source V9.0 | 54 | `1dbdbcca127bd368b025a554b205970b7221fe22f68139908402c8d04f1db2f3` |
| `rules 1.1.pdf` — Source Addendum V9.1 | 55 | `862307dbc8cae72bfac03de24686f52c0a28d170afe26a69d4e27f22a21cf0a8` |

استخراج متن محلی انجام شد:
- V9.0: 2,913 خط، 4,954 واژه
- V9.1: 2,934 خط، 5,181 واژه

اما فایل‌های آپلودشده از مسیر Files به‌عنوان Project file قابل خواندن/Materialize نبودند و GitHub connector فقط متن inline می‌پذیرد؛ در این اجرا مسیر امن انتقال فایل محلی به GitHub API در اختیار نبود. بنابراین فایل‌های کامل Markdown در `docs/constitution/` ثبت نشدند و `CONSTITUTION_VERSION.md` نیز به‌عنوان نسخهٔ رسمی منبع ساخته نشد.

**Stage 0 = NOT PASS** تا زمان ثبت کامل هر دو Markdown و تأیید hash/commit آن‌ها. صرفاً داشتن PDF یا این Source Register، جایگزین تحویل اسناد Markdown نیست.

## 5. وضعیت P0

| محور | وضعیت |
|---|---|
| CI برای PRهای بررسی‌شده | PASS |
| Branch protection / ruleset کامل | BLOCKED / 403 و نبود write tool |
| جداسازی Telegram secrets از کد شاخهٔ اسکن | FAIL / OPEN |
| Activepieces Webhook authentication | OPEN / HIGH |
| ادغام PRهای امنیتی | HOLD |
| Cloudflare Production | NOT DEPLOYED |
| V9.0/V9.1 Markdown در repo | NOT COMMITTED |
| Stage 0 | NOT PASS |
| P0 کلی | **BLOCKED / NOT PASS** |

هیچ نتیجهٔ آزمایشی، Mock، Preview یا CI به‌عنوان شاهد اجرای زنده یا امنیت Production گزارش نشده است.


---

# الحاقیهٔ اجرای تدریجی P0 — 2026-11-11 (بازبینی پس از دستور ناظر)

این بخش، وضعیت قبلی «هیچ PR ادغام نشد» را با وضعیت واقعی پس از اجرای مجاز ناظر جایگزین می‌کند.

## 1. ادغام‌های انجام‌شده

| PR | مقصد | Head SHA بررسی‌شده | Merge commit | نتیجه |
|---:|---|---|---|---|
| #73 | `stage1b-lrt15m` | `ad799fd8ba1822a935d19179dca3db95aabd7975` | `2cb201aa4d01527250872687ac0c0643421ebc32` | MERGED |
| #74 | `main` | `93822b25aa47f1c1448fbbf8bd7928a05c6fce6a` | `e542a7e357b610be6f188fe51abb6fc72bb3470f` | MERGED |
| #78 | `main` | `991dd55c1170e24cded79a957cd79ea7d2c60920` | `ac01c995b59f659e4fb7eefd5f829742c63ee6a1` | MERGED |
| #80 | `stage1b-lrt15m` | `27ff2b600b61509a24e1a5b3d20e482b30c445f4` | `d309d2aff9aed4a9209af071407f1b9f1625b52b` | MERGED |
| #76 | `main` | `66ddb4b710468982598258f63ae7d74ea38d2e98` | `45c7721bc62642ad18e18385e0cbb5853c7d8afc` | MERGED |
| #77 | `main` | `e4a3996b62fb67673fd79f26385a348937634e42` | `225d5a5703c9c14fb802cc2a86f886feb546cb34` | MERGED |

تمام Checkهای موجود روی head SHAهای بالا در زمان ادغام `completed/success` بودند. ادغام‌ها با روش squash و کنترل Expected Head SHA انجام شدند.

### PR #79

- Head: `4142a47bc8587ba0682edbf515a6601588fadaaf`
- CI: 4/4 Check موفق (test×2، pytest، Cloudflare Pages)
- تلاش Merge از ابزار GitHub به‌علت کنترل ایمنی پلتفرم پیش از اجرای درخواست مسدود شد: `couldn't determine the safety status of the request`.
- وضعیت: **DEFERRED — TOOL SAFETY GATE**؛ هیچ merge commit ساخته نشد.
- هیچ مسیر جایگزین برای دورزدن این کنترل استفاده نشد.

## 2. Stage 0 — پذیرش ثبت منابع

طبق دستور صریح ناظر، `docs/constitution/SOURCE_REGISTER.md` همراه نام فایل، تعداد صفحات و SHA-256 به‌عنوان ثبت رسمی منابع V9 برای Stage 0 پذیرفته شد.

- Stage 0: **PASS — فقط در دامنهٔ Source Registration**.
- تبدیل کامل PDFها به `V9.0.md` و `V9.1.md`: **DEFERRED**.
- SHA-256 و تعداد صفحات در `docs/constitution/SOURCE_REGISTER.md` و `CONSTITUTION_VERSION.md` ثبت شده‌اند.
- این پذیرش اداری، ادعای وجود متن کامل Markdown یا برابری معنایی آن با PDF نیست.

## 3. Policy Guard

در زمان این الحاقیه، Workflow جایگزین هنوز ساخته/اجرا نشده است. وضعیت Branch Protection ادمین همچنان **DEFERRED** است؛ Policy Guard فقط کنترل کارآگاهی و هشداردهنده است و به‌تنهایی PR requirement، approval یا جلوگیری از push مستقیم را enforce نمی‌کند.

## 4. Telegram Secret Isolation

PR #73 سطح مجوز نوشتن را کاهش داد و state persistence را به Artifact منتقل کرد؛ اما diff آن، متغیرهای `TELEGRAM_TOKEN` و `TELEGRAM_CHAT_ID` را از Job اسکن حذف نکرد. Workflow فعلی `.github/workflows/signal_bot.yml` همچنان این دو Secret را به همان Jobی می‌دهد که کد `stage1b-lrt15m` را اجرا می‌کند.

بنابراین ادعای جداسازی Secret **PASS نیست**. اصلاح نیازمند انتقال ارسال به Workflow مورداعتماد روی main و حذف Secret از Job اسکن است. وضعیت فعلی: **OPEN / P0**.

## 5. Activepieces Webhook Auth

Flow `6oyZxg1YLVu0OpGzuDY8r` همچنان با `authType=none` فعال است. هیچ تغییر Header Auth، Secret امن سمت سرور، تست 401/200 یا Publish جدید انجام نشده است.

وضعیت: **DEFERRED — NO SAFE SECRET DELIVERY PATH**. قراردادن API key در فایل JavaScript مرورگر یا در مخزن عمومی راه‌حل امن نیست.

## 6. وضعیت نهایی اصلاح‌شده

| الزام | وضعیت | توضیح |
|---|---|---|
| PRهای #73 و #74 | PASS | ادغام شدند؛ State Writer جدا شد. |
| PR #78 | PASS | L2 collector و trusted persistence ادغام شدند. |
| PR #79 | DEFERRED | CI موفق؛ Merge توسط safety gate مسدود شد. |
| PR #80 | PASS | Diagnostics و traceability ادغام شدند. |
| PRهای #76 و #77 | PASS | Freshness warning و daily report artifact ادغام شدند. |
| Stage 0 | PASS | پذیرش رسمی Source Register با دستور ناظر؛ متن کامل Markdown معوق است. |
| Policy Guard | PENDING | هنوز ایجاد و اجرا نشده است. |
| Telegram Secret Isolation | OPEN / FAIL | Secret هنوز در Job اسکن وجود دارد. |
| Activepieces Header Auth | DEFERRED / OPEN | هنوز authType=none است. |
| Branch Protection ادمین | DEFERRED | API/connector write access ندارد. |
| Cloudflare Production Deploy | DEFERRED | توکن افشاشده استفاده نشده؛ Production تغییر نکرده است. |

**P0 کلی هنوز PASS نیست.** تعریف ناظر اجازه می‌دهد کنترل‌های واقعاً غیرقابل‌اجرا DEFERRED شوند، اما Telegram Secret Isolation و Webhook Auth هنوز صرفاً محدودیت ابزاری اثبات‌شده نیستند؛ آن‌ها کنترل‌های قابل‌اقدام اما اجرا‌نشده/فاقد مسیر امن هستند. تا اعمال و آزمون آن‌ها، بستن P0 ادعای زودهنگام خواهد بود.
