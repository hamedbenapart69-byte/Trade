#!/usr/bin/env python3
"""Read-only availability probe for Binance Vision USD-M futures archives."""
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://data.binance.vision/data/futures/um"
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "NEARUSDT", "XRPUSDT", "SOLUSDT",
    "BNBUSDT", "UNIUSDT", "DOGEUSDT", "ADAUSDT",
]
MONTHS = ["2025-01", "2026-01"]
TIMEOUT = (10, 30)


def archive_url(kind: str, symbol: str, month: str) -> str:
    if kind == "klines":
        return f"{BASE}/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"
    if kind == "funding_rate":
        return f"{BASE}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"
    raise ValueError(kind)


def head(url: str) -> dict:
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        return {"url": url, "status_code": r.status_code, "content_length": r.headers.get("Content-Length")}
    except requests.RequestException as exc:
        return {"url": url, "status_code": None, "error": type(exc).__name__}


def checksum_text(url: str) -> str | None:
    r = requests.get(url + ".CHECKSUM", timeout=TIMEOUT)
    if r.status_code != 200:
        return None
    match = re.search(r"\b([a-fA-F0-9]{64})\b", r.text)
    return match.group(1).lower() if match else None


def verify_sample(kind: str, symbol: str, month: str) -> dict:
    url = archive_url(kind, symbol, month)
    try:
        r = requests.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return {"url": url, "status": "ARCHIVE_UNAVAILABLE", "http_status": r.status_code}
        expected = checksum_text(url)
        if not expected:
            return {"url": url, "status": "CHECKSUM_UNAVAILABLE", "archive_bytes": len(r.content)}
        actual = hashlib.sha256(r.content).hexdigest()
        if actual != expected:
            return {"url": url, "status": "CHECKSUM_MISMATCH", "expected": expected, "actual": actual}
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            members = zf.namelist()
            if not members:
                return {"url": url, "status": "EMPTY_ARCHIVE"}
            with zf.open(members[0]) as f:
                first_line = f.readline().decode("utf-8", errors="replace").strip()
        return {
            "url": url, "status": "CHECKSUM_VERIFIED", "sha256": actual,
            "archive_bytes": len(r.content), "member": members[0], "first_line": first_line[:240],
        }
    except (requests.RequestException, zipfile.BadZipFile, OSError) as exc:
        return {"url": url, "status": "ERROR", "error": type(exc).__name__}


def main() -> None:
    checks = [
        (kind, symbol, month)
        for kind in ("klines", "funding_rate")
        for symbol in SYMBOLS
        for month in MONTHS
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        availability = list(pool.map(lambda item: head(archive_url(*item)), checks))
    samples = [
        verify_sample("klines", "ETHUSDT", "2025-01"),
        verify_sample("funding_rate", "ETHUSDT", "2025-01"),
    ]
    ok = all(x.get("status_code") == 200 for x in availability) and all(
        x.get("status") == "CHECKSUM_VERIFIED" for x in samples
    )
    output = {
        "schema_version": "1.0.0",
        "artifact_type": "binance_vision_usdm_futures_archive_probe",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if ok else "FAIL",
        "provider": "Binance Vision USD-M public archives",
        "symbols": SYMBOLS,
        "months_probed": MONTHS,
        "availability_checks": availability,
        "checksum_samples": samples,
        "note": "Read-only archive availability and checksum probe; no trading or account credentials.",
    }
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/binance-vision-futures-probe.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": output["status"], "checks": len(availability), "samples": samples}, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
