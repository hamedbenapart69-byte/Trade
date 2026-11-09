"""Stage 1a-extended v2: pre-validation, HEAD, fallback, parallel and resumable."""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import urllib.error
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = "https://data.binance.vision"
EXCHANGE_INFO_URLS = [
    "https://fapi.binance.com/fapi/v1/exchangeInfo",
    # میزبان‌های جایگزین همان API؛ فقط پاسخ واقعی Binance با onboardDate پذیرفته می‌شود.
    "https://fapi1.binance.com/fapi/v1/exchangeInfo",
    "https://fapi2.binance.com/fapi/v1/exchangeInfo",
    "https://fapi3.binance.com/fapi/v1/exchangeInfo",
    "https://fapi4.binance.com/fapi/v1/exchangeInfo",
    # fallback وب‌سایت؛ فقط در صورت بازگشت schema معتبر.
    "https://www.binance.com/bapi/futures/v1/public/future/common/get-exchange-info",
]
HOUR_MS = 3_600_000
COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
           "quote_asset_volume", "number_of_trades", "taker_buy_base_volume",
           "taker_buy_quote_volume", "ignore"]


class FetchFailure(RuntimeError):
    pass


def request_bytes(url: str, method: str = "GET", retries: int = 3) -> tuple[int, bytes]:
    """404/4xx غیرموقت retry نمی‌شود؛ فقط 5xx و timeout حداکثر ۳ تلاش."""
    last = "UNKNOWN"
    for attempt in range(retries):
        req = urllib.request.Request(url, method=method,
                                     headers={"User-Agent": "Trade-Stage1A-Extended/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return response.status, response.read() if method == "GET" else b""
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 403):
                return exc.code, b""
            if exc.code in (405, 501) and method == "HEAD":
                return exc.code, b""
            if exc.code not in (500, 502, 503, 504):
                raise FetchFailure(f"HTTP_{exc.code}") from exc
            last = f"HTTP_{exc.code}"
        except (TimeoutError, urllib.error.URLError) as exc:
            last = "TIMEOUT"
        if attempt < retries - 1:
            import time
            time.sleep(min(2 ** attempt, 8))
    raise FetchFailure(f"RETRIES_EXHAUSTED_{last}")


def head_then_get(url: str) -> tuple[bytes | None, str]:
    status, _ = request_bytes(url, "HEAD")
    if status == 404:
        return None, "HEAD_404"
    if status == 403:
        return None, "HEAD_403"
    if status in (405, 501):
        # بعضی edgeها HEAD را پشتیبانی نمی‌کنند؛ GET fallback است.
        pass
    elif status != 200:
        return None, f"HEAD_HTTP_{status}"
    get_status, payload = request_bytes(url, "GET")
    if get_status == 404:
        return None, "GET_404"
    if get_status != 200:
        return None, f"GET_HTTP_{get_status}"
    return payload, "OK"


def fetch_exchange_info() -> dict[str, dict[str, Any]]:
    # Snapshot رسمی exchangeInfo برای دور زدن محدودیت 451 در GitHub Actions.
    # onboardDate دادهٔ تغییرناپذیر listing است؛ وضعیت روزانه از snapshot تاریخی است.
    snapshot_path = Path("data/binance_futures_exchange_info_snapshot.json")
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        result = {}
        for item in snapshot.get("symbols", []):
            symbol = item.get("symbol")
            onboard = item.get("onboardDate")
            if symbol and onboard is not None and int(onboard) > 0:
                result[symbol] = {
                    "listing_date": item.get("listing_date_utc") or datetime.fromtimestamp(int(onboard) / 1000, timezone.utc).date().isoformat(),
                    "status": item.get("status"),
                    "contract_type": item.get("contractType"),
                    "metadata_source": snapshot.get("source"),
                    "metadata_captured_at_utc": snapshot.get("captured_at_utc"),
                }
        if result:
            return result

    failures = []
    for endpoint in EXCHANGE_INFO_URLS:
        try:
            status, payload = request_bytes(endpoint, "GET")
            if status != 200:
                failures.append(f"{endpoint}:HTTP_{status}")
                continue
            data = json.loads(payload)
            # bapi ممکن است پاسخ را در data بسته‌بندی کند.
            if isinstance(data, dict) and isinstance(data.get("data"), dict):
                data = data["data"]
            symbols = data.get("symbols", []) if isinstance(data, dict) else []
            result = {}
            for item in symbols:
                symbol = item.get("symbol")
                onboard = item.get("onboardDate")
                if symbol and onboard is not None and int(onboard) > 0:
                    result[symbol] = {
                        "listing_date": datetime.fromtimestamp(int(onboard) / 1000, timezone.utc).date().isoformat(),
                        "status": item.get("status") or item.get("contractStatus"),
                        "contract_type": item.get("contractType"),
                    }
            if result:
                return result
            failures.append(f"{endpoint}:NO_SYMBOLS_WITH_ONBOARDDATE")
        except Exception as exc:
            failures.append(f"{endpoint}:{type(exc).__name__}:{exc}")
    raise FetchFailure("BINANCE_EXCHANGE_INFO_ALL_SOURCES_FAILED|" + " | ".join(failures))


def parse_zip(payload: bytes, start_ms: int, end_ms: int) -> list[list[str]]:
    rows = []
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        csv_name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
        if not csv_name:
            raise FetchFailure("ZIP_WITHOUT_CSV")
        with zf.open(csv_name) as raw:
            for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8")):
                if len(row) >= 12 and row[0].isdigit():
                    ts = int(row[0])
                    if start_ms <= ts < end_ms:
                        rows.append(row[:12])
    return rows


def month_iter(start: date, end: date):
    """فقط آرشیو ماهانه کامل/منتشرشده؛ ماه پایانی ناقص با daily پوشش داده می‌شود."""
    cur = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    while cur < end_month:
        yield cur
        cur = date(cur.year + (cur.month == 12), 1 if cur.month == 12 else cur.month + 1, 1)


def dates_for_month(month: date, start: date, end: date):
    month_end = date(month.year + (month.month == 12), 1 if month.month == 12 else month.month + 1, 1)
    cur = max(month, start)
    stop = min(month_end, end)
    while cur < stop:
        yield cur
        cur += timedelta(days=1)


def parquet_write(rows: dict[int, list[str]], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    records = []
    for ts, row in sorted(rows.items()):
        records.append({
            "open_time": int(row[0]), "open": float(row[1]), "high": float(row[2]),
            "low": float(row[3]), "close": float(row[4]), "volume": float(row[5]),
            "close_time": int(row[6]), "quote_asset_volume": float(row[7]),
            "number_of_trades": int(float(row[8])), "taker_buy_base_volume": float(row[9]),
            "taker_buy_quote_volume": float(row[10]), "ignore": float(row[11]),
        })
    pq.write_table(pa.Table.from_pylist(records), path, compression="zstd", version="2.6")


async def process_symbol(symbol: str, listing: dict[str, Any] | None, start: date, end: date,
                         outdir: Path, sem: asyncio.Semaphore) -> dict[str, Any]:
    if listing is None:
        return {"symbol": symbol, "listing_date": None, "archive_status": "NOT_IN_EXCHANGE_INFO",
                "rows": 0, "continuity": False, "reason": "DELISTED_OR_NOT_RETURNED_BY_EXCHANGE_INFO"}
    listing_date = date.fromisoformat(listing["listing_date"])
    if listing_date > start:
        return {"symbol": symbol, "listing_date": listing["listing_date"],
                "archive_status": "EXCLUDED_LISTED_AFTER_WINDOW_START", "rows": 0,
                "continuity": False, "reason": "LISTING_DATE_AFTER_730D_START"}
    start_ms = int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    collected: dict[int, list[str]] = {}
    archive_events: list[dict[str, str]] = []
    async with sem:
        for month in month_iter(start, end):
            monthly_name = f"{symbol}-1h-{month:%Y-%m}.zip"
            monthly_url = f"{BASE}/data/futures/um/monthly/klines/{symbol}/1h/{monthly_name}"
            try:
                payload, status = await asyncio.to_thread(head_then_get, monthly_url)
            except Exception as exc:
                payload, status = None, f"ERROR_{type(exc).__name__}:{exc}"
            if payload is not None:
                try:
                    for row in parse_zip(payload, start_ms, end_ms):
                        collected[int(row[0])] = row
                    archive_events.append({"archive": monthly_name, "status": "MONTHLY_OK"})
                    continue
                except Exception as exc:
                    archive_events.append({"archive": monthly_name, "status": f"MONTHLY_PARSE_ERROR:{exc}"})
            else:
                archive_events.append({"archive": monthly_name, "status": status})
            # Monthly missing: daily fallback only for the intersecting days.
            for day in dates_for_month(month, start, end):
                daily_name = f"{symbol}-1h-{day:%Y-%m-%d}.zip"
                daily_url = f"{BASE}/data/futures/um/daily/klines/{symbol}/1h/{daily_name}"
                try:
                    daily_payload, daily_status = await asyncio.to_thread(head_then_get, daily_url)
                    if daily_payload is None:
                        archive_events.append({"archive": daily_name, "status": daily_status})
                        continue
                    for row in parse_zip(daily_payload, start_ms, end_ms):
                        collected[int(row[0])] = row
                    archive_events.append({"archive": daily_name, "status": "DAILY_OK"})
                except Exception as exc:
                    archive_events.append({"archive": daily_name, "status": f"ERROR_{type(exc).__name__}:{exc}"})
        # بخش ناقص ماه پایانی هنوز آرشیو ماهانه منتشرشده ندارد؛ فقط daily.
        if end.day > 1:
            for day in dates_for_month(date(end.year, end.month, 1), start, end):
                daily_name = f"{symbol}-1h-{day:%Y-%m-%d}.zip"
                daily_url = f"{BASE}/data/futures/um/daily/klines/{symbol}/1h/{daily_name}"
                try:
                    daily_payload, daily_status = await asyncio.to_thread(head_then_get, daily_url)
                    if daily_payload is None:
                        archive_events.append({"archive": daily_name, "status": daily_status})
                        continue
                    for row in parse_zip(daily_payload, start_ms, end_ms):
                        collected[int(row[0])] = row
                    archive_events.append({"archive": daily_name, "status": "DAILY_OK"})
                except Exception as exc:
                    archive_events.append({"archive": daily_name, "status": f"ERROR_{type(exc).__name__}:{exc}"})
    timestamps = sorted(collected)
    gaps = sum(1 for a, b in zip(timestamps, timestamps[1:]) if b - a != HOUR_MS)
    expected = (end_ms - start_ms) // HOUR_MS
    complete = len(timestamps) == expected and gaps == 0
    file_name = None
    if complete:
        outdir.mkdir(parents=True, exist_ok=True)
        target = outdir / f"{symbol}_1h_{start}_{end}.parquet"
        await asyncio.to_thread(parquet_write, collected, target)
        file_name = str(target)
    return {
        "symbol": symbol, "listing_date": listing["listing_date"], "exchange_status": listing.get("status"),
        "archive_status": "COMPLETE" if complete else "INCOMPLETE",
        "rows": len(timestamps), "expected_rows": expected, "gap_count": gaps,
        "continuity": complete, "first_open_utc": datetime.fromtimestamp(timestamps[0]/1000, timezone.utc).isoformat() if timestamps else None,
        "last_open_utc": datetime.fromtimestamp(timestamps[-1]/1000, timezone.utc).isoformat() if timestamps else None,
        "file": file_name, "archive_events": archive_events,
    }


async def run(symbols: list[str], start: date, end: date, outdir: Path, report_path: Path):
    if end <= start:
        raise ValueError("end-date must be after start-date")
    listing_map = await asyncio.to_thread(fetch_exchange_info)
    candidates = [s for s in symbols if s in listing_map and
                  date.fromisoformat(listing_map[s]["listing_date"]) <= start]
    if len(candidates) < 40:
        # Fail cheap: وقتی سقف ممکن از ۴۰ کمتر است، آرشیوها را بی‌دلیل دانلود نکن.
        precheck_rows = []
        for symbol in symbols:
            meta = listing_map.get(symbol)
            eligible = bool(meta and date.fromisoformat(meta["listing_date"]) <= start)
            precheck_rows.append({
                "symbol": symbol,
                "listing_date": meta.get("listing_date") if meta else None,
                "exchange_status": meta.get("status") if meta else None,
                "archive_status": "NOT_CHECKED_PREVALIDATION_BELOW_40" if eligible else (
                    "EXCLUDED_LISTED_AFTER_WINDOW_START" if meta else "NOT_IN_EXCHANGE_INFO"
                ),
                "rows": None, "continuity": False,
                "reason": "PREVALIDATION_FAIL_BELOW_40; no archive requests issued",
            })
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "BINANCE_FUTURES_EXCHANGEINFO_ONBOARDDATE_SNAPSHOT",
            "start_utc": f"{start.isoformat()}T00:00:00+00:00",
            "end_exclusive_utc": f"{end.isoformat()}T00:00:00+00:00",
            "expected_rows_per_symbol": (end-start).days * 24,
            "symbols_before_filter": len(symbols),
            "symbols_after_listing_filter": len(candidates),
            "symbols_processed": len(symbols), "symbols_full_history": 0,
            "maximum_possible_full_history_symbols": len(candidates),
            "minimum_full_history_symbols": 40,
            "stage1a_extended_status": "FAIL",
            "failure_reason": f"Only {len(candidates)} of {len(symbols)} symbols were listed by {start.isoformat()}; threshold is 40",
            "archive_requests_issued": 0,
            "parallelism": 5, "head_before_get": True,
            "retry_policy": "3 attempts only for HTTP 5xx and timeout; no 4xx retry",
            "symbols": precheck_rows,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k != "symbols"}, ensure_ascii=False, indent=2))
        return report
    results: list[dict[str, Any]] = []
    # بازیابی نمادهای کامل‌شده از checkpoint قبلی؛ نمادهای ناقص دوباره تلاش می‌شوند.
    if report_path.exists():
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
            same_window = (
                previous.get("start_utc") == f"{start.isoformat()}T00:00:00+00:00"
                and previous.get("end_exclusive_utc") == f"{end.isoformat()}T00:00:00+00:00"
            )
            if same_window:
                allowed = set(symbols)
                results = [
                    row for row in previous.get("symbols", [])
                    if row.get("symbol") in allowed and row.get("continuity") is True
                    and row.get("archive_status") == "COMPLETE"
                ]
                if results:
                    print(f"RESUME loaded {len(results)} complete symbols from checkpoint", flush=True)
        except (OSError, ValueError, TypeError):
            results = []
    completed = {row["symbol"] for row in results}
    pending = [symbol for symbol in symbols if symbol not in completed]
    semaphore = asyncio.Semaphore(5)
    # ترتیب ورودی ثابت است؛ هم‌زمانی واقعی به پنج نماد محدود می‌شود.
    tasks = [asyncio.create_task(process_symbol(s, listing_map.get(s), start, end, outdir, semaphore))
             for s in pending]
    for idx, task in enumerate(asyncio.as_completed(tasks), len(results) + 1):
        try:
            item = await task
        except Exception as exc:
            item = {
                "symbol": "TASK_ERROR",
                "archive_status": "INCOMPLETE",
                "rows": 0,
                "continuity": False,
                "reason": f"{type(exc).__name__}:{str(exc)[:200]}",
            }
        results.append(item)
        if idx % 10 == 0 or idx == len(symbols):
            report = build_report(symbols, listing_map, candidates, results, start, end, "RUNNING")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"PROGRESS {idx}/{len(symbols)} | full={report['symbols_full_history']} | prevalidated={len(candidates)}", flush=True)
    report = build_report(symbols, listing_map, candidates, results, start, end, None)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_report(symbols, listing_map, candidates, results, start, end, forced_status):
    full = sum(bool(x.get("continuity")) for x in results)
    prevalidated = sum(1 for s in symbols if s in listing_map and
                       date.fromisoformat(listing_map[s]["listing_date"]) <= start)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "BINANCE_FAPI_EXCHANGE_INFO_AND_BINANCE_VISION_MONTHLY_WITH_DAILY_FALLBACK",
        "start_utc": f"{start.isoformat()}T00:00:00+00:00",
        "end_exclusive_utc": f"{end.isoformat()}T00:00:00+00:00",
        "expected_rows_per_symbol": (end-start).days * 24,
        "symbols_before_filter": len(symbols), "symbols_after_listing_filter": prevalidated,
        "symbols_processed": len(results), "symbols_full_history": full,
        "minimum_full_history_symbols": 40,
        "stage1a_extended_status": forced_status or ("PASS" if full >= 40 else "FAIL"),
        "parallelism": 5, "head_before_get": True, "retry_policy": "3 attempts only for HTTP 5xx and timeout; no 4xx retry",
        "symbols": sorted(results, key=lambda x: x["symbol"]),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols-file", default="data/stage1a_qualifying_symbols.json")
    p.add_argument("--start-date", default="2024-11-08")
    p.add_argument("--end-date", default="2026-11-08")
    p.add_argument("--output-dir", default="../market-data/datasets/stage1a_extended/ohlcv_1h")
    p.add_argument("--report", default="data/stage1a_extension_report.json")
    a = p.parse_args()
    data = json.loads(Path(a.symbols_file).read_text(encoding="utf-8"))
    report = asyncio.run(run(list(dict.fromkeys(data["symbols"])), date.fromisoformat(a.start_date),
                             date.fromisoformat(a.end_date), Path(a.output_dir), Path(a.report)))
    print(json.dumps({k:v for k,v in report.items() if k != "symbols"}, ensure_ascii=False, indent=2))
    return 0 if report["stage1a_extended_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
