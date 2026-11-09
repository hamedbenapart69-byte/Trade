"""دریافت تاریخچهٔ ۱۵ دقیقه‌ای Binance Vision برای ۲۷ نماد ثابت."""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = "https://data.binance.vision"
INTERVAL = "15m"
INTERVAL_MS = 900_000
RETRYABLE = {500, 502, 503, 504}


class ArchiveError(RuntimeError):
    pass


def request_bytes(url: str, method: str = "GET", attempts: int = 3) -> tuple[int, bytes]:
    last_error = "UNKNOWN"
    for attempt in range(attempts):
        request = urllib.request.Request(
            url, method=method, headers={"User-Agent": "Trade-LRT15m/1.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.status, response.read() if method == "GET" else b""
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRYABLE:
                return exc.code, b""
            last_error = f"HTTP_{exc.code}"
        except (TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError,)) or isinstance(exc, TimeoutError):
                last_error = "TIMEOUT"
            else:
                raise ArchiveError(f"NETWORK_ERROR:{reason}") from exc
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    raise ArchiveError(f"RETRIES_EXHAUSTED:{last_error}")


def head_get(url: str) -> tuple[bytes | None, str]:
    status, _ = request_bytes(url, "HEAD")
    if status == 404:
        return None, "404"
    if status in (405, 501):
        pass
    elif status != 200:
        return None, f"HEAD_{status}"
    status, payload = request_bytes(url, "GET")
    if status == 404:
        return None, "404"
    if status != 200:
        return None, f"GET_{status}"
    return payload, "200"


def parse_zip(payload: bytes, start_ms: int, end_ms: int) -> dict[int, dict[str, float]]:
    output: dict[int, dict[str, float]] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = next((n for n in archive.namelist() if n.lower().endswith(".csv")), None)
        if not csv_name:
            raise ArchiveError("ZIP_WITHOUT_CSV")
        with archive.open(csv_name) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                if len(row) < 11 or not row[0].isdigit():
                    continue
                ts = int(row[0])
                if start_ms <= ts < end_ms:
                    output[ts] = {
                        "open": float(row[1]), "high": float(row[2]),
                        "low": float(row[3]), "close": float(row[4]),
                        "volume": float(row[5]), "quote_volume": float(row[7]),
                        "trades": float(row[8]), "taker_buy_base": float(row[9]),
                        "taker_buy_quote": float(row[10]),
                    }
    return output


def months_between(start: date, end: date):
    current = date(start.year, start.month, 1)
    stop = date(end.year, end.month, 1)
    while current < stop:
        yield current
        current = date(current.year + (current.month == 12),
                       1 if current.month == 12 else current.month + 1, 1)


def days_between(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def month_end(month: date) -> date:
    return date(month.year + (month.month == 12),
                1 if month.month == 12 else month.month + 1, 1)


async def download_symbol(symbol: str, start: date, end: date,
                          outdir: Path, semaphore: asyncio.Semaphore) -> dict[str, Any]:
    start_ms = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end, datetime.min.time(), timezone.utc).timestamp() * 1000)
    bars: dict[int, dict[str, float]] = {}
    events: list[dict[str, str]] = []
    async with semaphore:
        for month in months_between(start, end):
            stop = min(month_end(month), end)
            first = max(month, start)
            is_complete_month = first == month and stop == month_end(month)
            if is_complete_month:
                name = f"{symbol}-{INTERVAL}-{month:%Y-%m}.zip"
                url = f"{BASE}/data/futures/um/monthly/klines/{symbol}/{INTERVAL}/{name}"
                try:
                    payload, status = await asyncio.to_thread(head_get, url)
                    if payload is not None:
                        bars.update(parse_zip(payload, start_ms, end_ms))
                        events.append({"archive": name, "status": "MONTHLY_OK"})
                        continue
                    events.append({"archive": name, "status": f"MONTHLY_{status}"})
                except Exception as exc:
                    events.append({"archive": name, "status": f"MONTHLY_ERROR:{type(exc).__name__}:{exc}"})
            # Fallback daily: missing monthly archive or partial current month.
            for day in days_between(first, stop):
                name = f"{symbol}-{INTERVAL}-{day:%Y-%m-%d}.zip"
                url = f"{BASE}/data/futures/um/daily/klines/{symbol}/{INTERVAL}/{name}"
                try:
                    payload, status = await asyncio.to_thread(head_get, url)
                    if payload is None:
                        events.append({"archive": name, "status": f"DAILY_{status}"})
                        continue
                    bars.update(parse_zip(payload, start_ms, end_ms))
                    events.append({"archive": name, "status": "DAILY_OK"})
                except Exception as exc:
                    events.append({"archive": name, "status": f"DAILY_ERROR:{type(exc).__name__}:{exc}"})

    timestamps = sorted(bars)
    gaps = sum(1 for a, b in zip(timestamps, timestamps[1:]) if b - a != INTERVAL_MS)
    expected = (end_ms - start_ms) // INTERVAL_MS
    complete = len(timestamps) == expected and gaps == 0
    output_file = None
    if timestamps:
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
            records = [{"open_time": ts, **bars[ts]} for ts in timestamps]
            table = pa.Table.from_pylist(records)
            outdir.mkdir(parents=True, exist_ok=True)
            target = outdir / f"{symbol}_15m_{start}_{end}.parquet"
            pq.write_table(table, target, compression="zstd", version="2.6")
            output_file = str(target)
        except Exception as exc:
            raise ArchiveError(f"PARQUET_WRITE_FAILED:{symbol}:{exc}") from exc
    return {
        "symbol": symbol, "rows": len(timestamps), "expected_rows": expected,
        "gap_count": gaps, "continuity": complete,
        "first_open_ms": timestamps[0] if timestamps else None,
        "last_open_ms": timestamps[-1] if timestamps else None,
        "file": output_file, "archive_events": events,
    }


