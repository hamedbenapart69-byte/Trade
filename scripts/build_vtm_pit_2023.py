#!/usr/bin/env python3
"""Build point-in-time Binance USD-M USDT-perpetual universe for 2023."""
from __future__ import annotations
import concurrent.futures, csv, hashlib, io, json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"
BASE = "https://data.binance.vision/"
PREFIX = "data/futures/um/monthly/klines/"
START, END = date(2023, 1, 1), date(2023, 12, 31)
WARMUP_START = START - timedelta(days=30)
MONTHS = ["2022-12"] + [f"2023-{m:02d}" for m in range(1, 13)]
LOOKBACK = 30
THRESHOLD = 10_000_000.0
OUT = Path("results/vtm_pit_2023")

def get_bytes(url: str, retries: int = 4) -> bytes:
    error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VTM-PIT-Research/1.0"})
            with urllib.request.urlopen(req, timeout=45) as response:
                return response.read()
        except Exception as exc:
            error = exc
            time.sleep(min(2 ** attempt, 12))
    raise RuntimeError(f"GET failed: {url}: {error}")

def list_s3(prefix: str, delimiter: str | None = None) -> list[dict[str, str]]:
    out, token = [], None
    ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if delimiter:
            params["delimiter"] = delimiter
        if token:
            params["continuation-token"] = token
        root = ET.fromstring(get_bytes(BUCKET + "?" + urllib.parse.urlencode(params)))
        for node in root.findall("s3:Contents", ns):
            out.append({"key": node.findtext("s3:Key", default="", namespaces=ns)})
        for node in root.findall("s3:CommonPrefixes", ns):
            out.append({"prefix": node.findtext("s3:Prefix", default="", namespaces=ns)})
        if root.findtext("s3:IsTruncated", default="false", namespaces=ns).lower() != "true":
            break
        token = root.findtext("s3:NextContinuationToken", default="", namespaces=ns)
        if not token:
            raise RuntimeError("S3 pagination token missing")
    return out

def discover_symbols() -> list[str]:
    found = set()
    for item in list_s3(PREFIX, delimiter="/"):
        p = item.get("prefix", "")
        symbol = p[len(PREFIX):].strip("/").upper() if p.startswith(PREFIX) else ""
        # USD-M USDT perpetual naming; dated delivery contracts contain underscore.
        if symbol.endswith("USDT") and "_" not in symbol and re.fullmatch(r"[A-Z0-9]+", symbol):
            found.add(symbol)
    if not found:
        raise RuntimeError("No candidate USDT perpetual symbol folders found")
    return sorted(found)

def archives_for(symbol: str) -> dict[str, str]:
    p = f"{PREFIX}{symbol}/1d/"
    found = {}
    pattern = re.compile(re.escape(p + symbol + "-1d-") + r"(\d{4}-\d{2})\.zip$")
    for item in list_s3(p):
        key = item.get("key", "")
        match = pattern.fullmatch(key)
        if match and match.group(1) in MONTHS:
            found[match.group(1)] = key
    return found

def download_verified(key: str) -> tuple[bytes, str]:
    url = BASE + key
    payload = get_bytes(url)
    checksum = get_bytes(url + ".CHECKSUM").decode("utf-8").strip().split()[0].lower()
    actual = hashlib.sha256(payload).hexdigest()
    if checksum != actual:
        raise ValueError(f"SHA256 mismatch {key}: expected {checksum}, got {actual}")
    return payload, actual

def parse_zip(symbol: str, month: str, payload: bytes) -> dict[date, dict[str, float]]:
    rows = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"{symbol} {month}: expected one CSV, got {names}")
        with zf.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            for row in reader:
                if not row or not row[0].strip().isdigit():
                    continue
                if len(row) < 8:
                    raise ValueError(f"{symbol} {month}: malformed Kline row")
                day = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).date()
                op, hi, lo, cl = map(float, row[1:5])
                qv = float(row[7])
                if qv < 0 or min(op, hi, lo, cl) <= 0 or hi < max(op, cl, lo) or lo > min(op, cl, hi):
                    raise ValueError(f"{symbol} {day}: invalid Kline values")
                if day in rows:
                    raise ValueError(f"{symbol} {day}: duplicate daily row")
                rows[day] = {"quote_volume": qv, "open": op, "high": hi, "low": lo, "close": cl}
    return rows

def fetch_symbol(symbol: str):
    keys = archives_for(symbol)
    rows, evidence = {}, []
    for month in MONTHS:
        key = keys.get(month)
        if not key:
            continue
        payload, sha = download_verified(key)
        part = parse_zip(symbol, month, payload)
        rows.update(part)
        evidence.append({"symbol": symbol, "month": month, "key": key, "sha256": sha, "rows": len(part)})
    return symbol, {d: r for d, r in rows.items() if WARMUP_START <= d <= END}, evidence

