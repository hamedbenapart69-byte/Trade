#!/usr/bin/env python3
"""Build a date-range PIT universe from Binance Vision USD-M daily klines."""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"
BASE = "https://data.binance.vision/"
PREFIX = "data/futures/um/monthly/klines/"
LOOKBACK_DAYS = 30
DEFAULT_LIQUIDITY_THRESHOLD_USDT = 10_000_000.0


def get_bytes(url: str, retries: int = 4) -> bytes:
    error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "PIT-Universe-Research/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"GET failed: {url}: {error}")


def list_s3(prefix: str, delimiter: str | None = None) -> list[dict[str, str]]:
    output, token = [], None
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        root = ET.fromstring(get_bytes(BUCKET + "?" + urllib.parse.urlencode(params)))
        for node in root.findall("s3:Contents", namespace):
            output.append({"key": node.findtext("s3:Key", default="", namespaces=namespace)})
        for node in root.findall("s3:CommonPrefixes", namespace):
            output.append({"prefix": node.findtext("s3:Prefix", default="", namespaces=namespace)})
        if root.findtext("s3:IsTruncated", default="false", namespaces=namespace).lower() != "true":
            break
        token = root.findtext("s3:NextContinuationToken", default="", namespaces=namespace)
        if not token:
            raise RuntimeError("S3 pagination token missing")
    return output


def discover_symbols() -> list[str]:
    found = set()
    for item in list_s3(PREFIX, delimiter="/"):
        prefix = item.get("prefix", "")
        symbol = prefix[len(PREFIX):].strip("/").upper() if prefix.startswith(PREFIX) else ""
        if symbol.endswith("USDT") and "_" not in symbol and re.fullmatch(r"[A-Z0-9]+", symbol):
            found.add(symbol)
    if not found:
        raise RuntimeError("No candidate USDT perpetual symbol folders found")
    return sorted(found)


def months_between(start: date, end: date) -> list[str]:
    cursor, last, months = date(start.year, start.month, 1), date(end.year, end.month, 1), []
    while cursor <= last:
        months.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return months


def archives_for(symbol: str, months: list[str]) -> dict[str, str]:
    prefix = f"{PREFIX}{symbol}/1d/"
    pattern = re.compile(re.escape(prefix + symbol + "-1d-") + r"(\d{4}-\d{2})\.zip$")
    return {
        match.group(1): key
        for item in list_s3(prefix)
        if (key := item.get("key", "")) and (match := pattern.fullmatch(key))
        and match.group(1) in months
    }


def download_verified(key: str) -> tuple[bytes, str]:
    url = BASE + key
    payload = get_bytes(url)
    expected = get_bytes(url + ".CHECKSUM").decode("utf-8").strip().split()[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if expected != actual:
        raise ValueError(f"SHA256 mismatch {key}: expected {expected}, got {actual}")
    return payload, actual


def parse_zip(symbol: str, month: str, payload: bytes) -> dict[date, dict[str, float]]:
    rows = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{symbol} {month}: expected one CSV, got {names}")
        with archive.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            for row in reader:
                if not row or not row[0].strip().isdigit():
                    continue
                if len(row) < 8:
                    raise ValueError(f"{symbol} {month}: malformed Kline row")
                day = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).date()
                op, high, low, close = map(float, row[1:5])
                quote_volume = float(row[7])
                if quote_volume < 0 or min(op, high, low, close) <= 0 or high < max(op, close, low) or low > min(op, close, high):
                    raise ValueError(f"{symbol} {day}: invalid Kline values")
                if day in rows:
                    raise ValueError(f"{symbol} {day}: duplicate daily row")
                rows[day] = {"quote_volume": quote_volume, "open": op, "high": high, "low": low, "close": close}
    return rows


