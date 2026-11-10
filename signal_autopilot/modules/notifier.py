"""Telegram delivery for actionable futures signals and daily no-signal status."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

import smtplib
import ssl
from io import BytesIO
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from telegram import Bot

from modules.chart_renderer import render_signal_chart

LOG = logging.getLogger("signal_autopilot.telegram")


def _credentials() -> tuple[str, str]:
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id


async def _send(token: str, chat_id: str, messages: list[str]) -> list[int]:
    """ارسال پیام و بازگرداندن شناسه‌های واقعی برگشتی از Telegram API."""
    message_ids: list[int] = []
    async with Bot(token=token) as bot:
        for message in messages:
            sent_message = await bot.send_message(
                chat_id=chat_id, text=message, disable_web_page_preview=True
            )
            message_id = getattr(sent_message, "message_id", None)
            if isinstance(message_id, int) and message_id > 0:
                message_ids.append(message_id)
    return message_ids


async def _send_signal_photos(token: str, chat_id: str, signals: list[tuple[dict, str]]) -> tuple[int, int]:
    """هر سیگنال را با چارت همان نماد و کپشن تحلیلی ارسال می‌کند."""
    sent = 0
    chart_failures = 0
    async with Bot(token=token) as bot:
        for signal, caption in signals:
            try:
                chart = render_signal_chart(signal)
                sent_message = await bot.send_photo(
                    chat_id=chat_id, photo=BytesIO(chart), caption=caption[:1024]
                )
                message_id = getattr(sent_message, "message_id", None)
                if isinstance(message_id, int) and message_id > 0:
                    signal["message_id_current"] = message_id
            except Exception:
                chart_failures += 1
                LOG.exception("Chart image delivery failed for %s; sending text fallback.", signal.get("symbol"))
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=(caption + "\n\n⚠️ تصویر چارت ساخته/ارسال نشد؛ سطوح و تحلیل بالا معتبرِ متنی هستند.")[:4096],
                    disable_web_page_preview=True,
                )
                message_id = getattr(sent_message, "message_id", None)
                if isinstance(message_id, int) and message_id > 0:
                    signal["message_id_current"] = message_id
            sent += 1
    return sent, chart_failures


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def _format_signal(signal: dict, payload: dict) -> str:
    targets = signal.get("take_profit") or []
    tp1 = targets[0] if len(targets) > 0 else "—"
    tp2 = targets[1] if len(targets) > 1 else "—"
    dashboard = (os.getenv("DASHBOARD_URL") or "https://trade-3vn.pages.dev/").strip()
    return "\n".join([
        "🔔 سیگنال فیوچرز",
        f"نماد: {signal.get('symbol', '—')}",
        f"جهت: {'خرید' if signal.get('status') == 'BUY_NOW' else 'فروش'}",
        f"ورود: {signal.get('entry') if signal.get('entry') is not None else '—'}",
        f"کیفیت زمان قیمت ورود: {signal.get('entry_price_quality', 'UNKNOWN')}",
        f"حد ضرر: {signal.get('stop_loss') if signal.get('stop_loss') is not None else '—'}",
        f"تارگت ۱: {tp1}",
        f"تارگت ۲: {tp2}",
        f"نوع تحلیل: EMA Trend Continuation | تایم‌فریم: {signal.get('timeframe', '1H')}",
        f"دلیل: {signal.get('reason', '—')}",
        f"فرضیه: {signal.get('hypothesis', '—')}",
        f"ابطال تحلیل: {signal.get('falsification', '—')}",
        "اطمینان: هنوز کالیبراسیون آماری انجام نشده است",
        f"زمان UTC: {payload.get('generated_at_utc', '—')}",
        dashboard,
    ])


def _initialize_delivery_metadata(payload: dict) -> None:
    """هر snapshot فقط شناسه‌های ارسال همین اجرای pipeline را نگه می‌دارد."""
    payload["message_id_current"] = None
    payload["message_id_audience"] = None
    payload["published_at"] = None
    for signal in payload.get("signals", []):
        signal["message_id_current"] = None
        signal["message_id_audience"] = None
        signal["published_at"] = None


def _finalize_delivery_metadata(payload: dict, daily_message_id: int | None = None) -> None:
    """ثبت شناسه‌های برگشتی واقعی؛ کانال دوم تا زمان پیکربندی صریحاً null می‌ماند."""
    current_ids = {
        str(signal.get("symbol")): signal["message_id_current"]
        for signal in payload.get("signals", [])
        if isinstance(signal.get("message_id_current"), int)
        and signal["message_id_current"] > 0
    }
    if isinstance(daily_message_id, int) and daily_message_id > 0:
        current_ids["_daily_status"] = daily_message_id
    payload["message_id_current"] = current_ids or None
    payload["message_id_audience"] = None
    published_at = datetime.now(timezone.utc).isoformat() if current_ids else None
    payload["published_at"] = published_at
    for signal in payload.get("signals", []):
        if signal.get("message_id_current") is not None:
            signal["published_at"] = published_at
        LOG_ID = signal.get("message_id_current")
        if isinstance(LOG_ID, int) and LOG_ID > 0:
            LOG.info("TELEGRAM_SIGNAL_MESSAGE_ID symbol=%s message_id=%s", signal.get("symbol"), LOG_ID)
    if isinstance(daily_message_id, int) and daily_message_id > 0:
        LOG.info("TELEGRAM_DAILY_STATUS_MESSAGE_ID message_id=%s", daily_message_id)


def notify_tier_a(payload: dict) -> dict:
    """نام قدیمی تابع حفظ شده؛ هر سیگنال با تصویر چارت و تحلیل ارسال می‌شود."""
    _initialize_delivery_metadata(payload)
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        return {"status": "SKIPPED_CI_VALIDATION", "sent": 0}
    token, chat_id = _credentials()
    if not token or not chat_id:
        LOG.info("Telegram skipped: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}

    candidates = [
        signal for signal in payload.get("signals", [])
        if signal.get("status") in ("BUY_NOW", "SELL_NOW")
        and signal.get("entry") is not None
        and signal.get("stop_loss") is not None
        and len(signal.get("take_profit") or []) >= 2
    ]
    state_path = Path(os.getenv(
        "TELEGRAM_STATE_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "telegram_sent.json"),
    ))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sent_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(sent_state, dict):
            sent_state = {}
    except (OSError, json.JSONDecodeError):
        sent_state = {}

    now = datetime.now(timezone.utc)

    # نسخهٔ ۲: شناسهٔ سیگنال مستقل از زمان تولید است و فقط با تغییر سطوح،
    # ارسال مجدد مجاز می‌شود. وضعیت قدیمی برای مهاجرت یک‌باره نگه داشته می‌شود.
    if sent_state.get("__schema_version__") == 2:
        signal_state = sent_state.get("signals", {})
        daily_state = sent_state.get("daily", {})
        legacy_state = sent_state.get("legacy", {})
        if not isinstance(signal_state, dict):
            signal_state = {}
        if not isinstance(daily_state, dict):
            daily_state = {}
        if not isinstance(legacy_state, dict):
            legacy_state = {}
    else:
        signal_state = {}
        daily_state = {}
        legacy_state = sent_state

    legacy_state = {
        key: value for key, value in legacy_state.items()
        if isinstance(key, str) and _parse_time(value) is not None
        and now - _parse_time(value) < timedelta(hours=48)
    }

    # حفظ dedup روزانهٔ نسخهٔ قبلی برای جلوگیری از ارسال مجدد در زمان مهاجرت.
    if legacy_state:
        for legacy_key, legacy_value in legacy_state.items():
            if isinstance(legacy_key, str) and legacy_key.startswith("DAILY_"):
                daily_state.setdefault(legacy_key, legacy_value)

    def _stable_identity(signal: dict) -> str:
        direction = str(
            signal.get("direction") or signal.get("side")
            or ("LONG" if signal.get("status") == "BUY_NOW" else "SHORT")
        ).upper()
        signal_id = str(
            signal.get("signal_id")
            or f"{signal.get('analysis_type') or signal.get('strategy_id') or 'UNSPECIFIED'}:"
               f"{signal.get('timeframe') or 'UNSPECIFIED'}"
        )
        identity = {
            "signal_id": signal_id,
            "symbol": str(signal.get("symbol") or "").upper(),
            "direction": direction,
        }
        raw = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _canonical_price(value):
        if value is None:
            return None
        try:
            return format(Decimal(str(value)).normalize(), "f")
        except (InvalidOperation, TypeError, ValueError):
            return str(value)

    def _levels_fingerprint(signal: dict) -> str:
        levels = {
            "entry": _canonical_price(signal.get("entry")),
            "stop_loss": _canonical_price(signal.get("stop_loss")),
            "take_profit": [_canonical_price(value) for value in (signal.get("take_profit") or [])],
        }
        raw = json.dumps(levels, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    pending: list[tuple[str, str, dict, str]] = []
    for signal in candidates:
        identity = _stable_identity(signal)
        fingerprint = _levels_fingerprint(signal)
        previous = signal_state.get(identity)

        # Legacy migration: اگر نسخهٔ قبلی همین سیگنال را ثبت کرده، در اولین
        # اجرای نسخهٔ جدید از ارسال تکراری جلوگیری می‌کنیم؛ fingerprint قدیمی
        # در state موجود نبود، پس سطوح تاریخی قابل بازیابی نیستند.
        if previous is None and legacy_state:
            legacy_prefix = (
                str(signal.get("symbol") or ""),
                str(signal.get("status") or ""),
                str(signal.get("analysis_type") or ""),
                str(signal.get("timeframe") or ""),
            )
            legacy_match = any(
                tuple(key.split("|")[:4]) == legacy_prefix
                and _parse_time(legacy_state.get(key)) is not None
                and now - _parse_time(legacy_state.get(key)) < timedelta(hours=48)
                for key in legacy_state
                if isinstance(key, str) and not key.startswith("DAILY_")
            )
            if legacy_match:
                signal_state[identity] = {"fingerprint": fingerprint, "sent_at": now.isoformat(),
                                           "migration": "legacy_suppressed"}
                continue

        previous_fingerprint = previous.get("fingerprint") if isinstance(previous, dict) else previous
        if previous_fingerprint != fingerprint:
            pending.append((identity, fingerprint, signal, _format_signal(signal, payload)))

    sent_state = {
        "__schema_version__": 2, "signals": signal_state,
        "daily": daily_state, "legacy": legacy_state,
    }

    if not candidates:
        generated = payload.get("generated_at_utc") or now.isoformat()
        day = str(generated)[:10]
        if payload.get("pipeline_status") == "DEGRADED":
            message = "دادهٔ کافی برای ارزیابی بازار در دسترس نیست؛ سیگنالی صادر نشد."
            key = f"DAILY_DEGRADED|{day}"
        else:
            message = "امروز سیگنال نیست"
            key = f"DAILY_NO_SIGNAL|{day}"
        if key not in daily_state:
            try:
                message_ids = asyncio.run(_send(token, chat_id, [message])) or []
                daily_message_id = message_ids[-1] if message_ids else None
                _finalize_delivery_metadata(payload, daily_message_id=daily_message_id)
                daily_state[key] = now.isoformat()
                state_path.write_text(json.dumps(sent_state, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
                return {"status": "SENT", "sent": 1}
            except Exception:
                LOG.exception("Telegram no-signal status delivery failed.")
                return {"status": "ERROR", "sent": 0}
        return {"status": "NO_NEW_MESSAGES", "sent": 0}

    if not pending:
        # ذخیرهٔ مهاجرت حتی وقتی هیچ پیام جدیدی برای ارسال وجود ندارد.
        state_path.write_text(json.dumps(sent_state, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        return {"status": "NO_NEW_MESSAGES", "sent": 0}

    try:
        chart_items = [(signal, caption) for _, _, signal, caption in pending if signal.get("chart_candles")]
        text_pending = [(signal, caption) for _, _, signal, caption in pending if not signal.get("chart_candles")]
        text_items = [caption for _, caption in text_pending]
        sent = 0
        chart_failures = 0
        if chart_items:
            sent, chart_failures = asyncio.run(_send_signal_photos(token, chat_id, chart_items))
        if text_items:
            quality = payload.get("quality") or {}
            requested = quality.get("symbols_requested")
            processed = quality.get("symbols_processed")
            header = (f"📊 {len(candidates)} سیگنال اقدام‌پذیر | پوشش اسکن: {processed}/{requested} نماد"
                      if requested else "")
            message = "\n\n".join(([header] if header else []) + text_items)
            message_ids = asyncio.run(_send(token, chat_id, [message[:4096]])) or []
            if message_ids:
                for signal, _ in text_pending:
                    signal["message_id_current"] = message_ids[-1]
            sent += 1
        _finalize_delivery_metadata(payload)
        for identity, fingerprint, _, _ in pending:
            signal_state[identity] = {"fingerprint": fingerprint, "sent_at": now.isoformat()}
        state_path.write_text(json.dumps(sent_state, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
        LOG.info("Telegram delivery succeeded: %d message(s), %d chart fallback(s).", sent, chart_failures)
        if not chart_items:
            return {"status": "SENT", "sent": sent}
        return {"status": "SENT_WITH_CHARTS" if chart_failures == 0 and not text_items else "SENT_TEXT_FALLBACK",
                "sent": sent}
    except Exception as exc:
        if "chat not found" in str(exc).lower():
            LOG.error("Telegram chat not found. Open the bot in Telegram, send /start, and verify TELEGRAM_CHAT_ID.")
            return {"status": "CHAT_NOT_FOUND", "sent": 0}
        LOG.exception("Telegram chart delivery failed.")
        return {"status": "ERROR", "sent": 0}



def notify_email(payload: dict) -> dict:
    """ایمیل جایگزین از طریق SMTP رایگانِ ارائه‌دهندهٔ ایمیل کاربر."""
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        return {"status": "SKIPPED_CI_VALIDATION", "sent": 0}
    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT") or "465")
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    recipient = os.getenv("ALERT_EMAIL_TO", "").strip()
    sender = (os.getenv("ALERT_EMAIL_FROM") or username).strip()
    if not all((host, username, password, recipient, sender)):
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}

    candidates = [
        signal for signal in payload.get("signals", [])
        if signal.get("status") in ("BUY_NOW", "SELL_NOW")
        and signal.get("entry") is not None
        and signal.get("stop_loss") is not None
        and len(signal.get("take_profit") or []) >= 2
    ]
    if not candidates:
        return {"status": "NO_ACTIONABLE_SIGNAL", "sent": 0}

    message = EmailMessage()
    message["Subject"] = f"Futures signals: {len(candidates)} actionable setup(s)"
    message["From"] = sender
    message["To"] = recipient
    message.set_content((chr(10) * 2).join(
        _format_signal(signal, payload) for signal in candidates
    ))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)
        LOG.info("SMTP fallback email sent.")
        return {"status": "SENT", "sent": 1}
    except Exception:
        LOG.exception("SMTP fallback email delivery failed.")
        return {"status": "ERROR", "sent": 0}


def send_test_message() -> dict:
    token, chat_id = _credentials()
    if not token or not chat_id:
        LOG.info("Telegram test skipped: credentials are not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}
    try:
        asyncio.run(_send(token, chat_id, [
            "✅ تست اتصال Futures Signal Autopilot",
            "ربات به سامانهٔ انتشار سیگنال متصل است.",
            "معامله فقط دستی است.",
        ]))
        LOG.info("Telegram test message delivered successfully.")
        return {"status": "TEST_SENT", "sent": 1}
    except Exception as exc:
        if "chat not found" in str(exc).lower():
            LOG.error("Telegram chat not found. Open the bot in Telegram and send /start; verify TELEGRAM_CHAT_ID.")
            return {"status": "CHAT_NOT_FOUND", "sent": 0}
        LOG.exception("Telegram test delivery failed.")
        return {"status": "ERROR", "sent": 0}
