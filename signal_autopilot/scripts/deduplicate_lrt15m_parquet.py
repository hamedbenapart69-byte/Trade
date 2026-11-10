"""نرمال‌سازی امن فایل‌های Parquet تایم‌فریم ۱۵ دقیقه و ثبت تعارض‌ها.

فایل‌های ورودی دست‌نخورده می‌مانند. ردیف‌های تکراری فقط وقتی ادغام می‌شوند
که OHLCV آن‌ها یکسان باشد؛ تعارض قیمت/حجم باعث توقف می‌شود.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

INTERVAL_MS = 900_000
CORE_FIELDS = ("open", "high", "low", "close", "volume")
REQUIRED_FIELDS = ("open_time", *CORE_FIELDS)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def symbol_for(path: Path, rows: list[dict[str, Any]]) -> str:
    if "_15m_" in path.name:
        value = path.name.split("_15m_", 1)[0]
        if value:
            return value.upper()
    values = {str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")}
    if len(values) == 1:
        return next(iter(values))
    raise ValueError(f"SYMBOL_NOT_IDENTIFIABLE:{path}")


def row_complete_count(row: dict[str, Any]) -> int:
    return sum(value is not None for value in row.values())


def core_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in CORE_FIELDS:
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            if a is not b:
                return False
            continue
        if not math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12):
            return False
    return True


def normalize(input_dir: Path, output_dir: Path, report_path: Path,
              expected_symbols: int | None = 27) -> dict[str, Any]:
    files = sorted(path for path in input_dir.rglob("*.parquet") if path.is_file())
    if not files:
        raise ValueError(f"NO_PARQUET_FILES:{input_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"OUTPUT_DIRECTORY_NOT_EMPTY:{output_dir}")

    grouped: dict[tuple[str, int], list[tuple[dict[str, Any], Path]]] = defaultdict(list)
    input_files = []
    symbols: set[str] = set()
    input_rows = 0

    for path in files:
        table = pq.read_table(path)
        rows = table.to_pylist()
        symbol = symbol_for(path, rows)
        symbols.add(symbol)
        input_files.append({
            "path": str(path),
            "rows": len(rows),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
        for row in rows:
            missing = [field for field in REQUIRED_FIELDS if row.get(field) is None]
            if missing:
                raise ValueError(f"REQUIRED_FIELD_MISSING:{path}:{missing}")
            timestamp = int(row["open_time"])
            if timestamp % INTERVAL_MS != 0:
                raise ValueError(f"INVALID_15M_TIMESTAMP:{symbol}:{timestamp}")
            values = [float(row[field]) for field in CORE_FIELDS]
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"NON_FINITE_OHLCV:{symbol}:{timestamp}")
            opn, high, low, close, volume = values
            if min(opn, high, low, close) <= 0 or volume < 0:
                raise ValueError(f"INVALID_OHLCV_RANGE:{symbol}:{timestamp}")
            if high < max(opn, close, low) or low > min(opn, close, high):
                raise ValueError(f"INVALID_OHLC_RELATION:{symbol}:{timestamp}")
            grouped[(symbol, timestamp)].append((row, path))
            input_rows += 1

    if expected_symbols is not None and len(symbols) != expected_symbols:
        raise ValueError(f"SYMBOL_COVERAGE_FAIL:expected={expected_symbols}:actual={len(symbols)}")

    conflicts = []
    chosen: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exact_duplicates = 0
    metadata_variants = 0

    for (symbol, timestamp), candidates in sorted(grouped.items()):
        base = candidates[0][0]
        if any(not core_equal(base, candidate) for candidate, _ in candidates[1:]):
            conflicts.append({
                "symbol": symbol,
                "open_time": timestamp,
                "files": sorted(str(path) for _, path in candidates),
                "core_values": [
                    {field: row.get(field) for field in CORE_FIELDS}
                    for row, _ in candidates
                ],
            })
            continue
        if len(candidates) > 1:
            exact_duplicates += len(candidates) - 1
            metadata_variants += int(any(
                any(row.get(key) != base.get(key) for key in set(row) | set(base)
                    if key not in CORE_FIELDS and key != "open_time")
                for row, _ in candidates[1:]
            ))
        best_row, _ = max(
            candidates,
            key=lambda item: (row_complete_count(item[0]), str(item[1])),
        )
        chosen[symbol].append(best_row)

    report: dict[str, Any] = {
        "schema_version": 1,
        "dataset": "stage1b_lrt15m_deduplicated",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_files_count": len(files),
        "input_rows": input_rows,
        "symbols_count": len(symbols),
        "symbols": sorted(symbols),
        "unique_rows": sum(len(rows) for rows in chosen.values()),
        "exact_duplicate_rows_removed": exact_duplicates,
        "duplicate_metadata_variants": metadata_variants,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "input_files": input_files,
        "output_files": [],
        "hash_algorithm": "SHA-256",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if conflicts:
        report["status"] = "FAIL_CONFLICTING_OHLCV"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise ValueError(f"CONFLICTING_OHLCV:{len(conflicts)}; see {report_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for symbol in sorted(chosen):
        rows = sorted(chosen[symbol], key=lambda row: int(row["open_time"]))
        target = output_dir / f"{symbol}_15m_deduplicated.parquet"
        pq.write_table(pa.Table.from_pylist(rows), target, compression="zstd", version="2.6")
        output_files = {
            "path": target.name,
            "symbol": symbol,
            "rows": len(rows),
            "size_bytes": target.stat().st_size,
            "sha256": sha256_file(target),
            "first_open_ms": int(rows[0]["open_time"]),
            "last_open_ms": int(rows[-1]["open_time"]),
        }
        report["output_files"].append(output_files)

    canonical = json.dumps(report["output_files"], sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    report["dataset_sha256"] = hashlib.sha256(canonical).hexdigest()
    report["status"] = "PASS"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "input_files": report["input_files_count"],
        "input_rows": report["input_rows"],
        "symbols": report["symbols_count"],
        "unique_rows": report["unique_rows"],
        "duplicates_removed": report["exact_duplicate_rows_removed"],
        "conflicts": report["conflict_count"],
        "dataset_sha256": report["dataset_sha256"],
    }, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--expected-symbols", type=int, default=27)
    args = parser.parse_args()
    normalize(Path(args.input_dir), Path(args.output_dir), Path(args.report), args.expected_symbols)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