def fetch_symbol(symbol: str, months: list[str], warmup_start: date, end: date):
    keys, rows, evidence = archives_for(symbol, months), {}, []
    for month in months:
        key = keys.get(month)
        if not key:
            continue
        payload, checksum = download_verified(key)
        part = parse_zip(symbol, month, payload)
        rows.update(part)
        evidence.append({"symbol": symbol, "month": month, "key": key, "sha256": checksum, "rows": len(part)})
    return symbol, {d: row for d, row in rows.items() if warmup_start <= d <= end}, evidence


def build_universe(data, start: date, end: date, lookback_days: int = LOOKBACK_DAYS,
                   threshold_usdt: float = DEFAULT_LIQUIDITY_THRESHOLD_USDT):
    if end < start or lookback_days < 1 or threshold_usdt < 0:
        raise ValueError("invalid_date_range_lookback_or_threshold")
    daily, membership = [], []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        prior = [day - timedelta(days=n) for n in range(lookback_days, 0, -1)]
        eligible = []
        for symbol, rows in data.items():
            if day not in rows or any(d not in rows for d in prior):
                continue
            mean_qv = sum(rows[d]["quote_volume"] for d in prior) / lookback_days
            if mean_qv > threshold_usdt:
                eligible.append(symbol)
                membership.append({
                    "date": day.isoformat(), "symbol": symbol,
                    "mean_quote_volume_30d_usdt": round(mean_qv, 6),
                    "quote_volume_today_usdt": round(rows[day]["quote_volume"], 6),
                    "lookback_start": prior[0].isoformat(), "lookback_end": prior[-1].isoformat(),
                })
        eligible.sort()
        daily.append({"date": day.isoformat(), "symbol_count": len(eligible), "symbols": eligible})
    monthly = []
    for month in months_between(start, end):
        days = [row for row in daily if row["date"][:7] == month]
        counts = [row["symbol_count"] for row in days]
        last = days[-1]
        monthly.append({
            "month": month, "days_observed": len(days),
            "mean_daily_universe_size": round(sum(counts) / len(counts), 4),
            "min_daily_universe_size": min(counts), "max_daily_universe_size": max(counts),
            "month_end_universe_size": last["symbol_count"], "month_end_symbols": last["symbols"],
        })
    return daily, membership, monthly


