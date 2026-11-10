#!/usr/bin/env python3
"""Collect public L2 snapshots from OKX, Bybit and KuCoin Futures into Parquet."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.orderbook_l2 import SYMBOLS, capture_orderbooks, write_parquet_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTC,ETH,SOL,XRP,DOGE,ADA,LINK,LTC,BCH,AVAX")
    parser.add_argument("--duration-seconds", type=int, default=600)
    parser.add_argument("--sample-interval-seconds", type=int, default=10)
    parser.add_argument("--output-dir", default="data/orderbook_l2")
    args = parser.parse_args()
    symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    unknown = [item for item in symbols if item not in SYMBOLS]
    if unknown:
        raise SystemExit("UNSUPPORTED_SYMBOLS=" + ",".join(unknown))
    if not 60 <= args.duration_seconds <= 900:
        raise SystemExit("duration_seconds must be between 60 and 900")
    if not 5 <= args.sample_interval_seconds <= 60:
        raise SystemExit("sample_interval_seconds must be between 5 and 60")
    result = asyncio.run(capture_orderbooks(symbols, args.duration_seconds, args.sample_interval_seconds))
    paths = write_parquet_records(result["records"], args.output_dir)
    summary = {key: value for key, value in result.items() if key != "records"}
    summary.update({"symbols": symbols, "parquet_files": paths})
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary_latest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("ORDERBOOK_L2_RESULT=" + json.dumps(summary, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
