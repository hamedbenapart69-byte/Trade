"""بازسازی ثانویهٔ کندل‌های FILUSDT از معاملات آرشیوی؛ بدون ذخیرهٔ دادهٔ خام."""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from signal_autopilot.modules.cryptohftdata_provider import (
    CryptoHFTDataProvider,
    ProviderDataUnavailable,
    ProviderRateLimited,
)

INTERVAL_MS = 15 * 60 * 1000
HOUR_MS = 60 * 60 * 1000
SYMBOL = "FILUSDT"
EXCHANGE_ID = "binance_futures"


def _load_gap_audit_module():
    path = Path(__file__).with_name("inspect_stage1b_gaps.py")
    spec = importlib.util.spec_from_file_location("inspect_stage1b_gaps", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("GAP_AUDIT_MODULE_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _decimal(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _utc_hour(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp((timestamp_ms // HOUR_MS) * 3600, timezone.utc)


def _hour_starts_for_segments(segments: list[dict[str, int]]) -> list[datetime]:
    hours: set[datetime] = set()
    for segment in segments:
        start_ms = segment["start_ms"]
        end_ms = segment["end_exclusive_ms"]
        first = _utc_hour(start_ms) - timedelta(hours=2)
        last = _utc_hour(end_ms - 1) + timedelta(hours=2)
        cursor = first
        while cursor <= last:
            hours.add(cursor)
            cursor += timedelta(hours=1)
    return sorted(hours)


def aggregate_trade_rows(rows: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    """تجمیع معاملات معتبر به OHLCV پانزده‌دقیقه‌ای؛ NA فقط برای کنترل ID می‌ماند."""
    ordered = sorted(
        rows,
        key=lambda row: (
            int(row["trade_time"]),
            int(row["trade_id"]),
        ),
    )
    buckets: dict[int, list[tuple[int, int, Decimal, Decimal]]] = defaultdict(list)
    na_rows = 0
    invalid_rows = 0
    invalid_timestamp_or_id_rows = 0
    invalid_event_time_rows = 0
    event_time_mismatch_rows = 0
    invalid_price_rows = 0
    nonpositive_price_rows = 0
    invalid_quantity_rows = 0
    nonpositive_quantity_rows = 0

    for row in ordered:
        try:
            trade_time = int(row["trade_time"])
            trade_id = int(row["trade_id"])
            event_time = int(row["event_time"])
        except (TypeError, ValueError, KeyError):
            invalid_rows += 1
            invalid_timestamp_or_id_rows += 1
            continue
        if event_time != trade_time:
            event_time_mismatch_rows += 1
        if str(row.get("order_type", "")).upper() == "NA":
            na_rows += 1
            continue

        price = _decimal(row.get("price"))
        quantity = _decimal(row.get("quantity"))
        row_invalid = False
        if price is None:
            invalid_price_rows += 1
            row_invalid = True
        elif price <= 0:
            nonpositive_price_rows += 1
            row_invalid = True
        if quantity is None:
            invalid_quantity_rows += 1
            row_invalid = True
        elif quantity <= 0:
            nonpositive_quantity_rows += 1
            row_invalid = True
        if row_invalid:
            invalid_rows += 1
            continue

        bucket = (trade_time // INTERVAL_MS) * INTERVAL_MS
        buckets[bucket].append((trade_time, trade_id, price, quantity))

    candles: dict[int, dict[str, Any]] = {}
    for open_time, trades in buckets.items():
        trades.sort(key=lambda item: (item[0], item[1]))
        prices = [item[2] for item in trades]
        candles[open_time] = {
            "open_time": open_time,
            "open": str(prices[0]),
            "high": str(max(prices)),
            "low": str(min(prices)),
            "close": str(prices[-1]),
            "volume": str(sum((item[3] for item in trades), Decimal("0"))),
            "trade_count": len(trades),
        }
    return candles, {
        "na_order_type_rows": na_rows,
        "invalid_or_nonpositive_rows": invalid_rows,
        "invalid_timestamp_or_id_rows": invalid_timestamp_or_id_rows,
        "invalid_event_time_rows": invalid_event_time_rows,
        "event_time_mismatch_rows": event_time_mismatch_rows,
        "invalid_price_rows": invalid_price_rows,
        "nonpositive_price_rows": nonpositive_price_rows,
        "invalid_quantity_rows": invalid_quantity_rows,
        "nonpositive_quantity_rows": nonpositive_quantity_rows,
        "valid_trade_rows": sum(item["trade_count"] for item in candles.values()),
        "candles_built": len(candles),
    }


def trade_id_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[tuple[int, int]] = []
    for row in rows:
        try:
            pairs.append((int(row["trade_id"]), int(row["trade_time"])))
        except (TypeError, ValueError, KeyError):
            continue
    # یک شناسه باید یک رخداد داشته باشد؛ duplicateها جداگانه گزارش می‌شوند.
    by_id: dict[int, int] = {}
    for trade_id, trade_time in sorted(pairs, key=lambda item: (item[0], item[1])):
        by_id.setdefault(trade_id, trade_time)
    unique_ids = sorted(by_id)
    gaps = []
    for left, right in zip(unique_ids, unique_ids[1:]):
        missing = right - left - 1
        if missing > 0:
            gaps.append({
                "after_trade_time_utc": datetime.fromtimestamp(
                    by_id[left] / 1000, timezone.utc
                ).isoformat(),
                "before_trade_time_utc": datetime.fromtimestamp(
                    by_id[right] / 1000, timezone.utc
                ).isoformat(),
                "missing_trade_ids_estimate": missing,
                "elapsed_seconds": round((by_id[right] - by_id[left]) / 1000, 3),
            })
    return {
        "trade_id_rows": len(pairs),
        "unique_trade_ids": len(unique_ids),
        "duplicate_trade_ids": len(pairs) - len(unique_ids),
        "trade_id_gap_intervals": len(gaps),
        "missing_trade_ids_estimate": sum(item["missing_trade_ids_estimate"] for item in gaps),
        "trade_id_gap_time_ranges": gaps,
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((percentile / 100) * (len(ordered) - 1))))
    return round(ordered[index], 8)


def _reference_rows(storage_dir: Path, start_ms: int, end_ms: int) -> dict[int, dict[str, Any]]:
    root = storage_dir
    paths = [root / "base" / f"{SYMBOL}_15m.parquet"]
    paths.extend(sorted((root / "live_tail").glob(f"**/{SYMBOL}_15m.parquet")))
    result: dict[int, dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        table = pq.read_table(path, columns=["open_time", "open", "high", "low", "close", "volume"])
        for row in table.to_pylist():
            timestamp = int(row["open_time"])
            if start_ms <= timestamp < end_ms:
                result[timestamp] = row
    return result


def _compare_overlap(
    candles: dict[int, dict[str, Any]],
    references: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    differences: list[float] = []
    matched = 0
    for timestamp, candle in candles.items():
        reference = references.get(timestamp)
        if not reference:
            continue
        matched += 1
        for field in ("open", "high", "low", "close"):
            actual = _decimal(candle[field])
            expected = _decimal(reference.get(field))
            if actual is None or expected is None or expected == 0:
                continue
            differences.append(float(abs(actual - expected) / abs(expected) * Decimal("100")))
    return {
        "matched_reference_candles": matched,
        "ohlc_point_comparisons": len(differences),
        "absolute_relative_difference_pct": {
            "median": _percentile(differences, 50),
            "p95": _percentile(differences, 95),
            "max": round(max(differences), 8) if differences else None,
        },
        "interpretation": (
            "Cross-venue comparison only; no acceptance threshold is assumed and these bars are not "
            "merged into the canonical dataset."
        ),
    }


def run_reconstruction(
    storage_dir: Path,
    report_path: Path,
    output_path: Path,
    provider: Any | None = None,
) -> dict[str, Any]:
    gap_module = _load_gap_audit_module()
    audit = gap_module.inspect_gap(storage_dir, report_path, SYMBOL)
    gaps = audit["compute_input_gap_ranges"]
    segments = [
        {
            "start_ms": int(item["first_open_ms"]),
            "end_exclusive_ms": int(item["last_open_ms"]) + INTERVAL_MS,
        }
        for item in gaps
    ]
    if not segments:
        raise ValueError("NO_COMPUTE_INPUT_GAPS")
    hours = _hour_starts_for_segments(segments)
    if len(hours) > 60:
        raise ValueError(f"ANONYMOUS_DOWNLOAD_BUDGET_EXCEEDED:{len(hours)}")

    client = provider or CryptoHFTDataProvider(
        api_key=None,
        timeout_seconds=30,
        max_file_bytes=32 * 1024 * 1024,
        min_request_interval_seconds=1.05,
    )
    symbols = set(client.discover_symbols(EXCHANGE_ID, "trades"))
    if SYMBOL not in symbols:
        raise ProviderDataUnavailable("FILUSDT_NOT_IN_PROVIDER_TRADE_UNIVERSE")

    rows_by_segment: list[list[dict[str, Any]]] = [[] for _ in segments]
    downloaded_hours: list[str] = []
    unavailable_hours: list[dict[str, str]] = []
    file_row_counts: dict[str, int] = {}
    for hour in hours:
        try:
            snapshot = client.download_hourly_parquet(EXCHANGE_ID, SYMBOL, "trades", hour)
        except ProviderRateLimited:
            time.sleep(5)
            try:
                snapshot = client.download_hourly_parquet(EXCHANGE_ID, SYMBOL, "trades", hour)
            except Exception as exc:
                unavailable_hours.append({"hour": hour.isoformat(), "reason": type(exc).__name__})
                continue
        except ProviderDataUnavailable:
            unavailable_hours.append({"hour": hour.isoformat(), "reason": "FILE_NOT_AVAILABLE"})
            continue
        except Exception as exc:
            unavailable_hours.append({"hour": hour.isoformat(), "reason": type(exc).__name__})
            continue

        downloaded_hours.append(hour.isoformat())
        file_row_counts[hour.isoformat()] = snapshot.row_count
        table = snapshot.table
        for row in table.to_pylist():
            try:
                trade_time = int(row["trade_time"])
            except (TypeError, ValueError, KeyError):
                continue
            for index, segment in enumerate(segments):
                # کمی حاشیه برای معامله‌ای که در ساعت بعد دریافت شده باشد.
                if segment["start_ms"] - 2 * HOUR_MS <= trade_time < segment["end_exclusive_ms"] + 2 * HOUR_MS:
                    rows_by_segment[index].append(row)
                    break

    all_candles: dict[int, dict[str, Any]] = {}
    segment_reports: list[dict[str, Any]] = []
    aggregate_totals = Counter()
    expected_timestamps: set[int] = set()
    for segment, rows in zip(segments, rows_by_segment):
        expected = list(range(segment["start_ms"], segment["end_exclusive_ms"], INTERVAL_MS))
        expected_timestamps.update(expected)
        candles, aggregate_quality = aggregate_trade_rows(rows)
        quality = trade_id_quality(rows)
        all_candles.update(candles)
        aggregate_totals.update(aggregate_quality)
        missing = [timestamp for timestamp in expected if timestamp not in candles]
        segment_reports.append({
            "first_open_utc": datetime.fromtimestamp(segment["start_ms"] / 1000, timezone.utc).isoformat(),
            "last_open_utc": datetime.fromtimestamp((segment["end_exclusive_ms"] - INTERVAL_MS) / 1000, timezone.utc).isoformat(),
            "expected_candles": len(expected),
            "reconstructed_candles": sum(1 for ts in expected if ts in candles),
            "missing_candles": len(missing),
            "missing_candle_ranges": gap_module.group_missing_timestamps(missing),
            "trade_quality": quality,
            "aggregation_quality": aggregate_quality,
        })

    # کیفیت شناسه در هر بازه جدا سنجیده می‌شود؛ فاصلهٔ دو شکاف به‌اشتباه gap محسوب نمی‌شود.
    sequence_gap_intervals = sum(item["trade_quality"]["trade_id_gap_intervals"] for item in segment_reports)
    missing_trade_ids = sum(item["trade_quality"]["missing_trade_ids_estimate"] for item in segment_reports)
    duplicate_trade_ids = sum(item["trade_quality"]["duplicate_trade_ids"] for item in segment_reports)

    overlap_ranges: list[tuple[int, int]] = []
    for segment in segments:
        overlap_ranges.append((segment["start_ms"] - 2 * HOUR_MS, segment["start_ms"]))
        overlap_ranges.append((segment["end_exclusive_ms"], segment["end_exclusive_ms"] + 2 * HOUR_MS))
    ref_rows: dict[int, dict[str, Any]] = {}
    for start, end in overlap_ranges:
        ref_rows.update(_reference_rows(storage_dir, start, end))
    overlap = _compare_overlap(all_candles, ref_rows)

    expected_count = len(expected_timestamps)
    reconstructed_count = sum(1 for timestamp in expected_timestamps if timestamp in all_candles)
    complete_candle_coverage = reconstructed_count == expected_count
    sequence_complete = sequence_gap_intervals == 0 and duplicate_trade_ids == 0
    timestamp_semantics_valid = aggregate_totals["event_time_mismatch_rows"] == 0
    invalid_rows_absent = aggregate_totals["invalid_or_nonpositive_rows"] == 0
    files_complete = not unavailable_hours
    status = (
        "COMPLETE_SECONDARY_SOURCE"
        if complete_candle_coverage and sequence_complete and timestamp_semantics_valid and invalid_rows_absent and files_complete
        else "DEGRADED_SECONDARY_SOURCE"
    )
    result = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": SYMBOL,
        "interval": "15m",
        "provider": "CryptoHFTData",
        "provider_exchange_id": EXCHANGE_ID,
        "access_mode": "ANONYMOUS_PUBLIC_REST_NO_API_KEY",
        "download_budget": {
            "requested_hour_files": len(hours),
            "downloaded_hour_files": len(downloaded_hours),
            "unavailable_hour_files": len(unavailable_hours),
            "anonymous_limit_documented_per_60_seconds": 60,
            "client_minimum_interval_seconds": 1.05,
        },
        "hour_file_row_counts": file_row_counts,
        "unavailable_hours": unavailable_hours,
        "segments": segment_reports,
        "totals": {
            "expected_missing_candles": expected_count,
            "reconstructed_candles": reconstructed_count,
            "missing_candles": expected_count - reconstructed_count,
            "trade_id_gap_intervals": sequence_gap_intervals,
            "missing_trade_ids_estimate": missing_trade_ids,
            "duplicate_trade_ids": duplicate_trade_ids,
            "na_order_type_rows": aggregate_totals["na_order_type_rows"],
            "invalid_or_nonpositive_rows": aggregate_totals["invalid_or_nonpositive_rows"],
            "event_time_mismatch_rows": aggregate_totals["event_time_mismatch_rows"],
            "valid_trade_rows": aggregate_totals["valid_trade_rows"],
        },
        "overlap_validation": overlap,
        "status": status,
        "canonical_dataset_mutated": False,
        "canonical_promotion": "NOT_AUTHORIZED_BY_THIS_RESEARCH_JOB",
        "raw_provider_files_persisted": False,
        "raw_trade_rows_emitted": False,
        "raw_prices_emitted": False,
        "trade_ids_emitted": False,
        "data_source_semantics": (
            "Historical Binance USD-M public trades collected and distributed by CryptoHFTData. "
            "This is not a Binance account connection or a direct exchange API call. "
            "The result remains a separate venue-specific data stream."
        ),
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("filusdt-trade-reconstruction.json"))
    args = parser.parse_args()
    result = run_reconstruction(args.storage_dir, args.report, args.output)
    print(json.dumps({
        "status": result["status"],
        "requested_hour_files": result["download_budget"]["requested_hour_files"],
        "downloaded_hour_files": result["download_budget"]["downloaded_hour_files"],
        "unavailable_hour_files": result["download_budget"]["unavailable_hour_files"],
        "totals": result["totals"],
        "overlap_validation": result["overlap_validation"],
        "report": str(args.output),
    }, ensure_ascii=False))
    return 0 if result["status"] == "COMPLETE_SECONDARY_SOURCE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
