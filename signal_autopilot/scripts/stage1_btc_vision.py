#!/usr/bin/env python3
"""Stage 1 L1: دریافت آرشیو روزانهٔ BTCUSDT و ساخت قرارداد JSON نسخه‌دار."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

INTERVAL_MS = 3_600_000
MAX_STALENESS_MS = 26 * INTERVAL_MS
SYMBOL = "BTCUSDT"
BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"
SCAN_ID = "scan-" + hashlib.sha256(b"cfss-stage1-btc-no-signal-v1").hexdigest()


class Stage1DataError(RuntimeError):
    """خطای قطعی دریافت یا اعتبارسنجی دادهٔ Stage 1."""


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fetch_bytes(url: str, timeout: int = 45) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "CFSS-Stage1/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise Stage1DataError(f"HTTP_STATUS_{response.status}:{url}")
        return response.read()


def parse_checksum(payload: bytes) -> str:
    parts = payload.decode("ascii", errors="strict").strip().split()
    if not parts or len(parts[0]) != 64:
        raise Stage1DataError("CHECKSUM_FORMAT_INVALID")
    digest = parts[0].lower()
    if any(ch not in "0123456789abcdef" for ch in digest):
        raise Stage1DataError("CHECKSUM_HEX_INVALID")
    return digest


def parse_daily_zip(payload: bytes, now_ms: int) -> list[dict[str, Any]]:
    """کندل‌های کامل را می‌خواند؛ دادهٔ ناقص یا timestamp نامعتبر رد می‌شود."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise Stage1DataError("ARCHIVE_CSV_COUNT_INVALID")
            with archive.open(csv_names[0]) as stream:
                rows = csv.reader(io.TextIOWrapper(stream, encoding="utf-8"))
                parsed: list[dict[str, Any]] = []
                for row in rows:
                    if not row or not row[0].isdigit():
                        continue
                    if len(row) < 11:
                        raise Stage1DataError("KLINE_ROW_TOO_SHORT")
                    open_ms = int(row[0])
                    close_ms = int(row[6])
                    values = [float(row[index]) for index in (1, 2, 3, 4, 5, 7, 9, 10)]
                    open_price, high, low, close, volume, quote_volume, taker_buy_base, taker_buy_quote = values
                    if open_ms % INTERVAL_MS:
                        raise Stage1DataError("KLINE_TIMESTAMP_ALIGNMENT_INVALID")
                    if close_ms < open_ms or close_ms >= open_ms + INTERVAL_MS:
                        raise Stage1DataError("KLINE_CLOSE_TIMESTAMP_INVALID")
                    if close_ms >= now_ms:
                        continue
                    if min(open_price, high, low, close) <= 0 or min(volume, quote_volume, taker_buy_base, taker_buy_quote) < 0:
                        raise Stage1DataError("KLINE_VALUE_OUT_OF_RANGE")
                    if high < max(open_price, low, close) or low > min(open_price, high, close):
                        raise Stage1DataError("KLINE_OHLC_RELATION_INVALID")
                    parsed.append({
                        "timestamp_ms": open_ms,
                        "close_time_ms": close_ms,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "volume": volume,
                        "volume_quote": quote_volume,
                        "taker_buy_base": taker_buy_base,
                        "taker_buy_quote": taker_buy_quote,
                    })
    except zipfile.BadZipFile as exc:
        raise Stage1DataError("DAILY_ARCHIVE_NOT_A_VALID_ZIP") from exc

    parsed.sort(key=lambda item: item["timestamp_ms"])
    if len({row["timestamp_ms"] for row in parsed}) != len(parsed):
        raise Stage1DataError("DUPLICATE_CANDLE_TIMESTAMP")
    return parsed


def select_latest_24(rows: list[dict[str, Any]], now_ms: int) -> list[dict[str, Any]]:
    closed = [row for row in rows if int(row["close_time_ms"]) < now_ms]
    selected = closed[-24:]
    if len(selected) != 24:
        raise Stage1DataError(f"EXPECTED_24_CLOSED_CANDLES_GOT_{len(selected)}")
    for left, right in zip(selected, selected[1:]):
        if int(right["timestamp_ms"]) - int(left["timestamp_ms"]) != INTERVAL_MS:
            raise Stage1DataError("LATEST_24_CANDLES_HAVE_GAP")
    latest_close = int(selected[-1]["close_time_ms"])
    staleness_ms = now_ms - latest_close
    if staleness_ms < 0:
        raise Stage1DataError("LATEST_CANDLE_CLOSE_IS_IN_FUTURE")
    if staleness_ms > MAX_STALENESS_MS:
        raise Stage1DataError(f"ARCHIVE_STALE:{staleness_ms}")
    return selected


