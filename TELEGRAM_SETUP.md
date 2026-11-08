# راه‌اندازی اعلان تلگرام

1. در تلگرام @BotFather را باز کن و /newbot بفرست.
2. نام نمایشی و username یکتا که به bot ختم شود انتخاب کن.
3. Token را خصوصی نگه دار و در چت یا مخزن قرار نده.
4. برای Chat ID از ابزار معتبر دریافت شناسه استفاده کن و گفت‌وگو با ربات ساخته‌شده را با Start آغاز کن.
5. در مخزن GitHub به Settings → Secrets and variables → Actions → New repository secret برو و دو Secret بساز:
   - TELEGRAM_TOKEN
   - TELEGRAM_CHAT_ID

## تست
در Actions گردش‌کار Futures Signals Pipeline را باز کن، شاخه stage-1-data-layer-v1 را انتخاب کن، test_telegram=true را تنظیم و اجرا کن. پیام «تست اتصال ربات سیگنال» باید دریافت شود.

اگر یکی از Secretها موجود نباشد، notifier با وضعیت SKIPPED_NOT_CONFIGURED بدون crash رد می‌شود. خطای واقعی API در log ثبت می‌شود. موتور فعلی Tier A/BUY_NOW/SELL_NOW تولید نمی‌کند؛ اعلان تست مستقل از اعلان سیگنال است.
