#!/usr/bin/env python3
"""Validate untrusted Stage 1b P0 artifacts before trusted persistence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pyarrow.parquet as pq

INTERVAL_MS = 15 * 60 * 1000
EXPECTED_ROWS = 730 * 24 * 4
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}USDT$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_manifest_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"UNSAFE_MANIFEST_PATH:{value}")
    if path.parts[0] == "base":
        valid = len(path.parts) == 2 and path.name.endswith("_15m.parquet")
    elif path.parts[0] == "live_tail":
        valid = len(path.parts) == 3 and path.name.endswith("_15m.parquet")
        if valid:
            datetime.strptime(path.parts[1], "%Y-%m-%d")
    else:
        valid = False
    if not valid:
        raise ValueError(f"UNEXPECTED_MANIFEST_PATH:{value}")
    return path


def validate_rows(rows: list[dict], symbol: str, kind: str, path: PurePosixPath) -> list[int]:
    required = ("open_time", "open", "high", "low", "close", "volume")
    timestamps: list[int] = []
    for index, row in enumerate(rows):
        if any(row.get(field) is None for field in required):
            raise ValueError(f"REQUIRED_FIELD_MISSING:{path}:row={index}")
        try:
            timestamp = int(row["open_time"])
            values = [float(row[field]) for field in ("open", "high", "low", "close", "volume")]
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"INVALID_OHLCV:{path}:row={index}") from exc
        if timestamp % INTERVAL_MS or not all(math.isfinite(value) for value in values):
            raise ValueError(f"INVALID_TIMESTAMP_OR_NONFINITE:{path}:row={index}")
        opn, high, low, close, volume = values
        if min(opn, high, low, close) <= 0 or volume < 0:
            raise ValueError(f"OHLCV_RANGE:{path}:row={index}")
        if high < max(opn, close, low) or low > min(opn, close, high):
            raise ValueError(f"OHLC_RELATION:{path}:row={index}")
        if kind == "LIVE_TAIL":
            day = datetime.fromtimestamp(timestamp / 1000, timezone.utc).strftime("%Y-%m-%d")
            if day != path.parts[1]:
                raise ValueError(f"TAIL_PARTITION_DATE_MISMATCH:{path}:row={index}")
        timestamps.append(timestamp)
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError(f"TIMESTAMP_ORDER_OR_DUPLICATE:{path}")
    return timestamps


def _parse_utc_ms(value: object, label: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{label}_MISSING_OR_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}_TIMEZONE_MISSING")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def validate_report_freshness(
    report: dict,
    symbols: list[str],
    timestamps_by_symbol: dict[str, set[int]],
    workflow_completed_at_ms: int,
    *,
    max_age_minutes: int = 30,
    expected_rows: int = EXPECTED_ROWS,
) -> None:
    """Recompute C10 data status from Parquet timestamps, not artifact claims."""
    if type(max_age_minutes) is not int or max_age_minutes <= 0:
        raise ValueError("DATA_REPORT_MAX_AGE_POLICY_INVALID")
    if type(expected_rows) is not int or expected_rows <= 0:
        raise ValueError("DATA_REPORT_EXPECTED_ROWS_POLICY_INVALID")
    completed_ms = int(workflow_completed_at_ms)
    generated_ms = _parse_utc_ms(report.get("generated_at_utc"), "DATA_REPORT_GENERATED_AT")
    report_age_minutes = (completed_ms - generated_ms) / 60_000
    if report_age_minutes < -5:
        raise ValueError("DATA_REPORT_TIMESTAMP_FROM_FUTURE")
    if report_age_minutes > max_age_minutes:
        raise ValueError("DATA_REPORT_TIMESTAMP_STALE")

    closed_end_ms = (completed_ms // INTERVAL_MS) * INTERVAL_MS
    window_start_ms = closed_end_ms - expected_rows * INTERVAL_MS
    expected_end_iso = datetime.fromtimestamp(
        closed_end_ms / 1000, timezone.utc
    ).isoformat()
    expected_start_date = datetime.fromtimestamp(
        window_start_ms / 1000, timezone.utc
    ).date().isoformat()
    if report.get("interval") != "15m":
        raise ValueError("DATA_REPORT_INTERVAL_INVALID")
    if report.get("start_date_utc") != expected_start_date:
        raise ValueError("DATA_REPORT_WINDOW_START_MISMATCH")
    if report.get("end_date_exclusive_utc") != expected_end_iso:
        raise ValueError("DATA_REPORT_WINDOW_END_MISMATCH")

    report_rows = report.get("symbols")
    if not isinstance(report_rows, list) or len(report_rows) != len(symbols):
        raise ValueError("DATA_REPORT_SYMBOL_LIST_INVALID")
    by_symbol = {
        row.get("symbol"): row for row in report_rows if isinstance(row, dict)
    }
    if len(by_symbol) != len(symbols) or set(by_symbol) != set(symbols):
        raise ValueError("DATA_REPORT_SYMBOL_SET_MISMATCH")

    complete_count = 0
    fresh_count = 0
    for symbol in symbols:
        actual = sorted(
            timestamp for timestamp in timestamps_by_symbol.get(symbol, set())
            if window_start_ms <= timestamp < closed_end_ms
        )
        rows_count = len(actual)
        continuity = (
            rows_count == expected_rows
            and all(
                right - left == INTERVAL_MS
                for left, right in zip(actual, actual[1:])
            )
        )
        last_open_ms = actual[-1] if actual else None
        first_open_ms = actual[0] if actual else None
        age_minutes = (
            round((completed_ms - (last_open_ms + INTERVAL_MS)) / 60_000, 2)
            if last_open_ms is not None else None
        )
        fresh = bool(
            continuity and age_minutes is not None
            and -1 <= age_minutes <= max_age_minutes
        )
        expected_reason = None if fresh else (
            "BASELINE_MISSING_OR_INCOMPLETE" if not continuity
            else "LATEST_15M_CANDLE_STALE"
        )
        row = by_symbol[symbol]
        if (
            row.get("rows") != rows_count
            or row.get("expected_rows") != expected_rows
            or row.get("continuity") is not continuity
            or row.get("first_open_ms") != first_open_ms
            or row.get("last_open_ms") != last_open_ms
            or row.get("fresh") is not fresh
            or row.get("reason") != expected_reason
        ):
            raise ValueError(f"DATA_REPORT_SYMBOL_FRESHNESS_MISMATCH:{symbol}")
        reported_age = row.get("age_minutes")
        if age_minutes is None:
            if reported_age is not None:
                raise ValueError(f"DATA_REPORT_SYMBOL_AGE_MISMATCH:{symbol}")
        elif (
            isinstance(reported_age, bool)
            or not isinstance(reported_age, (int, float))
            or not math.isfinite(float(reported_age))
            or abs(float(reported_age) - age_minutes) > 0.02
        ):
            raise ValueError(f"DATA_REPORT_SYMBOL_AGE_MISMATCH:{symbol}")
        complete_count += int(continuity)
        fresh_count += int(fresh)

    if (
        type(report.get("symbols_complete")) is not int
        or report.get("symbols_complete") != complete_count
        or type(report.get("symbols_fresh")) is not int
        or report.get("symbols_fresh") != fresh_count
    ):
        raise ValueError("DATA_REPORT_COUNT_MISMATCH")
    expected_status = (
        "PASS" if complete_count == len(symbols) and fresh_count == len(symbols)
        else "DEGRADED"
    )
    if report.get("status") != expected_status:
        raise ValueError("DATA_REPORT_GATE_LOGIC_MISMATCH")


def validate_artifact(
    artifact_dir: Path,
    expected_run_id: str,
    expected_workflow_sha: str,
    workflow_completed_at: str,
) -> str:
    root = artifact_dir.resolve()
    storage = root / "market-data/datasets/stage1b/lrt15m"
    manifest_path = root / "market-data/datasets/stage1b/manifest.json"
    report_path = root / "signal_autopilot/data/stage1b_15m_data_report.json"
    if not storage.is_dir() or not manifest_path.is_file() or not report_path.is_file():
        raise ValueError("ARTIFACT_REQUIRED_PATH_MISSING")

    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"ARTIFACT_SYMLINK_REJECTED:{path.relative_to(root)}")
    total_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
    if total_bytes > 250_000_000:
        raise ValueError(f"ARTIFACT_TOO_LARGE:{total_bytes}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    symbols = manifest.get("symbols")
    files = manifest.get("files")
    if manifest.get("schema_version") != 1 or manifest.get("dataset") != "stage1b_lrt15m_rolling_730d":
        raise ValueError("MANIFEST_SCHEMA_OR_DATASET_INVALID")
    if manifest.get("workflow_run_id") != str(expected_run_id):
        raise ValueError("WORKFLOW_RUN_ID_MISMATCH")
    if manifest.get("workflow_commit") != expected_workflow_sha:
        raise ValueError("WORKFLOW_COMMIT_MISMATCH")
    if manifest.get("signal_engine_executed") is not False:
        raise ValueError("P0_SIGNAL_ENGINE_MUST_REMAIN_DISABLED")
    if manifest.get("universe_count") != 27 or manifest.get("symbols_count") != 27:
        raise ValueError("MANIFEST_SYMBOL_COVERAGE_INVALID")
    if not isinstance(symbols, list) or len(symbols) != 27 or len(set(symbols)) != 27 or symbols != sorted(symbols):
        raise ValueError("MANIFEST_SYMBOL_LIST_INVALID")
    if any(not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) for symbol in symbols):
        raise ValueError("MANIFEST_SYMBOL_NAME_INVALID")
    if not isinstance(files, list) or manifest.get("files_count") != len(files):
        raise ValueError("MANIFEST_FILE_COUNT_INVALID")
    if manifest.get("baseline_files_count") != 27:
        raise ValueError("MANIFEST_BASELINE_COUNT_INVALID")
    if report.get("status") not in {"PASS", "DEGRADED"} or report.get("status") != manifest.get("data_gate_status"):
        raise ValueError("DATA_GATE_STATUS_MISMATCH")
    if report.get("universe_count") != 27 or report.get("symbols_processed") != 27:
        raise ValueError("DATA_REPORT_UNIVERSE_INVALID")
    if not isinstance(report.get("symbols_complete"), int) or not 0 <= report["symbols_complete"] <= 27:
        raise ValueError("DATA_REPORT_COMPLETENESS_INVALID")
    if not isinstance(report.get("symbols_fresh"), int) or not 0 <= report["symbols_fresh"] <= 27:
        raise ValueError("DATA_REPORT_FRESHNESS_INVALID")

    workflow_commit = manifest.get("workflow_commit", "")
    engine_commit = manifest.get("engine_commit", "")
    source_commit = manifest.get("legacy_source_commit", "")
    if not all(isinstance(value, str) and SHA_RE.fullmatch(value)
               for value in (workflow_commit, engine_commit, source_commit)):
        raise ValueError("MANIFEST_PROVENANCE_SHA_INVALID")

    actual_files = {
        path.relative_to(storage).as_posix()
        for path in storage.rglob("*") if path.is_file()
    }
    listed_files: set[str] = set()
    baseline_symbols: set[str] = set()
    timestamps_by_symbol: dict[str, set[int]] = {symbol: set() for symbol in symbols}
    rows_total = 0

    for item in files:
        rel = safe_manifest_path(str(item.get("path", "")))
        rel_text = rel.as_posix()
        if rel_text in listed_files:
            raise ValueError(f"MANIFEST_DUPLICATE_PATH:{rel_text}")
        listed_files.add(rel_text)
        symbol = item.get("symbol")
        kind = item.get("kind")
        if symbol not in timestamps_by_symbol:
            raise ValueError(f"UNKNOWN_FILE_SYMBOL:{symbol}")
        expected_name = f"{symbol}_15m.parquet"
        if rel.name != expected_name:
            raise ValueError(f"FILE_SYMBOL_PATH_MISMATCH:{rel_text}")
        if (rel.parts[0] == "base") != (kind == "BASELINE"):
            raise ValueError(f"FILE_KIND_PATH_MISMATCH:{rel_text}")
        path = storage.joinpath(*rel.parts)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"MANIFEST_FILE_MISSING_OR_LINK:{rel_text}")
        if path.stat().st_size != item.get("size_bytes"):
            raise ValueError(f"FILE_SIZE_MISMATCH:{rel_text}")
        digest = sha256_file(path)
        if digest != item.get("sha256"):
            raise ValueError(f"FILE_SHA256_MISMATCH:{rel_text}")
        table = pq.read_table(path)
        if table.num_rows != item.get("rows"):
            raise ValueError(f"FILE_ROW_COUNT_MISMATCH:{rel_text}")
        rows = table.to_pylist()
        timestamps = validate_rows(rows, symbol, kind, rel)
        if not timestamps:
            raise ValueError(f"EMPTY_MANIFEST_FILE:{rel_text}")
        if item.get("first_open_ms") != timestamps[0] or item.get("last_open_ms") != timestamps[-1]:
            raise ValueError(f"FILE_TIMESTAMP_RANGE_MISMATCH:{rel_text}")
        if kind == "BASELINE":
            if symbol in baseline_symbols or len(timestamps) != EXPECTED_ROWS:
                raise ValueError(f"BASELINE_COVERAGE_INVALID:{symbol}")
            if any(right - left != INTERVAL_MS for left, right in zip(timestamps, timestamps[1:])):
                raise ValueError(f"BASELINE_GAP:{symbol}")
            baseline_symbols.add(symbol)
        elif kind != "LIVE_TAIL":
            raise ValueError(f"UNKNOWN_FILE_KIND:{kind}")
        if timestamps_by_symbol[symbol].intersection(timestamps):
            raise ValueError(f"CROSS_FILE_DUPLICATE_TIMESTAMP:{symbol}")
        timestamps_by_symbol[symbol].update(timestamps)
        rows_total += len(rows)

    if actual_files != listed_files:
        raise ValueError("UNMANIFESTED_OR_MISSING_STORAGE_FILES")
    if baseline_symbols != set(symbols):
        raise ValueError("BASELINE_SYMBOL_SET_MISMATCH")
    if manifest.get("live_tail_files_count") != sum(1 for item in files if item.get("kind") == "LIVE_TAIL"):
        raise ValueError("LIVE_TAIL_COUNT_MISMATCH")
    if manifest.get("rows_total") != rows_total:
        raise ValueError("MANIFEST_TOTAL_ROWS_MISMATCH")

    completed_ms = _parse_utc_ms(workflow_completed_at, "WORKFLOW_COMPLETED_AT")
    validate_report_freshness(report, symbols, timestamps_by_symbol, completed_ms)

    ordered_files = sorted(files, key=lambda item: (item["symbol"], item["kind"], item["path"]))
    canonical = json.dumps(ordered_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    aggregate = hashlib.sha256(canonical).hexdigest()
    if aggregate != manifest.get("dataset_sha256"):
        raise ValueError("MANIFEST_AGGREGATE_SHA256_MISMATCH")
    print(f"LEGACY_SOURCE_COMMIT={source_commit}")
    print(f"DATA_GATE_STATUS={report['status']}")
    print(f"VALIDATED_FILES={len(files)}")
    print(f"VALIDATED_ROWS={rows_total}")
    print("P0_ARTIFACT_VALIDATION=PASS")
    return source_commit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--workflow-completed-at", required=True)
    args = parser.parse_args()
    validate_artifact(
        args.artifact_dir, args.run_id, args.workflow_sha,
        args.workflow_completed_at,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
