"""Optional Telegram Tier-A notifications using python-telegram-bot v20+."""
from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from telegram import Bot

LOG = logging.getLogger("signal_autopilot.telegram")

def _credentials():
    return (os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()

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
    tp1 = targets[0] if len(targets) > 0 else signal.get("take_profit_1", "—")
    tp2 = targets[1] if len(targets) > 1 else signal.get("take_profit_2", "—")
    calibrated = signal.get("calibrated_probability_pct")
    probability = f"{calibrated}%" if isinstance(calibrated, (int, float)) else "NOT_CALIBRATED"
    return "\n".join([
        "🔔 سیگنال Tier A",
        "",
        f"نماد: {signal.get('symbol', '—')}",
        f"جهت: {signal.get('side') or signal.get('direction') or '—'}",
        f"ورود: {signal.get('entry', '—')}",
        f"SL: {signal.get('stop_loss', '—')}",
        f"TP1: {tp1}",
        f"TP2: {tp2}",
        f"احتمال کالیبره: {probability}",
        f"فرضیه: LFS={signal.get('lfs', 'NOT_AVAILABLE')}, NSS={signal.get('nss', 'NOT_AVAILABLE')}",
        f"ابطال: {signal.get('falsification') or signal.get('invalidation') or 'در دادهٔ اسکن ثبت نشده'}",
        f"توضیح: {signal.get('hypothesis') or signal.get('reason') or '—'}",
        f"زمان UTC: {payload.get('generated_at_utc', '—')}",
        f"برای جزئیات: {os.getenv('DASHBOARD_URL', 'آدرس داشبورد پس از Deploy ثبت می‌شود')}",
        "معامله فقط با تصمیم و مسئولیت کاربر انجام می‌شود.",
    ])

def notify_tier_a(payload: dict):
    token, chat_id = _credentials()
    if not token or not chat_id:
        LOG.info("Telegram skipped: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}
    candidates = [s for s in payload.get("signals", [])
                  if s.get("tier") == "A" and s.get("status") in ("BUY_NOW", "SELL_NOW")]
    state_path = Path(os.getenv("TELEGRAM_STATE_PATH", str(Path(__file__).resolve().parents[1] / "data" / "telegram_sent.json")))
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        sent_state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        sent_state = {}
    now = datetime.now(timezone.utc)
    sent_state = {k:v for k,v in sent_state.items()
                  if _parse_time(v) and now - _parse_time(v) < timedelta(hours=48)}
    pending = []
    for signal in candidates:
        key = "|".join(str(signal.get(k, "")) for k in ("symbol", "status", "side", "entry", "stop_loss"))
        if key not in sent_state:
            pending.append((key, _format_signal(signal, payload)))
    if not pending:
        LOG.info("Telegram: no new Tier-A signals.")
        return {"status": "NO_NEW_TIER_A", "sent": 0}
    try:
        for key, message in pending:
            asyncio.run(_send(token, chat_id, [message]))
            sent_state[key] = now.isoformat()
            state_path.write_text(json.dumps(sent_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        LOG.info("Telegram delivery succeeded: %d Tier-A message(s).", len(pending))
        return {"status": "SENT", "sent": len(pending)}
    except Exception:
        LOG.exception("Telegram delivery failed.")
        return {"status": "ERROR", "sent": 0}

def send_test_message():
    token, chat_id = _credentials()
    if not token or not chat_id:
        LOG.info("Telegram test skipped: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID is not configured.")
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}
    message = "✅ تست اتصال Futures Signal Autopilot\nربات تلگرام به GitHub Actions متصل است.\nمعامله فقط دستی است."
    try:
        asyncio.run(_send(token, chat_id, [message]))
        LOG.info("Telegram test message delivered successfully.")
        return {"status": "TEST_SENT", "sent": 1}
    except Exception:
        LOG.exception("Telegram test delivery failed.")
        return {"status": "ERROR", "sent": 0}
