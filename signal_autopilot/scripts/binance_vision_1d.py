#!/usr/bin/env python3
"""Download Binance Vision USD-M futures 1d monthly klines for the approved universe.

Research data acquisition only. It does not calculate indicators or signals.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import hashlib
import io
import json
import logging
import os
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

# 25-symbol universe: the 27-symbol target minus unavailable HOT and 1000PEPE.
SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
    "BCHUSDT", "NEARUSDT", "INJUSDT", "UNIUSDT", "FILUSDT",
    "ARBUSDT", "ENAUSDT", "SUIUSDT", "TAOUSDT", "WLDUSDT",
    "ZECUSDT", "AAVEUSDT", "QNTUSDT", "RSRUSDT", "ONEUSDT",
)
COLUMNS = (
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "number_of_trades",
    "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
)
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"


@dataclass
class ArchiveResult:
    symbol: str
    month: str
    url: str
    status: str
    http_status: int | None
    bytes_downloaded: int
    sha256: str | None
    rows: int
    error: str | None


def month_starts(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    result = []
    while cursor <= last:
        result.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return result


def archive_url(symbol: str, month: date) -> str:
    ym = month.strftime("%Y-%m")
    filename = f"{symbol}-1d-{ym}.zip"
    return f"{BASE_URL}/{symbol}/1d/{filename}"


def fetch_archive(symbol: str, month: date, retries: int = 3) -> tuple[ArchiveResult, pd.DataFrame]:
    url = archive_url(symbol, month)
    last_error = None
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": "CFSS-Historical-Research/1.0", "Accept": "application/zip"})
            with urlopen(request, timeout=45) as response:
                payload = response.read()
                status = response.status
            digest = hashlib.sha256(payload).hexdigest()
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
                if len(names) != 1:
                    raise ValueError(f"EXPECTED_ONE_CSV_GOT_{len(names)}")
                raw = archive.read(names[0])
            frame = pd.read_csv(io.BytesIO(raw), header=None)
            if len(frame.columns) not in (12, 13):
                raise ValueError(f"UNEXPECTED_COLUMN_COUNT_{len(frame.columns)}")
            if len(frame.columns) == 13:
                frame = frame.iloc[:, :12]
            first = str(frame.iloc[0, 0]).strip().lower() if not frame.empty else ""
            if first in {"open_time", "open time", "opentime"}:
                frame = frame.iloc[1:].reset_index(drop=True)
            frame.columns = COLUMNS
            frame["open_time"] = pd.to_numeric(frame["open_time"], errors="raise").astype("int64")
            for col in ("open", "high", "low", "close", "volume", "quote_asset_volume",
                        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume"):
                frame[col] = pd.to_numeric(frame[col], errors="raise")
            frame["number_of_trades"] = pd.to_numeric(frame["number_of_trades"], errors="raise").astype("int64")
            frame["close_time"] = pd.to_numeric(frame["close_time"], errors="raise").astype("int64")
            frame["symbol"] = symbol
            frame["open_time_utc"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
            if frame.empty:
                raise ValueError("EMPTY_ARCHIVE")
            if frame["open_time"].duplicated().any() or not frame["open_time"].is_monotonic_increasing:
                raise ValueError("DUPLICATE_OR_UNSORTED_OPEN_TIME")
            if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any():
                raise ValueError("INVALID_HIGH")
            if (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any():
                raise ValueError("INVALID_LOW")
            return ArchiveResult(symbol, month.strftime("%Y-%m"), url, "PASS", status, len(payload), digest, len(frame), None), frame
        except HTTPError as exc:
            last_error = f"HTTP_{exc.code}"
            if exc.code == 404:
                break
        except (URLError, TimeoutError, OSError, ValueError, zipfile.BadZipFile, pd.errors.ParserError) as exc:
            last_error = f"{type(exc).__name__}:{exc}"
        if attempt + 1 < retries:
            time.sleep(1.5 * (attempt + 1))
    return ArchiveResult(symbol, month.strftime("%Y-%m"), url, "FAIL", None, 0, None, 0, last_error), pd.DataFrame()


def run(start: date, end: date, output: Path, workers: int) -> dict:
    if start > end:
        raise ValueError("START_AFTER_END")
    output.mkdir(parents=True, exist_ok=True)
    months = month_starts(start, end)
    jobs = [(symbol, month) for symbol in SYMBOLS for month in months]
    results: list[ArchiveResult] = []
    frames: dict[str, list[pd.DataFrame]] = {s: [] for s in SYMBOLS}
    with futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fetch_archive, symbol, month): (symbol, month) for symbol, month in jobs}
        for future in futures.as_completed(future_map):
            result, frame = future.result()
            results.append(result)
            if result.status == "PASS":
                frames[result.symbol].append(frame)
            logging.info("%s %s %s rows=%d", result.symbol, result.month, result.status, result.rows)
    symbol_reports = []
    for symbol in SYMBOLS:
        parts = frames[symbol]
        if not parts:
            symbol_reports.append({"symbol": symbol, "status": "UNAVAILABLE", "rows": 0})
            continue
        data = pd.concat(parts, ignore_index=True).sort_values("open_time").drop_duplicates("open_time", keep="last")
        data = data[(data["open_time_utc"].dt.date >= start) & (data["open_time_utc"].dt.date <= end)]
        data = data.reset_index(drop=True)
        csv_path = output / f"{symbol}_1d.csv"
        parquet_path = output / f"{symbol}_1d.parquet"
        data.to_csv(csv_path, index=False, quoting=csv.QUOTE_MINIMAL)
        data.to_parquet(parquet_path, index=False, compression="zstd")
        expected_days = (end - start).days + 1
        observed_days = int(data["open_time"].nunique())
        symbol_reports.append({
            "symbol": symbol, "status": "PASS" if len(data) > 0 else "EMPTY",
            "rows": len(data), "first_open_utc": data["open_time_utc"].min().isoformat() if len(data) else None,
            "last_open_utc": data["open_time_utc"].max().isoformat() if len(data) else None,
            "csv": csv_path.name, "parquet": parquet_path.name,
            "coverage_ratio_vs_calendar_days": round(observed_days / expected_days, 6),
            "sha256_csv": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "sha256_parquet": hashlib.sha256(parquet_path.read_bytes()).hexdigest(),
        })
    passed_archives = sum(r.status == "PASS" for r in results)
    report = {
        "schema": "cfss.binance_vision_1d_dataset.v1",
        "source": "Binance Vision USD-M Futures monthly klines",
        "interval": "1d", "universe": list(SYMBOLS),
        "start_date_utc": start.isoformat(), "end_date_utc": end.isoformat(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "requested_archives": len(jobs), "passed_archives": passed_archives,
        "failed_archives": [asdict(r) for r in results if r.status != "PASS"],
        "archive_manifest": [asdict(r) for r in sorted(results, key=lambda x: (x.symbol, x.month))],
        "symbols": symbol_reports,
        "overall_status": "PASS" if passed_archives == len(jobs) and all(s["status"] == "PASS" for s in symbol_reports) else "PARTIAL",
        "limitations": [
            "OHLCV archive only; this dataset does not contain historical order-book thinness.",
            "LFS components requiring historical funding, positioning and open interest are not inferred from OHLCV.",
            "Current partial month is excluded by default; choose explicit dates if partial coverage is intended.",
        ],
    }
    (output / "dataset_manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2024-11-01", help="UTC inclusive YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-10-31", help="UTC inclusive YYYY-MM-DD")
    parser.add_argument("--output", default="artifacts/binance_vision_1d")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if not 1 <= args.workers <= 12:
        parser.error("--workers must be between 1 and 12")
    return args


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    report = run(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date), Path(args.output), args.workers)
    print(json.dumps({k: report[k] for k in ("overall_status", "requested_archives", "passed_archives", "start_date_utc", "end_date_utc", "symbols")}, indent=2))
    return 0 if report["overall_status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
