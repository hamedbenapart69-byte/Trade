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


def validate_artifact(artifact_dir: Path, expected_run_id: str) -> str:
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
    if manifest.get("signal_engine_executed") is not False:
        raise ValueError("P0_SIGNAL_ENGINE_MUST_REMAIN_DISABLED")
    if manifest.get("universe_count") != 27 or manifest.get("symbols_count") != 27:
        raise ValueError("MANIFEST_SYMBOL_COVERAGE_INVALID")
    if not isinstance(symbols, list) or len(symbols) != 27 or len(set(symbols)) != 27:
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
    args = parser.parse_args()
    validate_artifact(args.artifact_dir, args.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