def build_l1_contract(
    candles: list[dict[str, Any]],
    now_ms: int,
    archive_url: str,
    checksum_url: str,
    archive_sha256: str,
    checksum_file_sha256: str,
    archive_bytes: int,
    archive_filename: str,
    run_id: str,
) -> dict[str, Any]:
    latest_close = int(candles[-1]["close_time_ms"])
    return {
        "schema_version": "1.0.0",
        "artifact_type": "cfss_stage1_btc_l1_v1",
        "run_id": run_id,
        "scan_id": SCAN_ID,
        "acquired_at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "window": {
            "timeframe": "1h",
            "start_ms": int(candles[0]["timestamp_ms"]),
            "end_ms": latest_close,
            "closed_candles": len(candles),
        },
        "provider": {
            "primary_provider_id": "binance_vision",
            "data_class": "DAILY_ARCHIVE_DELAYED",
            "realtime": False,
            "fallback_used": False,
        },
        "provenance": {
            "source_files": [{
                "filename": archive_filename,
                "archive_url": archive_url,
                "checksum_url": checksum_url,
                "sha256": archive_sha256,
                "checksum_file_sha256": checksum_file_sha256,
                "bytes": archive_bytes,
                "row_count": len(candles),
                "first_timestamp_ms": int(candles[0]["timestamp_ms"]),
                "last_timestamp_ms": int(candles[-1]["timestamp_ms"]),
            }],
            "sha256_verified": True,
        },
        "freshness": {
            "status": "DAILY_ARCHIVE_DELAYED",
            "latest_candle_close_ms": latest_close,
            "staleness_ms": now_ms - latest_close,
            "maximum_staleness_ms": MAX_STALENESS_MS,
        },
        "instruments": [{
            "instrument_id": SYMBOL,
            "unified_symbol": "BTC/USDT:USDT",
            "base": "BTC",
            "quote": "USDT",
            "settle": "USDT",
            "contract_type": "linear_perpetual",
            "provider_id": "binance_vision",
            "timeframe": "1h",
            "candles": [{
                **row,
                "price_currency": "USDT",
                "volume_unit": "base_asset",
                "volume_base_currency": "BTC",
                "volume_quote_currency": "USDT",
                "closed": True,
                "retrieved_at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
            } for row in candles],
            "funding": [],
            "open_interest": [],
            "availability": {
                "ohlcv": "AVAILABLE",
                "funding": "UNAVAILABLE",
                "open_interest": "UNAVAILABLE",
            },
        }],
        "trading_decision": "NOT_IN_SCOPE",
        "signal_generation_enabled": False,
    }


def run(output_dir: Path, now_ms: int | None = None) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000) if now_ms is None else int(now_ms)
    archive_day = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date() - timedelta(days=1)
    filename = f"{SYMBOL}-1h-{archive_day:%Y-%m-%d}.zip"
    archive_url = f"{BASE_URL}/{SYMBOL}/1h/{filename}"
    checksum_url = archive_url + ".CHECKSUM"

    # checksum و ZIP از یک منبع عمومی دریافت می‌شوند؛ hash در C++ مستقل بازبینی می‌شود.
    checksum_payload = fetch_bytes(checksum_url)
    expected_sha256 = parse_checksum(checksum_payload)
    archive_payload = fetch_bytes(archive_url)
    actual_sha256 = sha256_hex(archive_payload)
    if actual_sha256 != expected_sha256:
        raise Stage1DataError("BINANCE_VISION_SHA256_MISMATCH")

    rows = parse_daily_zip(archive_payload, now_ms)
    candles = select_latest_24(rows, now_ms)

    source_dir = output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / filename).write_bytes(archive_payload)
    contract = build_l1_contract(
        candles, now_ms, archive_url, checksum_url, actual_sha256,
        sha256_hex(checksum_payload), len(archive_payload), filename,
        os.getenv("GITHUB_RUN_ID", "local-stage1-run"),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "l1-btcusdt.v1.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "L1_PASS",
        "provider": "binance_vision",
        "data_class": "DAILY_ARCHIVE_DELAYED",
        "symbol": SYMBOL,
        "closed_candles": len(candles),
        "latest_close_ms": candles[-1]["close_time_ms"],
        "staleness_ms": contract["freshness"]["staleness_ms"],
        "archive_sha256": actual_sha256,
        "archive_bytes": len(archive_payload),
    }, ensure_ascii=False))
    return contract


def main() -> int:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts")
    try:
        run(output_dir)
    except (Stage1DataError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"STAGE1_L1_FAIL:{type(exc).__name__}:{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