def build_universe(data: dict[str, dict[date, dict[str, float]]]):
    daily, membership = [], []
    for offset in range((END - START).days + 1):
        day = START + timedelta(days=offset)
        eligible = []
        for symbol, rows in data.items():
            if day not in rows:
                continue
            prior = [day - timedelta(days=n) for n in range(LOOKBACK, 0, -1)]
            if any(d not in rows for d in prior):
                continue
            mean_qv = sum(rows[d]["quote_volume"] for d in prior) / LOOKBACK
            if mean_qv > THRESHOLD:
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
    for m in range(1, 13):
        days = [x for x in daily if int(x["date"][5:7]) == m]
        counts = [x["symbol_count"] for x in days]
        last = days[-1]
        monthly.append({
            "month": f"2023-{m:02d}", "days_observed": len(days),
            "mean_daily_universe_size": round(sum(counts) / len(counts), 4),
            "min_daily_universe_size": min(counts), "max_daily_universe_size": max(counts),
            "month_end_universe_size": last["symbol_count"], "month_end_symbols": last["symbols"],
        })
    return daily, membership, monthly

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    symbols = discover_symbols()
    print(f"Discovered {len(symbols)} candidate USDT symbols")
    data, archive_evidence, failures = {}, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {pool.submit(fetch_symbol, s): s for s in symbols}
        for job in concurrent.futures.as_completed(jobs):
            symbol = jobs[job]
            try:
                s, rows, evidence = job.result()
                if rows:
                    data[s] = rows
                archive_evidence.extend(evidence)
                print(f"{s}: {len(rows)} rows, {len(evidence)} archives")
            except Exception as exc:
                failures.append({"symbol": symbol, "error": str(exc)})
                print(f"ERROR {symbol}: {exc}")
    if failures:
        (OUT / "download_failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
        raise RuntimeError(f"{len(failures)} symbols failed; refusing incomplete Universe")
    daily, membership, monthly = build_universe(data)
    (OUT / "universe_daily.json").write_text(json.dumps(daily, indent=2), encoding="utf-8")
    with (OUT / "universe_daily.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "symbol_count", "symbols"]); w.writeheader()
        for x in daily: w.writerow({"date": x["date"], "symbol_count": x["symbol_count"], "symbols": ";".join(x["symbols"])})
    with (OUT / "universe_membership.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["date", "symbol", "mean_quote_volume_30d_usdt", "quote_volume_today_usdt", "lookback_start", "lookback_end"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(membership)
    (OUT / "monthly_universe_counts.json").write_text(json.dumps(monthly, indent=2), encoding="utf-8")
    with (OUT / "monthly_universe_counts.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["month", "days_observed", "mean_daily_universe_size", "min_daily_universe_size", "max_daily_universe_size", "month_end_universe_size", "month_end_symbols"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for x in monthly: w.writerow({**x, "month_end_symbols": ";".join(x["month_end_symbols"])})
    manifest = {
        "dataset": "vtm_pit_usdm_usdt_perpetual_universe_2023", "status": "PASS",
        "source": "Binance Vision USD-M Futures monthly 1d Kline archives",
        "source_index": BUCKET, "source_data_base": BASE,
        "universe_period": ["2023-01-01", "2023-12-31"],
        "warmup_period": [WARMUP_START.isoformat(), "2022-12-31"],
        "candidate_symbols_discovered": len(symbols), "symbols_with_relevant_rows": len(data),
        "verified_archive_files": len(archive_evidence), "checksum": "SHA-256 verified using sibling .CHECKSUM files",
        "perpetual_classification": "USDT suffix and no dated-delivery suffix; naming-convention proxy, not a historical exchangeInfo snapshot",
        "active_on_date_rule": "A valid daily Kline row exists for that UTC date; absent daily bar means not eligible",
        "liquidity_rule": {"metric": "USD-M Kline Quote Asset Volume (USDT)", "window": "30 immediately preceding UTC calendar days", "statistic": "arithmetic mean", "threshold_exclusive_usdt": THRESHOLD, "current_day_excluded": True, "requires_all_30_prior_daily_bars": True},
        "lookahead_policy": "Membership on D uses only the 30 completed calendar days before D; current-day bar is used only to establish current-date archive presence.",
        "records": {"daily_dates": len(daily), "membership_rows": len(membership), "monthly_summaries": len(monthly)},
        "limitations": [
            "Perpetual status is inferred from USD-M archive path and USDT non-delivery naming; a complete historical exchangeInfo status series is not included.",
            "A missing daily Kline is conservatively excluded and may undercount a live contract with no reported trades that day.",
            "This represents Binance USD-M USDT perpetuals, not the entire cross-exchange market."
        ],
        "archive_files": archive_evidence
    }
    (OUT / "universe_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "candidate_symbols": len(symbols), "symbols_with_rows": len(data), "verified_archives": len(archive_evidence), "membership_rows": len(membership), "monthly": monthly}, indent=2))

if __name__ == "__main__":
    main()
