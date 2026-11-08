"""Telegram delivery for actionable futures signals and daily no-signal status."""
from __future__ import annotations

import asyncio
import json
import logging
import os

import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telegram import Bot
from telegram.error import ChatNotFound

LOG = logging.getLogger("signal_autopilot.telegram")


def _credentials() -> tuple[str, str]:
    token = (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id


async def _send(token: str, chat_id: str, messages: list[str]) -> None:
    async with Bot(token=token) as bot:
        for message in messages:
            await bot.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)


def _parse_time(value):
    try:
        return datetime.fromisoformat(value)
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
        f"حد ضرر: {signal.get('stop_loss') if signal.get('stop_loss') is not None else '—'}",
        f"تارگت ۱: {tp1}",
        f"تارگت ۲: {tp2}",
        f"زمان UTC: {payload.get('generated_at_utc', '—')}",
        dashboard,
    ])


def notify_tier_a(payload: dict) -> dict:
    """نام قدیمی تابع حفظ شده؛ همه سیگنال‌های معتبر خرید/فروش ارسال می‌شوند."""
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
    sent_state = {
        key: value for key, value in sent_state.items()
        if _parse_time(value) and now - _parse_time(value) < timedelta(hours=48)
    }
    pending: list[tuple[str, str]] = []

    for signal in candidates:
        key = "|".join(str(signal.get(k, "")) for k in (
            "symbol", "status", "side", "entry", "stop_loss", "take_profit"
        ))
        if key not in sent_state:
            pending.append((key, _format_signal(signal, payload)))

    if not candidates:
        generated = payload.get("generated_at_utc") or now.isoformat()
        day = str(generated)[:10]
        if payload.get("pipeline_status") == "DEGRADED":
            message = "دادهٔ کافی برای ارزیابی بازار در دسترس نیست؛ سیگنالی صادر نشد."
            key = f"DAILY_DEGRADED|{day}"
        else:
            message = "امروز سیگنال نیست"
            key = f"DAILY_NO_SIGNAL|{day}"
        if key not in sent_state:
            pending.append((key, message))

    if not pending:
        return {"status": "NO_NEW_MESSAGES", "sent": 0}

    # سیگنال‌های تازه در یک پیام/چند بخشِ زیر سقف تلگرام تجمیع می‌شوند.
    header = ""
    quality = payload.get("quality") or {}
    requested = quality.get("symbols_requested")
    processed = quality.get("symbols_processed")
    if requested:
        header = f"📊 {len(candidates)} سیگنال اقدام‌پذیر | پوشش اسکن: {processed}/{requested} نماد"
    chunks: list[str] = []
    current = header
    for _, message in pending:
        candidate = (current + "\n\n" if current else "") + message
        if current and len(candidate) > 3800:
            chunks.append(current)
            current = message
        else:
            current = candidate
    if current:
        chunks.append(current)

    sent = 0
    try:
        asyncio.run(_send(token, chat_id, chunks))
        for key, _ in pending:
            sent_state[key] = now.isoformat()
        state_path.write_text(
            json.dumps(sent_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        sent = len(chunks)
        LOG.info("Telegram delivery succeeded: %d message(s) for %d item(s).", sent, len(pending))
        return {"status": "SENT", "sent": sent}
    except ChatNotFound:
        LOG.error("Telegram chat not found. Open the bot in Telegram, send /start, and verify TELEGRAM_CHAT_ID.")
        return {"status": "CHAT_NOT_FOUND", "sent": sent}
    except Exception:
        LOG.exception("Telegram delivery failed.")
        return {"status": "ERROR", "sent": sent}



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
    except ChatNotFound:
        LOG.error("Telegram chat not found. Open the bot in Telegram and send /start; verify TELEGRAM_CHAT_ID.")
        return {"status": "CHAT_NOT_FOUND", "sent": 0}
    except Exception:
        LOG.exception("Telegram test delivery failed.")
        return {"status": "ERROR", "sent": 0}
