#!/usr/bin/env python3
"""Rebuild real daily OHLCV from the verified VTM PIT universe artifact."""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, io, json, zipfile, urllib.request
from pathlib import Path
import pandas as pd

BASE = "https://data.binance.vision/"

def fetch_one(item):
    key = item["key"]
    expected = item["sha256"].lower()
    req = urllib.request.Request(BASE + key, headers={"User-Agent":"Trade-PIT-Research/1.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        payload = response.read()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch for {key}: {actual} != {expected}")
    rows = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_files = [n for n in archive.namelist() if n.endswith(".csv")]
        if len(csv_files) != 1:
            raise ValueError(f"Unexpected CSV count in {key}: {len(csv_files)}")
        import csv
        import io as _io
        with archive.open(csv_files[0]) as raw:
            for row in csv.reader(_io.TextIOWrapper(raw, encoding="utf-8")):
                if not row or not row[0].isdigit():
                    continue
                rows.append({
                    "timestamp": pd.to_datetime(int(row[0]), unit="ms", utc=True).floor("D"),
                    "symbol": item["symbol"],
                    "open": float(row[1]), "high": float(row[2]),
                    "low": float(row[3]), "close": float(row[4]),
                    "volume": float(row[5]), "quote_volume": float(row[7]),
                    "source_sha256": actual,
                })
    return rows, actual

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/pit/universe_manifest.json")
    ap.add_argument("--output", default="data/pit/ohlcv_2023.parquet")
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text())
    if manifest.get("status") != "PASS":
        raise RuntimeError("PIT universe manifest is not PASS")
    if manifest.get("dataset") != "vtm_pit_usdm_usdt_perpetual_universe_2023":
        raise RuntimeError("Unexpected PIT dataset identity")
    files = manifest.get("archive_files", [])
    if not files:
        raise RuntimeError("PIT manifest contains no archive file records")
    records, verified, errors = [], 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
        futures = {pool.submit(fetch_one, item): item for item in files}
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            try:
                rows, _ = future.result()
                records.extend(rows)
                verified += 1
            except Exception as exc:
                errors.append({"key":item.get("key"),"error":str(exc)})
    if errors:
        raise RuntimeError("Strict PIT archive validation failed: " + json.dumps(errors[:10]))
    df = pd.DataFrame.from_records(records)
    df = df.drop_duplicates(["symbol","timestamp"], keep="last")
    df = df.sort_values(["timestamp","symbol"]).reset_index(drop=True)
    start, end = map(pd.Timestamp, manifest["universe_period"])
    df = df[(df.timestamp >= start.tz_localize("UTC")) & (df.timestamp <= end.tz_localize("UTC"))]
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.output, index=False)
    result = {
        "status":"PASS", "dataset":manifest["dataset"],
        "source":"Binance Vision USD-M 1d Kline archives",
        "period":manifest["universe_period"],
        "manifest_archive_files":len(files), "verified_archive_files":verified,
        "rows":len(df), "symbols":int(df.symbol.nunique()),
        "sha256_verified":True, "output":args.output,
        "funding":"UNAVAILABLE", "open_interest":"UNAVAILABLE",
        "limitations":manifest.get("limitations",[])
    }
    Path(args.output + ".manifest.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__ == "__main__":
    main()
