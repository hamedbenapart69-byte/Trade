"""ممیزی تعارض OHLCV بین Snapshotهای خام تاریخی و baseline نرمال‌شده."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

INTERVAL_MS = 900_000
CORE = ("open", "high", "low", "close", "volume")
REQUIRED = ("open_time", *CORE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def symbol_from(path: Path) -> str:
    if "_15m_" not in path.name:
        raise ValueError(f"UNEXPECTED_RAW_FILENAME:{path.name}")
    return path.name.split("_15m_", 1)[0].upper()


def load_and_validate(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = pq.read_table(path).to_pylist()
    if not rows:
        raise ValueError(f"EMPTY_PARQUET:{path}")
    timestamps: list[int] = []
    for index, row in enumerate(rows):
        missing = [field for field in REQUIRED if row.get(field) is None]
        if missing:
            raise ValueError(f"MISSING_FIELDS:{path}:row={index}:{missing}")
        ts = int(row["open_time"])
        if ts % INTERVAL_MS:
            raise ValueError(f"BAD_15M_ALIGNMENT:{path}:row={index}")
        values = [float(row[field]) for field in CORE]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"NON_FINITE_OHLCV:{path}:row={index}")
        opn, high, low, close, volume = values
        if min(opn, high, low, close) <= 0 or volume < 0:
            raise ValueError(f"OHLCV_RANGE:{path}:row={index}")
        if high < max(opn, close, low) or low > min(opn, close, high):
            raise ValueError(f"OHLC_RELATION:{path}:row={index}")
        timestamps.append(ts)
    if timestamps != sorted(timestamps):
        raise ValueError(f"TIMESTAMPS_NOT_SORTED:{path}")
    if len(timestamps) != len(set(timestamps)):
        raise ValueError(f"DUPLICATE_TIMESTAMPS:{path}")
    return rows, {
        "path": str(path),
        "rows": len(rows),
        "size_bytes": path.stat().st_size,
        "first_open_ms": timestamps[0],
        "last_open_ms": timestamps[-1],
        "sha256": sha256_file(path),
    }


def core_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for field in CORE:
        if not math.isclose(float(left[field]), float(right[field]),
                            rel_tol=1e-12, abs_tol=1e-12):
            return False
    return True


def row_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(row["open_time"]): row for row in rows}


def compare_pair(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    left_map, right_map = row_map(left), row_map(right)
    overlap = sorted(set(left_map) & set(right_map))
    conflicts = []
    for ts in overlap:
        if not core_equal(left_map[ts], right_map[ts]):
            conflicts.append({
                "open_time": ts,
                "left": {field: left_map[ts][field] for field in CORE},
                "right": {field: right_map[ts][field] for field in CORE},
            })
    return {
        "overlap_rows": len(overlap),
        "conflict_rows": len(conflicts),
        "conflict_samples": conflicts[:20],
    }


def audit(raw_dir: Path, canonical_dir: Path, report_path: Path,
          expected_symbols: int, raw_source_commit: str,
          canonical_commit: str) -> dict[str, Any]:
    raw_files = sorted(raw_dir.glob("*_15m_*.parquet"))
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in raw_files:
        grouped[symbol_from(path)].append(path)

    symbols = sorted(grouped)
    if len(symbols) != expected_symbols:
        raise ValueError(f"RAW_SYMBOL_COVERAGE:expected={expected_symbols}:actual={len(symbols)}")

    results = []
    global_conflicts = 0
    global_overlap = 0
    errors = []

    for symbol in symbols:
        candidates = sorted(grouped[symbol], key=lambda path: path.name)
        if len(candidates) != 2:
            errors.append({"symbol": symbol, "error": f"EXPECTED_TWO_RAW_SNAPSHOTS:{len(candidates)}"})
            continue
        try:
            old_rows, old_meta = load_and_validate(candidates[0])
            new_rows, new_meta = load_and_validate(candidates[1])
            pair = compare_pair(old_rows, new_rows)
            global_conflicts += pair["conflict_rows"]
            global_overlap += pair["overlap_rows"]

            canonical_path = canonical_dir / f"{symbol}_15m.parquet"
            canonical_rows, canonical_meta = load_and_validate(canonical_path)
            canonical_vs_newest = compare_pair(canonical_rows, new_rows)
            canonical_map, newest_map = row_map(canonical_rows), row_map(new_rows)
            canonical_exact = (
                set(canonical_map) == set(newest_map)
                and canonical_vs_newest["conflict_rows"] == 0
                and canonical_vs_newest["overlap_rows"] == len(newest_map)
            )
            if not canonical_exact:
                errors.append({
                    "symbol": symbol,
                    "error": "CANONICAL_NOT_EXACTLY_NEWEST_VALID_SNAPSHOT",
                    "canonical_vs_newest": canonical_vs_newest,
                })
            if pair["conflict_rows"]:
                errors.append({
                    "symbol": symbol,
                    "error": "CONFLICTING_RAW_SNAPSHOT_OHLCV",
                    "comparison": pair,
                })
            results.append({
                "symbol": symbol,
                "raw_snapshots": [old_meta, new_meta],
                "overlap_comparison": pair,
                "canonical": canonical_meta,
                "canonical_matches_newest": canonical_exact,
            })
        except Exception as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    report = {
        "schema_version": 1,
        "status": "PASS" if not errors and global_conflicts == 0 else "FAIL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_source_commit": raw_source_commit,
        "canonical_market_data_commit": canonical_commit,
        "expected_symbols": expected_symbols,
        "symbols_seen": len(symbols),
        "raw_files_seen": len(raw_files),
        "overlap_rows_compared": global_overlap,
        "conflicting_ohlcv_rows": global_conflicts,
        "canonical_files_match_newest_snapshot": sum(
            1 for item in results if item["canonical_matches_newest"]
        ),
        "results": results,
        "errors": errors,
        "hash_algorithm": "SHA-256",
        "raw_snapshots_modified": False,
        "canonical_dataset_modified": False,
    }
    canonical = json.dumps(
        [{k: item[k] for k in ("symbol", "raw_snapshots", "canonical", "canonical_matches_newest")}
         for item in results],
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    report["audit_sha256"] = hashlib.sha256(canonical).hexdigest()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "symbols": report["symbols_seen"],
        "raw_files": report["raw_files_seen"],
        "overlap_rows_compared": report["overlap_rows_compared"],
        "conflicting_ohlcv_rows": report["conflicting_ohlcv_rows"],
        "canonical_files_match_newest": report["canonical_files_match_newest"],
        "audit_sha256": report["audit_sha256"],
    }, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--canonical-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-symbols", type=int, default=27)
    parser.add_argument("--raw-source-commit", default="UNKNOWN")
    parser.add_argument("--canonical-commit", default="UNKNOWN")
    args = parser.parse_args()
    report = audit(
        args.raw_dir, args.canonical_dir, args.report, args.expected_symbols,
        args.raw_source_commit, args.canonical_commit,
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
