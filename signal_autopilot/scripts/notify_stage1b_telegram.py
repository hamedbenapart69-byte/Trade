#!/usr/bin/env python3
"""Trusted Telegram notifier: consumes a bounded JSON report, never executes scanner code."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}$")
MAX_REPORT_BYTES = 2_000_000
MAX_MESSAGE_LENGTH = 3900


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def validate_report(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("REPORT_NOT_REGULAR_FILE")
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("REPORT_TOO_LARGE")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("REPORT_ROOT_NOT_OBJECT")
    if payload.get("stage") != "STAGE_1_UNCALIBRATED":
        raise ValueError("UNEXPECTED_REPORT_STAGE")
    if payload.get("calibration") != "UNCALIBRATED":
        raise ValueError("UNEXPECTED_CALIBRATION_STATE")
    if payload.get("decision_policy") != "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW":
        raise ValueError("UNEXPECTED_DECISION_POLICY")
    if payload.get("universe_count") != 27 or payload.get("symbols_reported") != 27:
        raise ValueError("UNIVERSE_COVERAGE_INVALID")
    rows = payload.get("symbols")
    if not isinstance(rows, list) or len(rows) != 27:
        raise ValueError("SYMBOL_ROWS_INVALID")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("SYMBOL_ROW_NOT_OBJECT")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or symbol in seen:
            raise ValueError("SYMBOL_ID_INVALID_OR_DUPLICATE")
        seen.add(symbol)
    generated = payload.get("generated_at_utc")
    if not isinstance(generated, str):
        raise ValueError("REPORT_TIMESTAMP_MISSING")
    parsed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("REPORT_TIMESTAMP_NOT_TIMEZONE_AWARE")
    return payload


def candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in payload["symbols"]:
        if row.get("decision") != "WATCHLIST" or row.get("veto") != "PASS":
            continue
        if row.get("direction") not in {"BUY", "SELL"}:
            continue
        entry = finite_number(row.get("entry"))
        stop = finite_number(row.get("stop_loss"))
        target = finite_number(row.get("take_profit"))
        rr = finite_number(row.get("rr"))
        if entry is None or stop is None or target is None or rr is None or min(entry, stop, target) <= 0 or rr <= 0:
            continue
        candidates.append({
            "symbol": row["symbol"],
            "direction": row["direction"],
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr,
        })
    return candidates


def build_message(payload: dict[str, Any]) -> str:
    candidates = candidate_rows(payload)
    timestamp = payload["generated_at_utc"].replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")
    lines = [
        "گزارش اسکن Stage 1B | LRT-15m",
        f"زمان تولید: {timestamp}",
        "پوشش: 27/27 نماد",
        "وضعیت کالیبراسیون: NOT_CALIBRATED",
        "سیاست: WATCHLIST فقط؛ BUY_NOW/SELL_NOW صادر نمی‌شود.",
        f"نامزدهای زیرنظر: {len(candidates)}",
    ]
    for item in candidates:
        lines.append(
            f"{item['symbol']} | {item['direction']} | "
            f"Entry {item['entry']:.10g} | SL {item['stop']:.10g} | "
            f"TP2 {item['target']:.10g} | R:R {item['rr']:.3g}"
        )
    if not candidates:
        lines.append("هیچ موقعیت WATCHLIST واجد شرایطی در این اسکن ثبت نشد.")
    lines.append("این گزارش اعلان پژوهشی است؛ سفارش یا اجرای معامله انجام نمی‌شود.")
    message = "\n".join(lines)
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValueError("TELEGRAM_MESSAGE_TOO_LONG")
    return message


def send_message(token: str, chat_id: str, message: str) -> None:
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_CREDENTIALS_MISSING")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"TELEGRAM_HTTP_ERROR:{exc.code}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TELEGRAM_NETWORK_ERROR:{type(exc.reason).__name__}") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("TELEGRAM_API_REJECTED_MESSAGE")
    message_id = (result.get("result") or {}).get("message_id")
    if not isinstance(message_id, int):
        raise RuntimeError("TELEGRAM_MESSAGE_ID_MISSING")
    print(f"TELEGRAM_DELIVERY=SUCCESS message_id={message_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    payload = validate_report(args.report)
    message = build_message(payload)
    send_message(
        os.environ.get("TELEGRAM_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
        message,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TELEGRAM_DELIVERY=FAILED reason={type(exc).__name__}:{str(exc)[:160]}")
        raise SystemExit(1)
