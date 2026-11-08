"""Stage 1a-extended: دریافت و اعتبارسنجی تاریخچه کامل 1H فیوچرز.

این اسکریپت فقط آرشیو عمومی Binance Vision را می‌خواند.
هیچ حساب معاملاتی، کلید خصوصی یا سفارش معاملاتی استفاده نمی‌شود.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE_URL = "https://data.binance.vision"
HOUR_MS = 3_600_000
COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
    "taker_buy_quote_volume", "ignore",
]


class ArchiveDownloadError(RuntimeError):
    pass


def month_starts(start: date, end_exclusive: date) -> list[date]:
    """ماه‌های آرشیوی که با بازه درخواستی هم‌پوشانی دارند."""
    current = date(start.year, start.month, 1)
    end_month = date(end_exclusive.year, end_exclusive.month, 1)
    result: list[date] = []
    while current < end_month:
        result.append(current)
        current = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
    return result


def date_range(start: date, end_exclusive: date):
    current = start
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def fetch_zip(url: str, timeout: int = 60, retries: int = 4) -> bytes:
    """دریافت ZIP با backoff برای 429/5xx و timeout."""
    last_error = "UNKNOWN"
    for attempt in range(retries):
        request = urllib.request.Request(url, headers={"User-Agent": "Trade-Stage1A-Extended/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise ArchiveDownloadError(f"HTTP_{response.status}")
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP_{exc.code}"
            if exc.code == 404:
                raise ArchiveDownloadError(last_error) from exc
            if exc.code not in (408, 425, 429, 500, 502, 503, 504):
                raise ArchiveDownloadError(last_error) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            last_error = "TIMEOUT" if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower() else type(exc).__name__
        if attempt + 1 < retries:
            time.sleep(min(2 ** attempt, 16))
    raise ArchiveDownloadError(f"RETRIES_EXHAUSTED_{last_error}")


def parse_zip_rows(payload: bytes, start_ms: int, end_ms: int) -> list[list[str]]:
    rows_out: list[list[str]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
        if not csv_name:
            raise ArchiveDownloadError("ZIP_WITHOUT_CSV")
        with archive.open(csv_name) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            for row in reader:
                if len(row) < 12 or not row[0].isdigit():
                    continue
                open_time = int(row[0])
                if start_ms <= open_time < end_ms:
                    rows_out.append(row[:12])
    return rows_out


def archive_urls(symbol: str, start: date, end_exclusive: date):
    """ماه‌های کامل/مرزی از monthly و بخش ماه جاری از daily دریافت می‌شود."""
    for month in month_starts(start, end_exclusive):
        name = f"{symbol}-1h-{month:%Y-%m}.zip"
        yield f"{BASE_URL}/data/futures/um/monthly/klines/{symbol}/1h/{name}", "monthly"
    if end_exclusive.day > 1:
        day = date(end_exclusive.year, end_exclusive.month, 1)
        while day < end_exclusive:
            name = f"{symbol}-1h-{day:%Y-%m-%d}.zip"
            yield f"{BASE_URL}/data/futures/um/daily/klines/{symbol}/1h/{name}", "daily"
            day += timedelta(days=1)


def run(symbols: list[str], start: date, end_exclusive: date, output_dir: Path, report_path: Path) -> dict[str, Any]:
    if end_exclusive <= start:
        raise ValueError("end-date must be after start-date")
    start_dt = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_exclusive, datetime.min.time(), tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    expected_rows = (end_ms - start_ms) // HOUR_MS
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    request_errors: Counter[str] = Counter()
    for symbol_index, symbol in enumerate(symbols, 1):
        collected: dict[int, list[str]] = {}
        errors: list[str] = []
        request_count = 0
        for url, archive_type in archive_urls(symbol, start, end_exclusive):
            request_count += 1
            try:
                payload = fetch_zip(url)
                for row in parse_zip_rows(payload, start_ms, end_ms):
                    collected[int(row[0])] = row
            except ArchiveDownloadError as exc:
                reason = str(exc)
                request_errors[reason.split("_")[0]] += 1
                errors.append(f"{archive_type}:{url.rsplit('/', 1)[-1]}:{reason}")
            time.sleep(0.10)

        timestamps = sorted(collected)
        gaps = sum(1 for left, right in zip(timestamps, timestamps[1:]) if right - left != HOUR_MS)
        complete = len(timestamps) == expected_rows and gaps == 0
        first_time = datetime.fromtimestamp(timestamps[0] / 1000, timezone.utc).isoformat() if timestamps else None
        last_time = datetime.fromtimestamp(timestamps[-1] / 1000, timezone.utc).isoformat() if timestamps else None
        row_result = {
            "symbol": symbol, "status": "FULL_HISTORY" if complete else "INCOMPLETE",
            "rows": len(timestamps), "expected_rows": expected_rows, "gaps": gaps,
            "first_open_utc": first_time, "last_open_utc": last_time,
            "archive_requests": request_count, "errors": errors[:30],
        }
        results.append(row_result)

        if complete:
            file_path = output_dir / f"{symbol}_1h_{start.isoformat()}_{end_exclusive.isoformat()}.csv.gz"
            with gzip.open(file_path, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(COLUMNS)
                writer.writerows(collected[ts] for ts in timestamps)
            row_result["file"] = str(file_path)

        print(f"[{symbol_index}/{len(symbols)}] {symbol}: {row_result['status']} {len(timestamps)}/{expected_rows} rows", flush=True)

    full_count = sum(row["status"] == "FULL_HISTORY" for row in results)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "BINANCE_VISION_USDM_MONTHLY_PLUS_DAILY",
        "start_utc": start_dt.isoformat(), "end_exclusive_utc": end_dt.isoformat(),
        "expected_rows_per_symbol": expected_rows, "symbols_requested": len(symbols),
        "symbols_full_history": full_count, "minimum_full_history_symbols": 40,
        "stage1a_extended_status": "PASS" if full_count >= 40 else "FAIL",
        "request_error_counts": dict(request_errors), "symbols": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols-file", default="data/stage1a_qualifying_symbols.json")
    parser.add_argument("--start-date", default="2024-11-09")
    parser.add_argument("--end-date", default="2026-11-09", help="exclusive UTC date")
    parser.add_argument("--output-dir", default="../market-data/ohlcv_1h")
    parser.add_argument("--report", default="data/stage1a_extension_report.json")
    args = parser.parse_args()

    symbol_data = json.loads(Path(args.symbols_file).read_text(encoding="utf-8"))
    symbols = list(dict.fromkeys(symbol_data["symbols"]))
    report = run(symbols, date.fromisoformat(args.start_date), date.fromisoformat(args.end_date),
                 Path(args.output_dir), Path(args.report))
    print(json.dumps({k: v for k, v in report.items() if k != "symbols"}, ensure_ascii=False, indent=2))
    return 0 if report["stage1a_extended_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
