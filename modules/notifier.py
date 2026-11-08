"""Optional Telegram notifications. Missing credentials cause a silent skip."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _configured() -> tuple[str | None, str | None]:
    return os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def _format_signal(payload: dict[str, Any], signal: dict[str, Any]) -> str:
    targets = signal.get("take_profit") or []
    if isinstance(targets, (int, float, str)):
        targets = [targets]
    tp_lines = "\n".join(f"TP{i}: {value}" for i, value in enumerate(targets, 1)) or "TP: ثبت نشده"
    confidence = signal.get("confidence") or "NOT_CALIBRATED"
    lfs = signal.get("lfs") or "NOT_CALCULATED"
    nss = signal.get("nss") or "NOT_CALCULATED"
    hypothesis = signal.get("hypothesis") or signal.get("reason") or "ثبت نشده"
    falsification = signal.get("falsification") or "ثبت نشده"
    dashboard = os.getenv("DASHBOARD_URL", "").strip()
    lines = [
        "🔔 سیگنال Tier A",
        "",
        f"نماد: {signal.get('symbol', 'نامشخص')}",
        f"جهت: {signal.get('side') or signal.get('status', 'نامشخص')}",
        f"ورود: {signal.get('entry') if signal.get('entry') is not None else 'ثبت نشده'}",
        f"SL: {signal.get('stop_loss') if signal.get('stop_loss') is not None else 'ثبت نشده'}",
        tp_lines,
        f"احتمال کالیبره: {confidence}",
        f"فرضیه: LFS={lfs}, NSS={nss}",
        f"ابطال: {falsification}",
    ]
    if dashboard:
        lines.extend(["", f"جزئیات: {dashboard}"])
    lines.extend(["", "معامله فقط دستی است؛ پیش از هر تصمیم، داده را مستقل بررسی کنید."])
    return "\n".join(lines)


async def _send(text: str, token: str, chat_id: str) -> None:
    from telegram import Bot

    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)


def _run_send(text: str, token: str, chat_id: str) -> None:
    try:
        asyncio.run(_send(text, token, chat_id))
    except Exception:
        logger.exception("Telegram delivery failed")
        raise


def notify_tier_a(payload: dict[str, Any]) -> dict[str, Any]:
    token, chat_id = _configured()
    if not token or not chat_id:
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}

    sent = 0
    for signal in payload.get("signals", []):
        if signal.get("tier") != "A" or signal.get("status") not in {"BUY_NOW", "SELL_NOW"}:
            continue
        _run_send(_format_signal(payload, signal), token, chat_id)
        sent += 1
    return {"status": "SENT" if sent else "NO_NEW_TIER_A", "sent": sent}


def send_test_message() -> dict[str, Any]:
    token, chat_id = _configured()
    if not token or not chat_id:
        return {"status": "SKIPPED_NOT_CONFIGURED", "sent": 0}
    message = (
        "🔔 تست اتصال ربات سیگنال\n\n"
        "اتصال تلگرام موفق است.\n"
        "این سامانه فقط داده و تحلیل ارائه می‌کند؛ ثبت سفارش خودکار غیرفعال است."
    )
    _run_send(message, token, chat_id)
    return {"status": "TEST_SENT", "sent": 1}