async def run(start: date, end: date, outdir: Path, report_path: Path,
              universe_path: Path) -> dict[str, Any]:
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; got {len(symbols)}")
    if (end - start).days != 730:
        raise ValueError("Stage 1b history window must be exactly 730 days")
    semaphore = asyncio.Semaphore(5)
    tasks = [asyncio.create_task(download_symbol(s, start, end, outdir, semaphore)) for s in symbols]
    results = []
    for index, task in enumerate(asyncio.as_completed(tasks), 1):
        try:
            result = await task
        except Exception as exc:
            result = {"symbol": "TASK_ERROR", "continuity": False,
                      "rows": 0, "reason": f"{type(exc).__name__}:{exc}"}
        results.append(result)
        print(f"15M_PROGRESS {index}/27 complete={sum(x.get('continuity') is True for x in results)}", flush=True)
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "universe_as_of_utc": universe.get("as_of_utc"),
            "start_date_utc": start.isoformat(), "end_date_exclusive_utc": end.isoformat(),
            "interval": INTERVAL, "universe_count": 27,
            "symbols_complete": sum(x.get("continuity") is True for x in results),
            "symbols_processed": len(results), "symbols": results,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    complete_count = sum(x.get("continuity") is True for x in results)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_as_of_utc": universe.get("as_of_utc"),
        "start_date_utc": start.isoformat(), "end_date_exclusive_utc": end.isoformat(),
        "interval": INTERVAL, "universe_count": 27,
        "symbols_complete": complete_count, "symbols_processed": len(results),
        "status": "PASS" if complete_count == 27 else "FAIL",
        "symbols": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STAGE1B_15M_DATA " + json.dumps({
        "complete": complete_count, "universe": 27, "status": report["status"]
    }), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--universe", default="signal_autopilot/data/stage1b_universe_27.json")
    args = parser.parse_args()
    report = asyncio.run(run(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date),
                             Path(args.output_dir), Path(args.report), Path(args.universe)))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
