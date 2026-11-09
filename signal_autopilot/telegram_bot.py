"""ارسال امن پیام ۹ بخشی Stage 1 به تلگرام."""
from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from telegram import Bot

LOG = logging.getLogger("trader_me.telegram")


def _value(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def build_signal_messages(signal: dict[str, Any]) -> tuple[str, str, str]:
    symbol = signal["symbol"]
    direction = signal["direction"]
    engine = signal.get("engine", "LRT-15m")
    timeframe = signal.get("timeframe", "15m")
    signal_id = signal["signal_id"]
    ichimoku = signal.get("ichimoku", {})
    levels = signal.get("levels", {})
    calibration = signal.get("calibration", {})
    costs = signal.get("costs", {})
    flags = signal.get("risk_flags", [])

    header = (
        "1. HEADER\n"
        f"⚠️ {symbol} | {direction} | {engine} | {timeframe}\n"
        "Calibration: UNCALIBRATED | Decision: WATCHLIST"
    )
    chart_caption = "2. CHART | کندل‌های بسته‌شدهٔ 15m + Kumo + Tenkan/Kijun + Entry/SL/TP"

    sections = [
        (
            "3. تحلیل کوتاه فارسی",
            "\n".join([
                f"• امتیاز Confluence: {_value(signal.get('confluence_score'))}/100",
                f"• وضعیت ایچیموکو: {ichimoku.get('bias', 'UNAVAILABLE')}",
                f"• فرضیه: {signal.get('hypothesis', 'UNAVAILABLE')}",
                "• خروجی صرفاً WATCHLIST است؛ هیچ سفارش یا توصیهٔ ورود صادر نشده است.",
            ]),
        ),
        (
            "4. ICHIMOKU STATUS",
            "\n".join([
                f"• قیمت نسبت به Kumo: {ichimoku.get('price_vs_kumo', 'UNAVAILABLE')}",
                f"• Tenkan/Kijun: {ichimoku.get('tenkan_kijun', 'UNAVAILABLE')}",
                f"• Chikou: {ichimoku.get('chikou', 'UNAVAILABLE')}",
                f"• Bias: {ichimoku.get('bias', 'UNAVAILABLE')}",
            ]),
        ),
        (
            "5. مشخصات سطوح مرجع (غیرقابل اجرا)",
            "\n".join([
                f"• Entry: {_value(levels.get('entry'))}",
                f"• SL (ATR/ساختار): {_value(levels.get('stop_loss'))}",
                f"• TP1: {_value(levels.get('tp1'))}",
                f"• TP2: {_value(levels.get('tp2'))}",
                f"• TP3: {_value(levels.get('tp3'))}",
                f"• RR مرجع: {_value(levels.get('rr'))}",
                "تمام سطوح صرفاً مرجع تحلیلی‌اند و بک‌تست/تأیید نشده‌اند.",
            ]),
        ),
        (
            "6. Calibration & Coverage",
            "\n".join([
                "• وضعیت: UNCALIBRATED",
                "• برچسب تصمیم: WATCHLIST",
                f"• LFS: {calibration.get('lfs_status', 'UNAVAILABLE')}",
                f"• LFS Source: {calibration.get('lfs_source', 'UNAVAILABLE')}",
                f"• Coverage: {_value(calibration.get('coverage_per_symbol'))}",
            ]),
        ),
        (
            "7. Cost & EV",
            "\n".join([
                f"• Fee: {_value(costs.get('fee_pct'))}",
                f"• Slippage: {_value(costs.get('slippage_pct'))}",
                f"• Spread: {_value(costs.get('spread_pct'))}",
                "• EV: NOT_CALCULATED (UNCALIBRATED)",
            ]),
        ),
        (
            "8. Risk Flags",
            "\n".join(f"⚠️ {item}" for item in flags) if flags else "• UNAVAILABLE",
        ),
        (
            "9. Footer",
            "\n".join([
                "⚠️ این پیام توصیهٔ سرمایه‌گذاری نیست.",
                f"• زمان UTC: {signal.get('created_at_utc', 'UNAVAILABLE')}",
                f"• Signal ID: {signal_id}",
                "• Stage 1 | Manual trade only | No order execution",
            ]),
        ),
    ]
    body = "\n\n".join(f"{title}\n{text}" for title, text in sections)
    return header, chart_caption, body


async def _preflight(token: str, chat_id: str) -> tuple[bool, str]:
    try:
        async with Bot(token=token) as bot:
            me = await bot.get_me()
            chat = await bot.get_chat(chat_id=chat_id)
        return True, f"bot=@{me.username or me.id}; chat={chat.id}"
    except Exception as exc:
        LOG.exception("Telegram preflight failed.")
        return False, f"{type(exc).__name__}: {str(exc)[:180]}"


def verify_telegram_connection() -> bool:
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOG.warning("TELEGRAM_PREFLIGHT_SKIPPED: missing repository secrets.")
        return False
    ok, detail = asyncio.run(_preflight(token, chat_id))
    if ok:
        LOG.info("TELEGRAM_PREFLIGHT_OK: %s", detail)
    else:
        LOG.error("TELEGRAM_PREFLIGHT_FAILED: %s", detail)
    return ok


async def _deliver(token: str, chat_id: str, signal: dict[str, Any], chart_path: Path) -> bool:
    header, chart_caption, body = build_signal_messages(signal)
    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat_id, text=header, disable_web_page_preview=True)
        try:
            with chart_path.open("rb") as image:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=BytesIO(image.read()),
                    caption=chart_caption,
                )
            LOG.info("TELEGRAM_CHART_SENT: %s", signal["signal_id"])
        except Exception:
            LOG.exception("TELEGRAM_CHART_FAILED: %s", signal["signal_id"])
            await bot.send_message(
                chat_id=chat_id,
                text="2. CHART\n⚠️ تصویر نمودار ارسال نشد.",
            )
        await bot.send_message(chat_id=chat_id, text=body, disable_web_page_preview=True)
    LOG.info("TELEGRAM_SIGNAL_SENT: %s | sections=9 | status=WATCHLIST", signal["signal_id"])
    return True


def send_signal_to_telegram(
    signal_data: dict[str, Any],
    chart_path: str | Path,
) -> bool:
    """ارسال فقط WATCHLIST با Confluence بالاتر از ۸۰؛ بدون اجرای سفارش."""
    if signal_data.get("status") != "WATCHLIST":
        LOG.warning("TELEGRAM_REJECTED_NON_WATCHLIST: %s", signal_data.get("symbol"))
        return False
    if signal_data.get("calibration_status") != "UNCALIBRATED":
        LOG.warning("TELEGRAM_REJECTED_CALIBRATION_STATE: %s", signal_data.get("symbol"))
        return False
    score = signal_data.get("confluence_score")
    if not isinstance(score, (int, float)) or score <= 80:
        LOG.info("TELEGRAM_SKIPPED_CONFLUENCE: %s score=%s", signal_data.get("symbol"), score)
        return False

    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOG.warning("TELEGRAM_SKIPPED_NOT_CONFIGURED")
        return False

    path = Path(chart_path)
    if not path.is_file():
        LOG.error("TELEGRAM_SKIPPED_CHART_MISSING: %s", path)
        return False

    try:
        return asyncio.run(_deliver(token, chat_id, signal_data, path))
    except Exception:
        LOG.exception("TELEGRAM_DELIVERY_FAILED: %s", signal_data.get("signal_id"))
        return False
