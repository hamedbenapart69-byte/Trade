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


async def _send_signal_photos(token: str, chat_id: str, signals: list[tuple[dict, str]], message_id_field: str = "message_id_current") -> tuple[int, int]:
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
                    signal[message_id_field] = message_id
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
                    signal[message_id_field] = message_id
            sent += 1
    return sent, chart_failures


def _parse_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def _load_destination_state(state_path: Path, destination: str) -> dict:
    """خواندن دفتر ارسال مستقل هر مقصد از یک فایل پایدار مشترک."""
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("__schema_version__") == 3 and isinstance(raw.get("destinations"), dict):
        value = raw["destinations"].get(destination, {})
        return value if isinstance(value, dict) else {}
    return raw if destination == "current" else {}


def _save_destination_state(state_path: Path, destination: str, destination_state: dict) -> None:
    """ذخیره وضعیت هر مقصد بدون بازنویسی دفتر مقصد دیگر."""
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("__schema_version__") == 3 and isinstance(raw.get("destinations"), dict):
        destinations = raw["destinations"]
    else:
        current_state = raw if raw else {}
        destinations = {"current": current_state, "audience": {}}
    destinations[destination] = destination_state
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({
        "__schema_version__": 3,
        "destinations": destinations,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")




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


def _finalize_delivery_metadata(payload: dict, daily_message_id: int | None = None,
                                destination: str = "current") -> None:
    """شناسه‌های واقعی هر مقصد را جدا ثبت می‌کند و زمان انتشار را مشترک نگه می‌دارد."""
    field = "message_id_" + destination
    destination_ids = {
        str(signal.get("symbol")): signal[field]
        for signal in payload.get("signals", [])
        if isinstance(signal.get(field), int) and signal[field] > 0
    }
    if isinstance(daily_message_id, int) and daily_message_id > 0:
        destination_ids["_daily_status"] = daily_message_id
    payload[field] = destination_ids or None
    any_delivery = any(payload.get(name) for name in ("message_id_current", "message_id_audience"))
    published_at = payload.get("published_at") or (
        datetime.now(timezone.utc).isoformat() if any_delivery else None
    )
    payload["published_at"] = published_at
    for signal in payload.get("signals", []):
        if signal.get("message_id_current") is not None or signal.get("message_id_audience") is not None:
            signal["published_at"] = published_at
        message_id = signal.get(field)
        if isinstance(message_id, int) and message_id > 0:
            LOG.info("TELEGRAM_SIGNAL_MESSAGE_ID destination=%s symbol=%s message_id=%s",
                     destination, signal.get("symbol"), message_id)
    if isinstance(daily_message_id, int) and daily_message_id > 0:
        LOG.info("TELEGRAM_DAILY_STATUS_MESSAGE_ID destination=%s message_id=%s",
                 destination, daily_message_id)


def _notify_tier_a_single_destination(payload: dict, chat_id: str, destination: str) -> dict:
    """نام قدیمی تابع حفظ شده؛ هر سیگنال با تصویر چارت و تحلیل ارسال می‌شود."""
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        return {"status": "SKIPPED_CI_VALIDATION", "sent": 0}
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token or not chat_id:
        LOG.info("Telegram skipped for %s: token or destination is not configured.", destination)
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
        sent_state = _load_destination_state(state_path, destination)
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
                _finalize_delivery_metadata(payload, daily_message_id=daily_message_id, destination=destination)
                daily_state[key] = now.isoformat()
                _save_destination_state(state_path, destination, sent_state)
                return {"status": "SENT", "sent": 1}
            except Exception:
                LOG.exception("Telegram no-signal status delivery failed.")
                return {"status": "ERROR", "sent": 0}
        return {"status": "NO_NEW_MESSAGES", "sent": 0}

    if not pending:
        # ذخیرهٔ مهاجرت حتی وقتی هیچ پیام جدیدی برای ارسال وجود ندارد.
        _save_destination_state(state_path, destination, sent_state)
        return {"status": "NO_NEW_MESSAGES", "sent": 0}

    try:
        chart_items = [(signal, caption) for _, _, signal, caption in pending if signal.get("chart_candles")]
        text_pending = [(signal, caption) for _, _, signal, caption in pending if not signal.get("chart_candles")]
        text_items = [caption for _, caption in text_pending]
        sent = 0
        chart_failures = 0
        if chart_items:
            sent, chart_failures = asyncio.run(_send_signal_photos(token, chat_id, chart_items, "message_id_" + destination))
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
                    signal["message_id_" + destination] = message_ids[-1]
            sent += 1
        _finalize_delivery_metadata(payload, destination=destination)
        for identity, fingerprint, _, _ in pending:
            signal_state[identity] = {"fingerprint": fingerprint, "sent_at": now.isoformat()}
        _save_destination_state(state_path, destination, sent_state)
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



def notify_tier_a(payload: dict) -> dict:
    """ارسال مستقل به کانال فعلی و کانال مخاطبان، با دفتر idempotency جدا برای هر مقصد."""
    _initialize_delivery_metadata(payload)
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        return {"status": "SKIPPED_CI_VALIDATION", "sent": 0}
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    current_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    audience_chat = os.getenv("TELEGRAM_AUDIENCE_CHANNEL_ID", "").strip()
    if not token or not (current_chat or audience_chat):
        LOG.info("Telegram skipped: token or all destinations are not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}

    destinations = []
    if current_chat:
        destinations.append(("current", current_chat))
    if audience_chat and audience_chat != current_chat:
        destinations.append(("audience", audience_chat))

    results = {
        destination: _notify_tier_a_single_destination(payload, chat_id, destination)
        for destination, chat_id in destinations
    }
    if len(results) == 1:
        return next(iter(results.values()))

    sent = sum(int(result.get("sent", 0)) for result in results.values())
    failures = any(result.get("status") in {"ERROR", "CHAT_NOT_FOUND", "SKIPPED_NOT_CONFIGURED"}
                   for result in results.values())
    if sent and failures:
        status = "PARTIAL"
    elif sent:
        status = "SENT"
    elif failures:
        status = "ERROR"
    else:
        status = "NO_NEW_MESSAGES"
    return {"status": status, "sent": sent, "destinations": results}



def _format_legacy_quarantine_status(state: dict) -> str:
    """ساخت پیام وضعیت قرنطینه؛ این پیام ادعای ارزیابی زنده بازار نمی‌کند."""
    if state.get("lifecycle") != "LEGACY_RESEARCH_ONLY" or state.get("production_enabled") is not False:
        raise ValueError("LEGACY_QUARANTINE_STATE_INVALID")
    return "\\n".join([
        "⛔ وضعیت موتور یک‌ساعته",
        "Lifecycle: LEGACY_RESEARCH_ONLY",
        "production_enabled: false",
        "خروجی معاملاتی: NO_QUALIFIED_SETUP",
        "توضیح: موتور در قرنطینه است؛ این وضعیت حاصل اسکن زنده بازار نیست.",
    ])


def send_legacy_quarantine_status_test(state: dict) -> dict:
    """ارسال اختیاری فقط به مقصد تست؛ هرگز از کانال اصلی fallback نمی‌گیرد."""
    if os.getenv("GITHUB_EVENT_NAME") == "pull_request":
        return {"status": "SKIPPED_CI_VALIDATION", "sent": 0}
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    test_chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID", "").strip()
    if not token or not test_chat_id:
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}
    message = _format_legacy_quarantine_status(state)
    try:
        message_ids = asyncio.run(_send(token, test_chat_id, [message])) or []
        return {"status": "TEST_SENT" if message_ids else "ERROR",
                "sent": 1 if message_ids else 0}
    except Exception:
        LOG.exception("Telegram quarantine test delivery failed.")
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
    """آزمون ارسال به تمام مقصدهای پیکربندی‌شده؛ کانال مخاطبان اختیاری است."""
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    current_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    audience_chat = os.getenv("TELEGRAM_AUDIENCE_CHANNEL_ID", "").strip()
    targets = []
    if current_chat:
        targets.append(("current", current_chat))
    if audience_chat and audience_chat != current_chat:
        targets.append(("audience", audience_chat))
    if not token or not targets:
        LOG.info("Telegram test skipped: token or destinations are not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}

    sent = 0
    failures = {}
    for destination, chat_id in targets:
        try:
            asyncio.run(_send(token, chat_id, [
                "✅ تست اتصال Futures Signal Autopilot",
                f"مقصد: {destination}",
                "ربات به سامانهٔ انتشار سیگنال متصل است.",
                "معامله فقط دستی است.",
            ]))
            sent += 1
            LOG.info("Telegram test message delivered: destination=%s", destination)
        except Exception as exc:
            failures[destination] = type(exc).__name__ + ":" + str(exc)[:200]
            LOG.exception("Telegram test delivery failed: destination=%s", destination)
    if failures and sent:
        return {"status": "PARTIAL", "sent": sent, "failures": failures}
    if failures:
        return {"status": "ERROR", "sent": 0, "failures": failures}
    return {"status": "TEST_SENT", "sent": sent}
