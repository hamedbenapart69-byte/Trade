#!/usr/bin/env python3
"""Trusted Telegram notifier: consumes a bounded JSON report, never executes scanner code."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from pathlib import Path
from typing import Any

SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}$")
MAX_REPORT_BYTES = 2_000_000
MAX_MESSAGE_LENGTH = 3900
MAX_REPORT_AGE = timedelta(hours=4)
MAX_FUTURE_SKEW = timedelta(minutes=5)
EXPECTED_UNIVERSE_SIZE = 27


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def load_expected_universe(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("UNIVERSE_NOT_REGULAR_FILE")
    if path.stat().st_size > 100_000:
        raise ValueError("UNIVERSE_TOO_LARGE")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("UNIVERSE_ROOT_NOT_OBJECT")
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("UNIVERSE_DEFINITION_INVALID")
    if any(not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) for symbol in symbols):
        raise ValueError("UNIVERSE_SYMBOL_INVALID")
    expected = set(symbols)
    if len(expected) != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("UNIVERSE_SYMBOL_DUPLICATE")
    return expected


def validate_report(
    path: Path,
    universe_path: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
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

    expected_symbols = load_expected_universe(universe_path)
    rows = payload.get("symbols")
    if payload.get("universe_count") != len(expected_symbols):
        raise ValueError("UNIVERSE_COVERAGE_INVALID")
    if payload.get("symbols_reported") != len(expected_symbols):
        raise ValueError("UNIVERSE_COVERAGE_INVALID")
    if not isinstance(rows, list) or len(rows) != len(expected_symbols):
        raise ValueError("SYMBOL_ROWS_INVALID")

    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("SYMBOL_ROW_NOT_OBJECT")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or symbol in seen:
            raise ValueError("SYMBOL_ID_INVALID_OR_DUPLICATE")
        seen.add(symbol)
    if seen != expected_symbols:
        missing = sorted(expected_symbols - seen)
        unexpected = sorted(seen - expected_symbols)
        raise ValueError(
            f"UNIVERSE_SYMBOL_SET_MISMATCH:missing={','.join(missing)}:"
            f"unexpected={','.join(unexpected)}"
        )

    generated = payload.get("generated_at_utc")
    if not isinstance(generated, str):
        raise ValueError("REPORT_TIMESTAMP_MISSING")
    try:
        parsed = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("REPORT_TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("REPORT_TIMESTAMP_NOT_TIMEZONE_AWARE")
    reference_now = now or datetime.now(timezone.utc)
    if reference_now.tzinfo is None:
        raise ValueError("VALIDATION_CLOCK_NOT_TIMEZONE_AWARE")
    age = reference_now.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
    if age > MAX_REPORT_AGE:
        raise ValueError("REPORT_STALE")
    if age < -MAX_FUTURE_SKEW:
        raise ValueError("REPORT_TIMESTAMP_TOO_FAR_IN_FUTURE")
    return payload


def validate_dashboard_url(value: str) -> str:
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("DASHBOARD_URL_UNAVAILABLE_OR_INVALID")
    return url.rstrip("/")


def candidate_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in payload["symbols"]:
        if row.get("mode") != "PRODUCTION":
            continue
        if row.get("decision") != "WATCHLIST":
            continue
        if row.get("veto") != "PASS":
            raise ValueError("WATCHLIST_VETO_NOT_PASS")
        direction = row.get("direction")
        if direction not in {"BUY", "SELL"}:
            raise ValueError("WATCHLIST_DIRECTION_INVALID")
        entry = finite_number(row.get("entry"))
        stop = finite_number(row.get("stop_loss"))
        target1 = finite_number(row.get("take_profit_1"))
        target2 = finite_number(row.get("take_profit"))
        rr = finite_number(row.get("rr"))
        if any(value is None for value in (entry, stop, target1, target2, rr)) or min(entry, stop, target1, target2) <= 0 or rr <= 0:
            raise ValueError("WATCHLIST_LEVELS_INVALID")
        risk, reward1, reward2 = (
            (entry - stop, target1 - entry, target2 - entry)
            if direction == "BUY"
            else (stop - entry, entry - target1, entry - target2)
        )
        if risk <= 0 or reward1 <= 0 or reward2 <= reward1:
            raise ValueError("WATCHLIST_LEVEL_DIRECTION_INVALID")
        computed_rr = reward2 / risk
        if not math.isclose(rr, computed_rr, rel_tol=0.10, abs_tol=0.05):
            raise ValueError("WATCHLIST_RR_MISMATCH")
        hypothesis = row.get("hypothesis")
        falsification = row.get("falsification")
        if not isinstance(hypothesis, str) or hypothesis.strip().upper() in {"", "UNAVAILABLE", "NOT_AVAILABLE", "N/A", "NONE"}:
            raise ValueError("WATCHLIST_HYPOTHESIS_MISSING")
        if not isinstance(falsification, str) or falsification.strip().upper() in {"", "UNAVAILABLE", "NOT_AVAILABLE", "N/A", "NONE"}:
            raise ValueError("WATCHLIST_FALSIFICATION_MISSING")
        if len(hypothesis) > 700 or len(falsification) > 700:
            raise ValueError("WATCHLIST_THESIS_TOO_LONG")
        cvd = row.get("cvd")
        cvd = cvd if isinstance(cvd, dict) else {}
        lfs_score = finite_number(row.get("lfs_score"))
        lfs_coverage = finite_number(row.get("lfs_coverage_pct"))
        if lfs_score is not None and not 0 <= lfs_score <= 1:
            raise ValueError("WATCHLIST_LFS_SCORE_OUT_OF_RANGE")
        if lfs_coverage is not None and not 0 <= lfs_coverage <= 100:
            raise ValueError("WATCHLIST_LFS_COVERAGE_OUT_OF_RANGE")
        candidates.append({
            "symbol": row["symbol"],
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target1": target1,
            "target2": target2,
            "rr": rr,
            "hypothesis": hypothesis.strip(),
            "falsification": falsification.strip(),
            "cvd_source": str(cvd.get("source") or "UNAVAILABLE"),
            "lfs_score": lfs_score,
            "lfs_status": str(row.get("lfs_status") or "UNAVAILABLE"),
            "lfs_coverage_pct": lfs_coverage,
        })
    return candidates


def build_messages(payload: dict[str, Any], dashboard_url: str) -> list[str]:
    dashboard = validate_dashboard_url(dashboard_url)
    candidates = candidate_rows(payload)
    timestamp = payload["generated_at_utc"].replace("T", " ").replace("+00:00", " UTC").replace("Z", " UTC")
    header = [
        "گزارش اسکن Stage 1B | LRT-15m",
        f"زمان تولید: {timestamp}",
        "پوشش: 27/27 نماد",
        "کالیبراسیون: NOT_CALIBRATED",
        "EV: NOT_CALCULATED",
        "Data Gate: NOT_REPORTED",
        "سیاست: WATCHLIST فقط؛ BUY_NOW/SELL_NOW صادر نمی‌شود.",
        f"نامزدهای زیرنظر: {len(candidates)}",
        f"داشبورد: {dashboard}",
    ]
    if not candidates:
        return ["\n".join(header + [
            "هیچ موقعیت WATCHLIST واجد شرایطی در این اسکن ثبت نشد.",
            "این گزارش اعلان پژوهشی است؛ سفارش یا اجرای معامله انجام نمی‌شود.",
        ])]

    messages: list[str] = []
    current = list(header)
    for item in candidates:
        block = "\n".join([
            f"{item['symbol']} | {item['direction']}",
            f"Entry: {item['entry']:.10g} | SL: {item['stop']:.10g}",
            f"TP1: {item['target1']:.10g} | TP2: {item['target2']:.10g} | R:R(TP2): {item['rr']:.3g}",
            "Confidence: NOT_CALIBRATED",
            f"CVD: {item['cvd_source']}",
            f"LFS: {item['lfs_score'] if item['lfs_score'] is not None else 'UNAVAILABLE'} | status={item['lfs_status']} | coverage={item['lfs_coverage_pct'] if item['lfs_coverage_pct'] is not None else 'UNAVAILABLE'}",
            f"Hypothesis: {item['hypothesis']}",
            f"Falsification: {item['falsification']}",
        ])
        if len("\n".join(current + [block])) > MAX_MESSAGE_LENGTH:
            messages.append("\n".join(current))
            current = [
                "گزارش اسکن Stage 1B | LRT-15m (ادامه)",
                f"زمان تولید: {timestamp}",
                f"داشبورد: {dashboard}",
            ]
        if len("\n".join(current + [block])) > MAX_MESSAGE_LENGTH:
            raise ValueError("TELEGRAM_CANDIDATE_BLOCK_TOO_LONG")
        current.append(block)
    current.append("این گزارش WATCHLIST پژوهشی است؛ سفارش یا اجرای معامله انجام نمی‌شود.")
    if len("\n".join(current)) > MAX_MESSAGE_LENGTH:
        footer = current.pop()
        messages.append("\n".join(current))
        messages.append("\n".join([
            "گزارش اسکن Stage 1B | LRT-15m (پایان)",
            f"داشبورد: {dashboard}",
            footer,
        ]))
    else:
        messages.append("\n".join(current))
    return messages


def validate_telegram_config(
    token: str,
    chat_id: str,
    expected_channel_title: str,
) -> tuple[str, str, str]:
    token = token.strip()
    chat_id = chat_id.strip()
    expected_title = expected_channel_title.strip()
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise ValueError("TELEGRAM_TOKEN_INVALID_OR_MISSING")
    if not re.fullmatch(r"-100[0-9]+", chat_id):
        raise ValueError("TELEGRAM_CHAT_ID_INVALID_OR_MISSING")
    if not expected_title:
        raise ValueError("TELEGRAM_EXPECTED_CHANNEL_TITLE_MISSING")
    return token, chat_id, expected_title


def verify_telegram_destination() -> None:
    import sys
    package_root = str(Path(__file__).resolve().parents[1])
    if package_root not in sys.path:
        sys.path.insert(0, package_root)
    from telegram_bot import verify_telegram_connection
    if not verify_telegram_connection():
        raise RuntimeError("TELEGRAM_DESTINATION_PREFLIGHT_FAILED")


def send_message(token: str, chat_id: str, message: str) -> None:
    token, chat_id, _ = validate_telegram_config(
        token, chat_id, os.environ.get("TELEGRAM_EXPECTED_CHANNEL_TITLE", "")
    )
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
    message_result = result.get("result")
    if not isinstance(message_result, dict):
        raise RuntimeError("TELEGRAM_MESSAGE_RESULT_INVALID")
    message_id = message_result.get("message_id")
    chat = message_result.get("chat")
    if type(message_id) is not int or not isinstance(chat, dict):
        raise RuntimeError("TELEGRAM_MESSAGE_RESULT_INVALID")
    configured_chat = chat_id.strip()
    if configured_chat.startswith("@"):
        returned_username = str(chat.get("username") or "").lower()
        if returned_username != configured_chat[1:].lower():
            raise RuntimeError("TELEGRAM_DESTINATION_MISMATCH")
    elif str(chat.get("id")) != configured_chat:
        raise RuntimeError("TELEGRAM_DESTINATION_MISMATCH")
    if chat.get("type") not in {"private", "group", "supergroup", "channel"}:
        raise RuntimeError("TELEGRAM_CHAT_TYPE_INVALID")
    print(f"TELEGRAM_DELIVERY=SUCCESS message_id={message_id} chat_id={chat.get('id')}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verify-destination-only", action="store_true")
    args = parser.parse_args()

    if args.verify_destination_only:
        token, chat_id, _ = validate_telegram_config(
            os.environ.get("TELEGRAM_TOKEN", ""),
            os.environ.get("TELEGRAM_CHAT_ID", ""),
            os.environ.get("TELEGRAM_EXPECTED_CHANNEL_TITLE", ""),
        )
        verify_telegram_destination()
        print("TELEGRAM_DESTINATION=VERIFIED")
        return 0

    if args.report is None or args.universe is None:
        parser.error("--report and --universe are required unless --verify-destination-only is used")

    payload = validate_report(args.report, args.universe)
    dashboard_url = validate_dashboard_url(os.environ.get("DASHBOARD_URL", ""))
    messages = build_messages(payload, dashboard_url)
    # اعتبارسنجی محلی باید مستقل از Secret و شبکهٔ تلگرام باشد.
    if args.validate_only:
        print(f"REPORT_VALIDATION=PASS messages={len(messages)}")
        return 0
    token, chat_id, _ = validate_telegram_config(
        os.environ.get("TELEGRAM_TOKEN", ""),
        os.environ.get("TELEGRAM_CHAT_ID", ""),
        os.environ.get("TELEGRAM_EXPECTED_CHANNEL_TITLE", ""),
    )
    verify_telegram_destination()
    for message in messages:
        send_message(token, chat_id, message)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"TELEGRAM_DELIVERY=FAILED reason={type(exc).__name__}:{str(exc)[:160]}")
        raise SystemExit(1)
