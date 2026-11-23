#!/usr/bin/env python3
"""Strategy-agnostic Telegram signal delivery with SQLite idempotency."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_CAPTION_LENGTH = 1024
API_BASE = "https://api.telegram.org"


class TelegramDeliveryError(RuntimeError):
    """Definite Telegram API rejection."""


class TelegramDeliveryUnknown(RuntimeError):
    """Request outcome unknown; retry is blocked to prevent duplicate posts."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _value(value: Any, fallback: str = "نامشخص") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def normalize_signal(signal: dict[str, Any]) -> dict[str, Any]:
    signal_id = str(signal.get("signal_id") or "").strip()
    symbol = str(signal.get("symbol") or "").strip().upper()
    direction = str(signal.get("direction") or "").strip().upper()
    timeframe = str(signal.get("timeframe") or "").strip()
    chart = signal.get("chart")
    if not signal_id:
        raise ValueError("signal_id is required")
    if not symbol or not direction or not timeframe:
        raise ValueError("symbol, direction and timeframe are required")
    if len(direction) > 32 or any(ord(char) < 32 for char in direction):
        raise ValueError("direction must be a short printable label")
    if not isinstance(chart, str) or not chart.strip():
        raise ValueError("chart must be a local image path or HTTPS URL")
    chart = chart.strip()
    if chart.startswith(("http://", "https://")):
        if not chart.startswith("https://"):
            raise ValueError("remote chart URL must use HTTPS")
    else:
        path = Path(chart)
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("chart must point to an existing PNG/JPEG file")
    return {**signal, "signal_id": signal_id, "symbol": symbol,
            "direction": direction, "timeframe": timeframe, "chart": chart}


def build_caption(signal: dict[str, Any]) -> str:
    levels = signal.get("levels") or {}
    targets = signal.get("targets")
    if targets is None:
        targets = [v for v in (signal.get("tp1"), signal.get("tp2"), signal.get("tp3")) if v is not None]
    if targets is not None and not isinstance(targets, (list, tuple)):
        targets = [targets]
    target_text = " | ".join(_value(v) for v in targets) if targets else "ثبت نشده"
    lines = [
        f"1) نماد و جهت: {signal['symbol']} | {signal['direction']} | {signal['timeframe']}",
        f"2) وضعیت و زمان: {_value(signal.get('status'))} | {_value(signal.get('generated_at'))}",
        f"3) فرضیه: {_value(signal.get('hypothesis'))}",
        f"4) ورود: {_value(levels.get('entry', signal.get('entry')))}",
        f"5) حد ضرر: {_value(levels.get('stop_loss', signal.get('stop_loss')))}",
        f"6) اهداف: {target_text}",
        f"7) نسبت ریسک به بازده: {_value(signal.get('risk_reward', signal.get('rr')))}",
        f"8) اطمینان/کالیبراسیون: {_value(signal.get('confidence'))} | {_value(signal.get('calibration_status'), 'NOT_CALIBRATED')}",
        f"9) ابطال فرضیه: {_value(signal.get('invalidation', signal.get('falsification')))}",
    ]
    caption = "\n".join(lines)
    if signal.get("source"):
        caption += f"\nمنبع: {_value(signal['source'])}"
    if signal.get("signal_url"):
        caption += f"\nجزئیات: {_value(signal['signal_url'])}"
    if len(caption) > MAX_CAPTION_LENGTH:
        raise ValueError(f"caption too long for Telegram photo: {len(caption)} characters")
    return caption


