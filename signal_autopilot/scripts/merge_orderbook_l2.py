#!/usr/bin/env python3
"""Merge one capture into market-data Parquet without replacing earlier samples."""
from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def merge(source_dir: Path, target_dir: Path) -> int:
    merged_files = 0
    for source in sorted(source_dir.rglob("*.parquet")):
        relative = source.relative_to(source_dir)
        target = target_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        incoming = pq.read_table(source).to_pylist()
        previous = pq.read_table(target).to_pylist() if target.exists() else []
        unique = {}
        for row in previous + incoming:
            key = (row.get("exchange"), row.get("symbol"), row.get("sampled_at_ms"))
            unique[key] = row
        rows = sorted(unique.values(), key=lambda row: (
            row.get("sampled_at_ms", 0), row.get("exchange", ""), row.get("symbol", "")
        ))
        pq.write_table(pa.Table.from_pylist(rows), target, compression="zstd")
        merged_files += 1
        print(f"MERGED {target}: rows={len(rows)}")
    return merged_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--target-dir", required=True)
    args = parser.parse_args()
    count = merge(Path(args.source_dir), Path(args.target_dir))
    print(f"ORDERBOOK_PARQUET_FILES_MERGED={count}")
    return 0 if count else 2


if __name__ == "__main__":
    raise SystemExit(main())
