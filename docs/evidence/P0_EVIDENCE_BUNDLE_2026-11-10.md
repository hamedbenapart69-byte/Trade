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