def initialize_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS telegram_deliveries (
                signal_id TEXT PRIMARY KEY,
                payload_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                telegram_message_id TEXT,
                error TEXT
            )
        """)
        connection.commit()


def reserve_delivery(db_path: Path, signal_id: str, payload_sha256: str) -> bool:
    """Atomic reservation; SENT/SENDING/UNKNOWN IDs are never resent."""
    initialize_db(db_path)
    with sqlite3.connect(db_path, timeout=30, isolation_level=None) as connection:
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload_sha256,status FROM telegram_deliveries WHERE signal_id=?",
            (signal_id,),
        ).fetchone()
        if row:
            old_hash, status = row
            if old_hash != payload_sha256:
                connection.execute("ROLLBACK")
                raise ValueError("signal_id already exists with a different payload")
            if status != "FAILED":
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                "UPDATE telegram_deliveries SET status='SENDING',updated_at=?,error=NULL WHERE signal_id=?",
                (_now(), signal_id),
            )
        else:
            connection.execute(
                """INSERT INTO telegram_deliveries
                (signal_id,payload_sha256,status,created_at,updated_at)
                VALUES (?,?,'SENDING',?,?)""",
                (signal_id, payload_sha256, _now(), _now()),
            )
        connection.execute("COMMIT")
        return True


def update_delivery(db_path: Path, signal_id: str, status: str,
                    message_id: str | None = None, error: str | None = None) -> None:
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.execute(
            """UPDATE telegram_deliveries SET status=?,updated_at=?,
            telegram_message_id=?,error=? WHERE signal_id=?""",
            (status, _now(), message_id, error, signal_id),
        )
        connection.commit()


def telegram_send_photo(token: str, chat_id: str, chart: str, caption: str,
                        timeout: int = 30) -> str:
    endpoint = f"{API_BASE}/bot{token}/sendPhoto"
    if chart.startswith("https://"):
        body = urllib.parse.urlencode({"chat_id": chat_id, "photo": chart, "caption": caption}).encode()
        request = urllib.request.Request(endpoint, data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    else:
        boundary = "----PITTelegram" + uuid.uuid4().hex
        fields = {"chat_id": chat_id, "caption": caption}
        chunks = []
        for name, value in fields.items():
            chunks += [f"--{boundary}\r\n".encode(),
                       f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                       value.encode("utf-8"), b"\r\n"]
        path = Path(chart)
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        chunks += [f"--{boundary}\r\n".encode(),
                   f'Content-Disposition: form-data; name="photo"; filename="{path.name}"\r\n'.encode(),
                   f"Content-Type: {mime}\r\n\r\n".encode(), path.read_bytes(), b"\r\n",
                   f"--{boundary}--\r\n".encode()]
        request = urllib.request.Request(endpoint, data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TelegramDeliveryError(f"Telegram HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TelegramDeliveryUnknown(str(exc)) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramDeliveryUnknown("Telegram returned invalid JSON") from exc
    if not payload.get("ok"):
        raise TelegramDeliveryError(f"Telegram API rejected request: {_value(payload.get('description'))}")
    return str((payload.get("result") or {}).get("message_id", ""))


def send_signal(signal_path: Path, db_path: Path, token: str | None = None,
                chat_id: str | None = None) -> dict[str, Any]:
    raw = signal_path.read_bytes()
    signal = normalize_signal(json.loads(raw.decode("utf-8")))
    canonical_payload = json.dumps(signal, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(canonical_payload).hexdigest()
    caption = build_caption(signal)
    bot_token = token or os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    target_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not target_chat:
        raise RuntimeError("Telegram bot token (TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN) and TELEGRAM_CHAT_ID are required")
    if not reserve_delivery(db_path, signal["signal_id"], payload_hash):
        return {"status": "DUPLICATE_SKIPPED", "signal_id": signal["signal_id"]}
    try:
        message_id = telegram_send_photo(bot_token, target_chat, signal["chart"], caption)
    except TelegramDeliveryError as exc:
        update_delivery(db_path, signal["signal_id"], "FAILED", error=str(exc))
        raise
    except Exception as exc:
        update_delivery(db_path, signal["signal_id"], "UNKNOWN", error=str(exc))
        raise
    update_delivery(db_path, signal["signal_id"], "SENT", message_id=message_id)
    return {"status": "SENT", "signal_id": signal["signal_id"], "telegram_message_id": message_id}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one strategy-agnostic signal JSON to Telegram.")
    parser.add_argument("--signal", required=True, help="Path to signal JSON")
    parser.add_argument("--db", default="data/telegram_delivery.sqlite3")
    args = parser.parse_args()
    print(json.dumps(send_signal(Path(args.signal), Path(args.db)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
