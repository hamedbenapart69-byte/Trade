# دفتر کشف و ارزیابی ابزارهای داده و تحلیل

## اصل اجرایی
این دفتر برای ابزارهایی است که سیستم از محیط سمت سرور استفاده می‌کند. کاربر فقط تلگرام را می‌بیند. محدودیت ایران، فیلترشدن برای کاربر یا نیاز او به حساب/تأییدیه، معیار حذف ابزار نیست. فقط دسترسی واقعی runner، هزینه، مجوز، کیفیت و ارزش افزوده اهمیت دارد.

## وضعیت فعلی
تمام مواردی که در کاتالوگ با `DISCOVERED_NOT_RUNTIME_TESTED` ثبت شده‌اند، فقط از روی مستندات رسمی/اولیه کشف شده‌اند؛ هنوز ادعای اتصال موفق از GitHub Actions نداریم. هیچ provider صرفاً با دیدن صفحهٔ مستندات وارد مسیر تولید نمی‌شود.

## دسته‌های پوشش
| دسته | گزینه‌های کشف‌شده | مرز داده |
|---|---|---|
| Perpetual OHLCV / بازار | OKX، Bybit، Binance USD-M، Bitget، KuCoin Futures | قرارداد و نوع بازار باید دقیقاً linear USDT perpetual باشد |
| مشتقات | APIهای عمومی صرافی‌ها | Funding و OI تاریخچهٔ متفاوت و محدود دارند؛ عمق هر endpoint جدا ثبت شود |
| Order Flow | معاملات عمومی و AggTrades صرافی‌ها | CVD از معاملات محاسبه می‌شود؛ دادهٔ محاسبه‌شده با Order Book تاریخی یکی نیست |
| Order Book | snapshotهای عمومی صرافی‌ها | snapshot لحظه‌ای، تاریخچهٔ L2 تولید نمی‌کند |
| On-chain | DefiLlama، Coin Metrics Community، CoinGecko Demo | هر endpoint فقط در محدودهٔ رایگان واقعی و مجوز خودش |
| News / Narrative | RSS رسمی ناشران؛ CryptoPanic فقط پس از بررسی هزینه/مجوز | خبر تکراری و syndicated deduplicate شود |
| Sentiment | Alternative.me Fear & Greed | شاخص کلان/کند؛ محرک مستقل ورود نیست |
| Charting | Lightweight Charts | فقط رندر دادهٔ خود سیستم؛ نه منبع قیمت |
| Quant / Backtest | Python stack و ارزیابی Freqtrade به‌عنوان مرجع | هیچ مسیر سفارش زنده یا حساب معاملاتی فعال نشود |
| Monitoring | GitHub Actions، artifactها، provider-health و پیام تلگرام | freshness، خطا، پوشش و provenance ثبت شوند |

## نکات مهم کشف‌شده از مستندات
1. OKX اعلام می‌کند endpointهای Market Data بدون احراز هویت‌اند؛ مستندات Funding History تا سه ماه را نشان می‌دهد. این عمق برای دو سال دادهٔ Funding کافی نیست.
2. Bybit برای دستهٔ Linear، کندل، معاملات عمومی، Order Book و endpointهای مشتقات مستند دارد؛ محدودیت هر endpoint باید جداگانه اندازه‌گیری شود.
3. Binance USD-M مستندات Kline، AggTrades، Funding و OI دارد. OI History فقط دادهٔ یک ماه اخیر را ارائه می‌کند؛ endpoint قدیمی Historical Trades به API key نیاز دارد. بنابراین آن endpoint را keyless فرض نکن.
4. KuCoin Futures در Kline دسترسی Public دارد، اما هر درخواست حداکثر ۵۰۰ رکورد می‌دهد و بازه‌های بدون معامله ممکن است کندل نداشته باشند.
5. CoinGecko Demo رایگان است، اما حساب و API key می‌خواهد و سهمیهٔ آن ۱۰۰ درخواست در دقیقه و ۱۰٬۰۰۰ درخواست ماهانه است. فقط برای مرجع بازار/متادیتا/DEX در حد endpoint مجاز؛ نه جایگزین دادهٔ Perpetual.
6. DefiLlama API رایگانِ بدون کلید دارد، اما endpointهای رایگان `/pools` و `/chart/{pool}` از ۱۳ نوامبر ۲۰۲۶ متوقف شده‌اند؛ مسیرهای Pro/API و MCP پولی از معماری صفرهزینه حذف‌اند.
7. Coin Metrics Community بدون API key و با مجوز Community در دسترس است، اما پوشش/تاریخچه محدود و نرخ آن ۱۰ درخواست در ۶ ثانیه است؛ شرایط استفاده باید برای کاربرد نهایی بررسی شود.
8. Alternative.me شاخص Fear & Greed را از API عمومی می‌دهد و attribution را الزامی می‌کند.
9. TradingView برای widgetها API داده یا export نمی‌دهد و سیاست استفادهٔ داده، پردازش ماشینی غیرنمایشی را محدود می‌کند؛ پس از موتور سیگنال حذف و فقط در صورت نیاز نمایش‌محور بررسی می‌شود.
10. CryptoPanic برای API به auth token نیاز دارد؛ تا وقتی هزینه و مجوز رایگان پایدار اثبات نشده، منبع تولید نیست.
11. CoinBoss API در مستندات فعلی REST/WebSocket عمومی بدون کلید و رایگان در دورهٔ فعلی با سقف اعلامی ۱۲۰۰ درخواست در دقیقه معرفی شده و مجموعهٔ وسیعی از OI، Funding، Liquidations، Long/Short، عمق دفتر سفارش و دادهٔ تجمیعی را ارائه می‌کند. اما صفحهٔ قیمت، tierهای پولیِ برنامه‌ریزی‌شده و نامشخص‌بودن تداوم دسترسی رایگان را اعلام می‌کند؛ بنابراین فقط نامزد ثانویهٔ cross-check است، نه وابستگی اصلی. شرایط استفاده باید پیش از تولید بررسی شود و اعداد تجمیعی آن با منبع مستقیم، قرارداد، روش محاسبه و timestamp تطبیق داده شوند.