def write_outputs(output_dir: Path, start: date, end: date, symbols, data, archive_evidence,
                  daily, membership, monthly, lookback_days: int, threshold_usdt: float):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "universe_daily.json").write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "universe_daily.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["date", "symbol_count", "symbols"])
        writer.writeheader()
        for row in daily:
            writer.writerow({"date": row["date"], "symbol_count": row["symbol_count"], "symbols": ";".join(row["symbols"])})
    fields = ["date", "symbol", "mean_quote_volume_30d_usdt", "quote_volume_today_usdt", "lookback_start", "lookback_end"]
    with (output_dir / "universe_membership.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(membership)
    (output_dir / "monthly_universe_counts.json").write_text(json.dumps(monthly, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["month", "days_observed", "mean_daily_universe_size", "min_daily_universe_size", "max_daily_universe_size", "month_end_universe_size", "month_end_symbols"]
    with (output_dir / "monthly_universe_counts.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in monthly:
            writer.writerow({**row, "month_end_symbols": ";".join(row["month_end_symbols"])})
    warmup_start = start - timedelta(days=lookback_days)
    manifest = {
        "dataset": "binance_usdm_usdt_perpetual_pit_universe", "status": "PASS",
        "source": "Binance Vision USD-M Futures monthly 1d Kline archives",
        "source_index": BUCKET, "source_data_base": BASE,
        "universe_period": [start.isoformat(), end.isoformat()],
        "warmup_period": [warmup_start.isoformat(), (start - timedelta(days=1)).isoformat()],
        "candidate_symbols_discovered": len(symbols), "symbols_with_relevant_rows": len(data),
        "verified_archive_files": len(archive_evidence),
        "checksum": "SHA-256 verified using sibling .CHECKSUM files",
        "perpetual_classification": "USDT suffix and no dated-delivery suffix; naming-convention proxy, not a historical exchangeInfo snapshot",
        "active_on_date_rule": "A valid daily Kline row exists for that UTC date; absent daily bar means not eligible",
        "liquidity_rule": {
            "metric": "USD-M Kline Quote Asset Volume (USDT)",
            "window": f"{lookback_days} immediately preceding UTC calendar days",
            "statistic": "arithmetic mean", "threshold_exclusive_usdt": threshold_usdt,
            "current_day_excluded": True, "requires_all_prior_daily_bars": True,
        },
        "lookahead_policy": "Membership on D uses only completed calendar days before D; current-day bar is used only to establish current-date archive presence.",
        "records": {"daily_dates": len(daily), "membership_rows": len(membership), "monthly_summaries": len(monthly)},
        "limitations": [
            "Perpetual status is inferred from USD-M archive path and USDT non-delivery naming; complete historical exchangeInfo status is not included.",
            "A missing daily Kline is conservatively excluded and may undercount a live contract with no reported trades that day.",
            "This represents Binance USD-M USDT perpetuals, not the entire cross-exchange market.",
            "Candidate symbols are discovered from currently discoverable Binance Vision archive folders; historical delisted-symbol completeness is not independently proven.",
        ],
        "archive_files": archive_evidence,
    }
    (output_dir / "universe_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def run_build(start: date, end: date, output_dir: Path, workers: int = 8,
              lookback_days: int = LOOKBACK_DAYS,
              threshold_usdt: float = DEFAULT_LIQUIDITY_THRESHOLD_USDT):
    if end < start:
        raise ValueError("end_date_must_be_on_or_after_start_date")
    if not 1 <= workers <= 32:
        raise ValueError("workers_must_be_between_1_and_32")
    warmup_start = start - timedelta(days=lookback_days)
    months, symbols = months_between(warmup_start, end), discover_symbols()
    print(f"Discovered {len(symbols)} candidate USDT symbols", flush=True)
    data, evidence, failures = {}, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(fetch_symbol, s, months, warmup_start, end): s for s in symbols}
        for job in concurrent.futures.as_completed(jobs):
            symbol = jobs[job]
            try:
                returned, rows, archive_rows = job.result()
                if rows:
                    data[returned] = rows
                evidence.extend(archive_rows)
                print(f"{returned}: {len(rows)} rows, {len(archive_rows)} archives", flush=True)
            except Exception as exc:
                failures.append({"symbol": symbol, "error": str(exc)})
                print(f"ERROR {symbol}: {exc}", flush=True)
    if failures:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "download_failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
        raise RuntimeError(f"{len(failures)} symbols failed; refusing incomplete PIT universe")
    daily, membership, monthly = build_universe(data, start, end, lookback_days, threshold_usdt)
    manifest = write_outputs(output_dir, start, end, symbols, data, evidence, daily, membership, monthly, lookback_days, threshold_usdt)
    print(json.dumps({
        "status": manifest["status"], "period": manifest["universe_period"],
        "candidate_symbols": manifest["candidate_symbols_discovered"],
        "symbols_with_rows": manifest["symbols_with_relevant_rows"],
        "verified_archives": manifest["verified_archive_files"],
        "membership_rows": manifest["records"]["membership_rows"],
        "daily_dates": manifest["records"]["daily_dates"],
        "monthly_summaries": manifest["records"]["monthly_summaries"],
    }, ensure_ascii=False, indent=2), flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a date-range PIT universe from verified Binance Vision archives.")
    parser.add_argument("--start-date", required=True, help="Inclusive UTC date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="Inclusive UTC date YYYY-MM-DD")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    parser.add_argument("--threshold-usdt", type=float, default=DEFAULT_LIQUIDITY_THRESHOLD_USDT)
    args = parser.parse_args()
    run_build(date.fromisoformat(args.start_date), date.fromisoformat(args.end_date),
              Path(args.output_dir), args.workers, args.lookback_days, args.threshold_usdt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
