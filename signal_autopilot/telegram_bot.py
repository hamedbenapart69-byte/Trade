"""ارسال امن پیام ۹ بخشی Stage 1 به تلگرام."""
from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any

from telegram import Bot
from modules.lrt15m_engine import (
    PRODUCTION_MODE_THRESHOLD,
    RESEARCH_MODE_THRESHOLD,
)

LOG = logging.getLogger("trader_me.telegram")


def _normalize_chat_title(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


async def _verified_channel(bot: Bot, configured_chat_id: str):
    """Fail closed: کانال عمومی یا خصوصی باید با شناسه و عنوان دقیق تأیید شود و ربات مجوز ارسال داشته باشد."""
    chat_id = str(configured_chat_id or "").strip()
    if not chat_id.startswith("-100"):
        raise RuntimeError("TELEGRAM_TARGET_REJECTED_NOT_CHANNEL_ID")
    me = await bot.get_me()
    chat = await bot.get_chat(chat_id=chat_id)
    if str(chat.id) != chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID_RESOLUTION_MISMATCH")
    if str(chat.type) != "channel":
        raise RuntimeError(f"TELEGRAM_TARGET_REJECTED_CHAT_TYPE:{chat.type}")
    expected = os.getenv("TELEGRAM_EXPECTED_CHANNEL_TITLE", "").strip()
    if not expected:
        raise RuntimeError("TELEGRAM_EXPECTED_CHANNEL_TITLE_MISSING")
    if _normalize_chat_title(chat.title) != _normalize_chat_title(expected):
        raise RuntimeError(
            f"TELEGRAM_CHANNEL_TITLE_MISMATCH:expected={expected!r}:actual={chat.title!r}"
        )
    member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
    if str(member.status) != "administrator":
        raise RuntimeError(f"TELEGRAM_BOT_NOT_CHANNEL_ADMIN:{member.status}")
    if getattr(member, "can_post_messages", None) is not True:
        raise RuntimeError("TELEGRAM_BOT_ADMIN_CANNOT_POST_MESSAGES")
    return chat, me




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

    format_test = signal.get("format_test") is True
    format_test_prefix = "[FORMAT TEST - NOT A REAL SIGNAL]\n" if format_test else ""
    header = (
        format_test_prefix + "1. HEADER\n"
        f"⚠️ {symbol} | {direction} | {engine} | {timeframe}\n"
        "Calibration: UNCALIBRATED | Decision: WATCHLIST\n"
        "⚙️ STAGE_1_UNCALIBRATED | Veto: DATA/KUMO/LFS | WATCHLIST Tier A/B only"
    )
    chart_caption = (
        ("[FORMAT TEST - NOT A REAL SIGNAL] | " if format_test else "")
        + "2. CHART | کندل‌های بسته‌شدهٔ 15m + Kumo + Tenkan/Kijun + Entry/SL/TP"
    )

    sections = [
        (
            "3. تحلیل کوتاه فارسی",
            "\n".join([
                f"• امتیاز Confluence: {_value(signal.get('confluence_score'))}/100 | Tier {signal.get('tier', '—')}",
                "• Confluence Breakdown:",
                *[
                    f"  - {name}: {_value(value)} امتیاز"
                    for name, value in (signal.get("confluence_components") or {}).items()
                ],
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
                (f"• LFS Coverage: {_value(calibration.get('lfs_coverage_pct'))}%"
                 if calibration.get("lfs_coverage_pct") is not None else "• LFS Coverage: UNAVAILABLE"),
                f"• Data Window: {_value(calibration.get('coverage_per_symbol'))}",
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
                "⚠️ این آستانه‌ها برای جمع‌آوری داده در Stage 1 تنظیم شده‌اند. پس از 100+ سیگنال، بازبینی می‌شوند.",
            ]),
        ),
    ]
    body = "\n\n".join(f"{title}\n{text}" for title, text in sections)
    return header, chart_caption, body


async def _preflight(token: str, chat_id: str) -> tuple[bool, str]:
    try:
        async with Bot(token=token) as bot:
            chat, me = await _verified_channel(bot, chat_id)
        return True, (
            f"bot=@{me.username or me.id}; chat={chat.id}; type=channel; "
            f"title={chat.title!r}; username=@{chat.username or 'NO_PUBLIC_USERNAME'}; admin=administrator"
        )
    except Exception as exc:
        LOG.exception("Telegram channel preflight failed.")
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


async def _deliver(token: str, chat_id: str, signal: dict[str, Any], chart_path: Path) -> int:
    header, chart_caption, body = build_signal_messages(signal)
    async with Bot(token=token) as bot:
        chat, _ = await _verified_channel(bot, chat_id)
        target_chat_id = chat.id
        header_message = await bot.send_message(chat_id=target_chat_id, text=header, disable_web_page_preview=True)
        LOG.info("TELEGRAM_HEADER_MESSAGE_ID: %s | signal_id=%s", header_message.message_id, signal["signal_id"])
        try:
            with chart_path.open("rb") as image:
                chart_message = await bot.send_photo(
                    chat_id=target_chat_id,
                    photo=BytesIO(image.read()),
                    caption=chart_caption,
                )
            LOG.info("TELEGRAM_CHART_SENT: %s | message_id=%s", signal["signal_id"], chart_message.message_id)
        except Exception:
            LOG.exception("TELEGRAM_CHART_FAILED: %s", signal["signal_id"])
            fallback_message = await bot.send_message(
                chat_id=target_chat_id,
                text="[FORMAT TEST - NOT A REAL SIGNAL]\n2. CHART\n⚠️ تصویر نمودار ارسال نشد."
                if signal.get("format_test") is True else "2. CHART\n⚠️ تصویر نمودار ارسال نشد.",
            )
            LOG.info("TELEGRAM_CHART_FALLBACK_SENT: %s | message_id=%s", signal["signal_id"], fallback_message.message_id)
        await bot.send_message(chat_id=target_chat_id, text=body, disable_web_page_preview=True)
    if signal.get("format_test") is True:
        LOG.info("TELEGRAM_FORMAT_TEST_SENT: symbol=%s signal_id=%s message_id=%s", signal.get("symbol"), signal["signal_id"], header_message.message_id)
    else:
        LOG.info("TELEGRAM_SIGNAL_SENT: %s | sections=9 | status=WATCHLIST | message_id=%s", signal["signal_id"], header_message.message_id)
    return int(header_message.message_id)


def send_signal_to_telegram(
    signal_data: dict[str, Any],
    chart_path: str | Path,
    *,
    format_test: bool = False,
) -> int | None:
    """ارسال WATCHLIST؛ حالت format_test فقط برای آزمون صریح ARB و بدون سیگنال معاملاتی است."""
    if format_test:
        if os.getenv("TELEGRAM_FORMAT_TEST_ENABLED", "").strip().lower() != "true":
            LOG.error("TELEGRAM_FORMAT_TEST_DISABLED")
            return False
        if (
            signal_data.get("symbol") != "ARBUSDT"
            or signal_data.get("mode") != "RESEARCH"
            or signal_data.get("decision") != "RESEARCH_WATCHLIST"
            or signal_data.get("calibration_status") != "UNCALIBRATED"
            or not signal_data.get("signal_id")
        ):
            LOG.error("TELEGRAM_FORMAT_TEST_REJECTED_INVALID_RESEARCH_PAYLOAD")
            return False
        signal_data = {**signal_data, "format_test": True}
    else:
        if signal_data.get("status") != "WATCHLIST":
            LOG.warning("TELEGRAM_REJECTED_NON_WATCHLIST: %s", signal_data.get("symbol"))
            return False
        if signal_data.get("calibration_status") != "UNCALIBRATED":
            LOG.warning("TELEGRAM_REJECTED_CALIBRATION_STATE: %s", signal_data.get("symbol"))
            return False
        score = signal_data.get("confluence_score")
        if not isinstance(score, (int, float)) or score < PRODUCTION_MODE_THRESHOLD:
            LOG.info("TELEGRAM_SKIPPED_CONFLUENCE_BELOW_80: %s score=%s", signal_data.get("symbol"), score)
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


async def _deliver_test_message(token: str, chat_id: str) -> tuple[int, str | None]:
    """Send one explicit test message and return Telegram's real message_id."""
    async with Bot(token=token) as bot:
        chat, _ = await _verified_channel(bot, chat_id)
        message = await bot.send_message(
            chat_id=chat.id,
            text=(
                "[TEST MODE] Trader_me Telegram delivery verification\n"
                "Transport test only; not a trading signal.\n"
                "Stage 1B | LRT-15m"
            ),
            disable_web_page_preview=True,
        )
        username = getattr(chat, "username", None)
        link = f"https://t.me/{username}/{message.message_id}" if username else None
        LOG.info(
            "FORCE_TEST_SENT message_id=%s chat_id=%s message_link=%s",
            message.message_id, chat.id, link or "UNAVAILABLE_PRIVATE_CHAT",
        )
        return int(message.message_id), link


def send_test_message_to_telegram() -> tuple[int, str | None]:
    """Synchronous entry point used by force_test.py."""
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_TOKEN_OR_CHAT_ID_MISSING")
    return asyncio.run(_deliver_test_message(token, chat_id))

def build_research_message(signal: dict[str, Any]) -> str:
    """پیام پژوهشی؛ هرگز به‌عنوان سیگنال معاملاتی یا دستور ورود نمایش داده نمی‌شود."""
    if signal.get("mode") != "RESEARCH" or signal.get("decision") != "RESEARCH_WATCHLIST":
        raise ValueError("RESEARCH_MESSAGE_REQUIRES_RESEARCH_MODE")
    labels = {
        "bias_4h": "Bias4H",
        "bias_1h": "Bias1H",
        "sweep": "Sweep",
        "zone_reaction": "Zone",
        "tenkan_kijun_cross_10": "Cross",
    }
    points = signal.get("points") or {}
    component_lines = [
        f"  - {labels.get(name, name)}: {'✓' if int(value or 0) > 0 else '✗'} ({int(value or 0)})"
        for name, value in points.items()
    ]
    return "\n".join([
        "🔬 STAGE 1 RESEARCH — NOT A TRADING SIGNAL",
        "#RESEARCH_DATA_COLLECTION",
        "",
        "⚠️ این سیگنال برای جمع‌آوری داده است، نه معامله.",
        "⚠️ سیستم هنوز کالیبره نشده (UNCALIBRATED).",
        "⚠️ این خروجی ممکن است اشتباه باشد؛ هیچ اقدام معاملاتی بر اساس آن انجام ندهید.",
        "",
        f"📊 Symbol: {signal.get('symbol', 'UNAVAILABLE')}",
        f"🎯 Direction: {signal.get('direction', 'UNAVAILABLE')}",
        f"📈 Confluence: {signal.get('raw_score', '—')}/100 | Tier: {signal.get('tier_score', '—')} | RESEARCH_WATCHLIST",
        "🔍 Components:",
        *component_lines,
        "",
        "📋 هدف: جمع‌آوری داده برای ارزیابی و کالیبراسیون آتی",
        "📅 حداقل 100 مشاهدهٔ یکتا؛ سپس برچسب‌گذاری نتایج و ارزیابی OOS لازم است.",
        f"🆔 Research ID: {signal.get('signal_id', 'UNAVAILABLE')}",
        f"🕒 UTC: {signal.get('created_at_utc', 'UNAVAILABLE')}",
        "⛔ NOT A TRADING SIGNAL | NO ORDER EXECUTION",
    ])


async def _deliver_research(token: str, chat_id: str, signal: dict[str, Any]) -> int:
    message_text = build_research_message(signal)
    async with Bot(token=token) as bot:
        chat, _ = await _verified_channel(bot, chat_id)
        message = await bot.send_message(
            chat_id=chat.id,
            text=message_text,
            disable_web_page_preview=True,
        )
    LOG.info(
        "TELEGRAM_RESEARCH_SENT symbol=%s signal_id=%s message_id=%s",
        signal.get("symbol"), signal.get("signal_id"), message.message_id,
    )
    return int(message.message_id)


def send_research_signal_to_telegram(signal_data: dict[str, Any]) -> int | None:
    """ارسال فقط دادهٔ پژوهشی ۶۰ تا ۷۹؛ هرگز از مسیر WATCHLIST تولیدی استفاده نمی‌کند."""
    if (
        signal_data.get("mode") != "RESEARCH"
        or signal_data.get("decision") != "RESEARCH_WATCHLIST"
        or signal_data.get("stage_label") != "STAGE_1_RESEARCH_UNCALIBRATED"
        or signal_data.get("calibration_status") != "UNCALIBRATED"
    ):
        LOG.error("TELEGRAM_RESEARCH_REJECTED_INVALID_LABEL: %s", signal_data.get("symbol"))
        return False
    score = signal_data.get("tier_score")
    if not isinstance(score, (int, float)) or not RESEARCH_MODE_THRESHOLD <= score < PRODUCTION_MODE_THRESHOLD:
        LOG.error("TELEGRAM_RESEARCH_REJECTED_SCORE: %s score=%s", signal_data.get("symbol"), score)
        return False
    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        LOG.warning("TELEGRAM_RESEARCH_SKIPPED_NOT_CONFIGURED")
        return False
    try:
        return asyncio.run(_deliver_research(token, chat_id, signal_data))
    except Exception:
        LOG.exception("TELEGRAM_RESEARCH_DELIVERY_FAILED: %s", signal_data.get("signal_id"))
        return False
