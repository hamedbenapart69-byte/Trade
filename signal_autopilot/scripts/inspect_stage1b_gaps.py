"""ممیزی شکاف‌های FILUSDT فقط از روی timestamp؛ بدون خواندن یا خروجی‌دادن قیمت‌ها."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

INTERVAL_MS = 15 * 60 * 1000
CRYPTOHFTDATA_ARCHIVE_START_UTC = "2025-06-28T00:00:00+00:00"


def group_missing_timestamps(missing: list[int], interval_ms: int = INTERVAL_MS) -> list[dict[str, Any]]:
    """Timestampهای گمشده را به بازه‌های پیوسته تبدیل می‌کند."""
    if not missing:
        return []
    ordered = sorted(set(int(value) for value in missing))
    groups: list[list[int]] = [[ordered[0]]]
    for value in ordered[1:]:
        if value - groups[-1][-1] == interval_ms:
            groups[-1].append(value)
        else:
            groups.append([value])
    result = []
    for group in groups:
        result.append({
            "first_open_ms": group[0],
            "last_open_ms": group[-1],
            "first_open_utc": datetime.fromtimestamp(group[0] / 1000, timezone.utc).isoformat(),
            "last_open_utc": datetime.fromtimestamp(group[-1] / 1000, timezone.utc).isoformat(),
            "bars": len(group),
            "duration_minutes": len(group) * interval_ms // 60_000,
            "within_cryptohftdata_archive": (
                group[0] >= int(datetime.fromisoformat(CRYPTOHFTDATA_ARCHIVE_START_UTC).timestamp() * 1000)
            ),
        })
    return result


def _read_open_times(path: Path) -> list[int]:
    if not path.exists():
        return []
    # فقط ستون زمان خوانده می‌شود؛ OHLCV خام وارد گزارش ممیزی نمی‌شود.
    table = pq.read_table(path, columns=["open_time"])
    return [int(value) for value in table.column("open_time").to_pylist() if value is not None]


def inspect_gap(storage_dir: Path, report_path: Path, symbol: str = "FILUSDT") -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    symbol_rows = report.get("symbols")
    if not isinstance(symbol_rows, list):
        raise ValueError("DATA_REPORT_SYMBOLS_INVALID")
    item = next((row for row in symbol_rows if row.get("symbol") == symbol), None)
    if not isinstance(item, dict):
        raise ValueError(f"SYMBOL_NOT_FOUND_IN_DATA_REPORT:{symbol}")

    first_ms = int(item["first_open_ms"])
    last_ms = int(item["last_open_ms"])
    if first_ms % INTERVAL_MS or last_ms % INTERVAL_MS or last_ms < first_ms:
        raise ValueError("DATA_REPORT_TIMESTAMP_RANGE_INVALID")

    base_path = storage_dir / "base" / f"{symbol}_15m.parquet"
    tail_paths = sorted((storage_dir / "live_tail").glob(f"**/{symbol}_15m.parquet"))
    base_times = _read_open_times(base_path)
    tail_times: list[int] = []
    for path in tail_paths:
        tail_times.extend(_read_open_times(path))

    combined = base_times + tail_times
    unique_times = sorted(set(combined))
    expected = list(range(first_ms, last_ms + INTERVAL_MS, INTERVAL_MS))
    actual_set = set(unique_times)
    missing = [timestamp for timestamp in expected if timestamp not in actual_set]
    outside_window = [timestamp for timestamp in unique_times if timestamp < first_ms or timestamp > last_ms]
    duplicates = len(combined) - len(actual_set)
    gaps = group_missing_timestamps(missing)

    consistency = {
        "report_rows_matches_unique_rows": len(unique_times) == int(item.get("rows", -1)),
        "report_tail_rows_matches_partition_rows": len(tail_times) == int(item.get("tail_rows", -1)),
        "report_gap_count_matches_gap_ranges": len(gaps) == int(item.get("gap_count", -1)),
        "report_missing_count_matches_expected_minus_actual": (
            len(expected) - len(unique_times) == len(missing)
        ),
    }
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "interval": "15m",
        "data_report_generated_at_utc": report.get("generated_at_utc"),
        "market_data_branch_snapshot": "c34b037e3534192fd95e65a10bc67acba9821f8b",
        "expected_window": {
            "first_open_ms": first_ms,
            "last_open_ms": last_ms,
            "first_open_utc": datetime.fromtimestamp(first_ms / 1000, timezone.utc).isoformat(),
            "last_open_utc": datetime.fromtimestamp(last_ms / 1000, timezone.utc).isoformat(),
            "expected_bars": len(expected),
        },
        "storage_counts": {
            "base_rows": len(base_times),
            "tail_rows": len(tail_times),
            "combined_rows_including_duplicates": len(combined),
            "unique_rows": len(unique_times),
            "duplicate_timestamps": duplicates,
            "outside_window_timestamps": len(outside_window),
            "missing_bars": len(missing),
            "gap_ranges": len(gaps),
        },
        "data_report_claims": {
            "rows": item.get("rows"),
            "tail_rows": item.get("tail_rows"),
            "expected_rows": item.get("expected_rows"),
            "gap_count": item.get("gap_count"),
            "reason": item.get("reason"),
            "provider_status": item.get("provider_status"),
        },
        "consistency_checks": consistency,
        "gap_ranges": gaps,
        "archive_coverage_note": (
            "CryptoHFTData archive begins 2025-06-28. Gaps after this date are date-eligible for a probe, "
            "but provider symbol/file availability must be tested per hour."
        ),
        "raw_price_values_read": False,
        "raw_provider_data_downloaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--symbol", default="FILUSDT")
    parser.add_argument("--output", type=Path, default=Path("filusdt-gap-audit.json"))
    args = parser.parse_args()
    result = inspect_gap(args.storage_dir, args.report, args.symbol)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "symbol": result["symbol"],
        "missing_bars": result["storage_counts"]["missing_bars"],
        "gap_ranges": result["storage_counts"]["gap_ranges"],
        "consistency_checks": result["consistency_checks"],
        "report": str(args.output),
    }, ensure_ascii=False))
    return 0 if all(result["consistency_checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
