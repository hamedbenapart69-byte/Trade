"""اعتبارسنجی آرشیو رسمی کندل‌های FILUSDT؛ فقط گزارش کیفیت، بدون انتشار داده خام."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_autopilot.scripts.inspect_stage1b_gaps import inspect_gap

BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"
SYMBOL = "FILUSDT"
INTERVAL = "15m"
FIELDS = ("open", "high", "low", "close", "volume")


def _get(url: str, limit: int = 80_000_000) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Trade-Internal-Research/1.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if int(response.status) != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("ARCHIVE_EXCEEDS_SIZE_LIMIT")
    return data


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values.sort()
    return round(values[min(len(values) - 1, int((len(values) - 1) * p / 100))], 10)


def _parse_checksum(body: bytes) -> str:
    match = re.search(rb"\b([a-fA-F0-9]{64})\b", body)
    if not match:
        raise RuntimeError("CHECKSUM_FORMAT_INVALID")
    return match.group(1).decode("ascii").lower()


def _daily_klines(date: str) -> tuple[dict[int, dict[str, str]], dict[str, Any]]:
    filename = f"{SYMBOL}-{INTERVAL}-{date}.zip"
    directory = f"{BASE_URL}/{SYMBOL}/{INTERVAL}"
    archive = _get(f"{directory}/{filename}")
    checksum_body = _get(f"{directory}/{filename}.CHECKSUM", limit=4096)
    expected_sha = _parse_checksum(checksum_body)
    actual_sha = hashlib.sha256(archive).hexdigest()
    if actual_sha != expected_sha:
        raise RuntimeError(f"CHECKSUM_MISMATCH:{date}")

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"UNEXPECTED_CSV_MEMBERS:{date}:{len(names)}")
        with zf.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            rows: dict[int, dict[str, str]] = {}
            for row in csv.reader(text):
                if len(row) < 11:
                    continue
                timestamp = int(row[0])
                rows[timestamp] = {
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                    "number_of_trades": row[8],
                    "taker_buy_base_volume": row[9],
                    "taker_buy_quote_volume": row[10],
                }
    return rows, {
        "date": date,
        "archive_sha256": actual_sha,
        "checksum_verified": True,
        "daily_rows": len(rows),
        "archive_bytes": len(archive),
    }


def validate_archive(storage_dir: Path, report_path: Path, output_path: Path) -> dict[str, Any]:
    audit = inspect_gap(storage_dir, report_path, SYMBOL)
    ranges = audit["compute_input_gap_ranges"]
    expected: set[int] = set()
    for item in ranges:
        first = int(item["first_open_ms"])
        last = int(item["last_open_ms"])
        expected.update(range(first, last + 15 * 60 * 1000, 15 * 60 * 1000))
    if len(expected) != 200:
        raise RuntimeError(f"EXPECTED_GAP_COUNT_CHANGED:{len(expected)}")

    dates = sorted({datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d") for ts in expected})
    all_rows: dict[int, dict[str, str]] = {}
    daily_reports = []
    for date in dates:
        rows, daily = _daily_klines(date)
        all_rows.update(rows)
        daily_reports.append(daily)

    missing = sorted(expected.difference(all_rows))
    comparisons: dict[str, list[float]] = {field: [] for field in FIELDS}
    exact_candles = 0
    for timestamp in sorted(expected.intersection(all_rows)):
        row = all_rows[timestamp]
        matched = True
        for field in FIELDS:
            value = _decimal(row[field])
            if value is None:
                matched = False
                continue
            # OHLCV is emitted only as summary errors; never print source values.
        if matched:
            exact_candles += 1

    result = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "source": "BINANCE_VISION_DAILY_UM_KLINES",
        "access_mode": "PUBLIC_ARCHIVE_NO_ACCOUNT_NO_API_KEY",
        "scope": "EXACT_COMPUTE_INPUT_GAPS_ONLY",
        "expected_gap_candles": len(expected),
        "archive_dates": daily_reports,
        "available_gap_candles": len(expected) - len(missing),
        "missing_gap_candles": len(missing),
        "missing_gap_ranges": [
            {"first_open_utc": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat()}
            for ts in missing[:20]
        ],
        "all_five_fields_parseable": exact_candles,
        "ohlcv_values_emitted": False,
        "raw_archive_persisted": False,
        "canonical_dataset_mutated": False,
        "redistribution_license": "CC BY-NC-SA 4.0; non-commercial research only",
        "production_signal_distribution_approved": False,
        "status": "ARCHIVE_COVERAGE_VERIFIED_RESEARCH_ONLY" if not missing else "ARCHIVE_COVERAGE_INCOMPLETE",
        "limitations": [
            "This is a venue-native Binance USD-M archive, not an independent multi-venue aggregator.",
            "Kline coverage validates OHLCV availability only; it does not recover missing trade-level order flow.",
            "The provider terms restrict use to non-commercial research and require share-alike attribution for redistributed derivatives.",
            "No values are merged into the canonical dataset by this research job.",
        ],
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("filusdt-binance-vision-audit.json"))
    args = parser.parse_args()
    result = validate_archive(args.storage_dir, args.report, args.output)
    print(json.dumps({
        "status": result["status"],
        "expected_gap_candles": result["expected_gap_candles"],
        "available_gap_candles": result["available_gap_candles"],
        "missing_gap_candles": result["missing_gap_candles"],
        "dates": result["archive_dates"],
        "report": str(args.output),
    }, ensure_ascii=False))
    return 0 if result["status"] == "ARCHIVE_COVERAGE_VERIFIED_RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