## پذیرش provider
هر provider باید از این مراحل عبور کند:
1. بررسی مستندات رسمی و endpoint دقیق؛
2. تأیید هزینهٔ صفر واقعی، بدون trial و کارت؛
3. بررسی مجوز دریافت، ذخیره، پردازش و بازنشر؛
4. probe واقعی از runner و ثبت HTTP status/latency؛
5. اعتبارسنجی schema، contract type، symbol mapping، timestamp و freshness؛
6. اندازه‌گیری coverage و missingness؛
7. مقایسه با منبع مستقل و بررسی اختلاف؛
8. آزمون fallback در 403/429/451/5xx/timeout/malformed response؛
9. برای هر feature سیگنال‌ساز، آزمون ablation و ارزش افزودهٔ OOS.

## وضعیت فعلی اجرا
- کاتالوگ نامزدها ساخته شده است.
- این سند اثبات runtime reachability نیست.
- ابزارهای نیازمند کلید رایگان فقط در صورت وجود secret سمت سرور و بدون اقدام اتصال از طرف کاربر قابل فعال‌سازی‌اند.
- اگر یک منبع از runner مسدود باشد، فقط همان منبع کنار گذاشته می‌شود؛ هیچ قاعده‌ای برای حذف به‌خاطر محل زندگی کاربر وجود ندارد.
- ابزارهایی که دادهٔ تکراری، ناسازگار، کم‌کیفیت یا فاقد بهبود OOS دارند به امتیاز سیگنال اضافه نمی‌شوند.

## منابع رسمی/اولیه
- OKX API: https://www.okx.com/docs-v5/en/
- Bybit V5 Kline: https://bybit-exchange.github.io/docs/v5/market/kline
- Bybit V5 Market API: https://bybit-exchange.github.io/docs/api-explorer/v5/market/market
- Binance USD-M Market Data: https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Bitget Market Data: https://www.bitget.com/docs/catalog/market/market-data
- KuCoin Futures Kline: https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines
- CoinGecko Pricing: https://www.coingecko.com/en/api/pricing
- DefiLlama API: https://api-docs.defillama.com/
- Coin Metrics Community: https://docs.coinmetrics.io/packages/coin-metrics-community-data
- CoinBoss API / Authentication / Pricing: https://www.coinboss.com/api-docs | https://www.coinboss.com/api-docs/authentication | https://www.coinboss.com/pricing
- Alternative.me FNG: https://alternative.me/crypto/fear-and-greed-index/
- TradingView Data FAQ: https://www.tradingview.com/widget-docs/faq/data/
- TradingView Lightweight Charts: https://www.tradingview.com/free-charting-libraries/
- Freqtrade Backtesting: https://docs.freqtrade.io/en/latest/backtesting/

**تذکر:** این فهرست، دفتر زندهٔ ابزارهای کشف‌شده است، نه ادعای بررسی تک‌تک ابزارهای جهان. هر وضعیت باید با شواهد تازه به‌روزرسانی شود.
