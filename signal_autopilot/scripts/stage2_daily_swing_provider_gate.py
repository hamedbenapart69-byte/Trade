#!/usr/bin/env python3
"""Stage 2 L1 provider gate: Binance Vision UM perpetual 1D/4H."""
from __future__ import annotations

import csv
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BASE = "https://data.binance.vision/data/futures/um/daily/klines"
EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TIMEFRAMES = {"1d": 86_400_000, "4h": 14_400_000}
MAX_STALENESS_MS = 32 * 60 * 60 * 1000
USER_AGENT = "CFSS-Stage2-DailySwing-ProviderGate/1.0"


class GateError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                raise GateError(f"HTTP_{response.status}")
            return response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="replace").replace("\\n", " ").replace("\\r", " ")
        body = " ".join(body.split())[:240]
        raise GateError(f"HTTP_{exc.code}:{urlsplit(url).netloc}{urlsplit(url).path}:body={body}") from exc
    except urllib.error.URLError as exc:
        raise GateError(f"NETWORK_{type(exc.reason).__name__}") from exc


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_universe(path: Path) -> list[str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    symbols = obj.get("symbols")
    if not isinstance(symbols, list) or len(symbols) != 27:
        raise GateError("UNIVERSE_MUST_CONTAIN_EXACTLY_27_SYMBOLS")
    if len(set(symbols)) != 27 or any(not isinstance(s, str) or not s for s in symbols):
        raise GateError("UNIVERSE_SYMBOLS_INVALID_OR_DUPLICATED")
    return symbols


def verify_exchange_contracts(symbols: list[str]) -> dict[str, dict[str, Any]]:
    info = json.loads(fetch(EXCHANGE_INFO))
    rows = {row.get("symbol"): row for row in info.get("symbols", [])}
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        row = rows.get(symbol)
        if not row:
            raise GateError(f"CONTRACT_NOT_FOUND:{symbol}")
        expected = (
            row.get("contractType") == "PERPETUAL"
            and row.get("status") == "TRADING"
            and row.get("quoteAsset") == "USDT"
            and row.get("marginAsset") == "USDT"
        )
        if not expected:
            raise GateError(f"CONTRACT_IDENTITY_REJECTED:{symbol}")
        result[symbol] = {
            "symbol": symbol,
            "contract_type": row["contractType"],
            "status": row["status"],
            "base_asset": row.get("baseAsset"),
            "quote_asset": row.get("quoteAsset"),
            "margin_asset": row.get("marginAsset"),
            "onboard_date_ms": row.get("onboardDate"),
        }
    return result


def parse_archive(payload: bytes, symbol: str, interval: str, now_ms: int) -> list[dict[str, Any]]:
    duration = TIMEFRAMES[interval]
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise GateError("ARCHIVE_CSV_CARDINALITY_INVALID")
            with zf.open(csv_names[0]) as stream:
                reader = csv.reader(io.TextIOWrapper(stream, encoding="utf-8"))
                candles = []
                for row in reader:
                    if not row or not row[0].isdigit():
                        continue
                    if len(row) < 12:
                        raise GateError("KLINE_ROW_TOO_SHORT")
                    ts, close_ts = int(row[0]), int(row[6])
                    vals = [float(row[i]) for i in (1, 2, 3, 4, 5, 7)]
                    op, hi, lo, cl, vol, quote_vol = vals
                    if ts % duration or close_ts < ts or close_ts >= ts + duration:
                        raise GateError("KLINE_TIMESTAMP_INVALID")
                    if close_ts >= now_ms:
                        continue
                    if min(op, hi, lo, cl) <= 0 or min(vol, quote_vol) < 0:
                        raise GateError("KLINE_VALUE_INVALID")
                    if hi < max(op, lo, cl) or lo > min(op, hi, cl):
                        raise GateError("KLINE_OHLC_INVALID")
                    candles.append({
                        "open_time_ms": ts, "close_time_ms": close_ts,
                        "open": op, "high": hi, "low": lo, "close": cl,
                        "volume_base": vol, "volume_quote": quote_vol,
                        "closed": True,
                    })
    except zipfile.BadZipFile as exc:
        raise GateError("ARCHIVE_NOT_ZIP") from exc
    candles.sort(key=lambda x: x["open_time_ms"])
    if not candles:
        raise GateError("NO_CLOSED_CANDLES")
    if len({x["open_time_ms"] for x in candles}) != len(candles):
        raise GateError("DUPLICATE_CANDLE")
    for a, b in zip(candles, candles[1:]):
        if b["open_time_ms"] - a["open_time_ms"] != duration:
            raise GateError("CANDLE_GAP")
    expected_count = 1 if interval == "1d" else 6
    if len(candles) != expected_count:
        raise GateError(f"EXPECTED_{expected_count}_CANDLES_GOT_{len(candles)}")
    return candles


def probe_one(symbol: str, interval: str, archive_date: str, now_ms: int) -> dict[str, Any]:
    filename = f"{symbol}-{interval}-{archive_date}.zip"
    url = f"{BASE}/{symbol}/{interval}/{filename}"
    checksum_url = url + ".CHECKSUM"
    checksum_bytes = fetch(checksum_url)
    checksum_parts = checksum_bytes.decode("ascii").strip().split()
    if not checksum_parts or len(checksum_parts[0]) != 64:
        raise GateError("CHECKSUM_FORMAT_INVALID")
    expected = checksum_parts[0].lower()
    if any(c not in "0123456789abcdef" for c in expected):
        raise GateError("CHECKSUM_HEX_INVALID")
    archive = fetch(url)
    actual = sha256(archive)
    if actual != expected:
        raise GateError("SHA256_MISMATCH")
    candles = parse_archive(archive, symbol, interval, now_ms)
    age = now_ms - int(candles[-1]["close_time_ms"])
    if age < 0 or age > MAX_STALENESS_MS:
        raise GateError(f"STALE:{age}")
    return {
        "symbol": symbol, "timeframe": interval.upper(),
        "status": "PASS", "provider": "binance_vision",
        "data_class": "DELAYED_HISTORICAL_ARCHIVE",
        "archive_date_utc": archive_date, "archive_url": url,
        "archive_sha256": actual, "archive_bytes": len(archive),
        "closed_candles": len(candles),
        "first_open_ms": candles[0]["open_time_ms"],
        "latest_open_ms": candles[-1]["open_time_ms"],
        "latest_close_ms": candles[-1]["close_time_ms"],
        "staleness_ms": age, "max_staleness_ms": MAX_STALENESS_MS,
    }


def run(universe_path: Path, output_path: Path, now_ms: int | None = None) -> dict[str, Any]:
    now_ms = now_ms if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    archive_date = (datetime.fromtimestamp(now_ms / 1000, timezone.utc).date() - timedelta(days=1)).isoformat()
    symbols = load_universe(universe_path)
    metadata_error = None
    try:
        contracts = verify_exchange_contracts(symbols)
        metadata_status = "VERIFIED"
    except Exception as exc:
        # آرشیو را مستقل از API اطلاعات قرارداد آزمایش می‌کنیم؛ اما بدون متادیتای زنده PASS نمی‌دهیم.
        contracts = {}
        metadata_status = "UNAVAILABLE"
        metadata_error = f"{type(exc).__name__}:{exc}"
    results: list[dict[str, Any]] = []
    tasks = [(symbol, interval) for symbol in symbols for interval in ("1d", "4h")]
    # محدودیت هم‌زمانی، از فشار غیرضروری روی سرویس عمومی جلوگیری می‌کند.
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(probe_one, symbol, interval, archive_date, now_ms): (symbol, interval)
            for symbol, interval in tasks
        }
        for future in as_completed(futures):
            symbol, interval = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({
                    "symbol": symbol, "timeframe": interval.upper(),
                    "status": "FAIL", "provider": "binance_vision",
                    "reason": f"{type(exc).__name__}:{exc}",
                })
    results.sort(key=lambda row: (row["symbol"], row["timeframe"]))
    passed = sum(x["status"] == "PASS" for x in results)
    failed = len(results) - passed
    contract_hash = sha256(json.dumps(contracts, sort_keys=True).encode())
    report = {
        "schema_version": "1.0.0",
        "artifact_type": "cfss_stage2_provider_gate_v1",
        "run_id": os.getenv("GITHUB_RUN_ID", "local-provider-gate"),
        "acquired_at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider": "binance_vision",
        "contract_metadata_provider": "binance_usdm_exchange_info",
        "universe_count": len(symbols),
        "timeframes": ["1D", "4H"],
        "expected_probes": 54,
        "passed_probes": passed,
        "failed_probes": failed,
        "max_staleness_ms": MAX_STALENESS_MS,
        "contract_metadata_status": metadata_status,
        "contract_metadata_error": metadata_error,
        "contract_metadata_sha256": contract_hash,
        "contract_metadata": contracts,
        "results": results,
        "signal_generation_enabled": False,
        "overall_status": "PASS" if metadata_status == "VERIFIED" and failed == 0 and passed == 54 else "FAIL",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"STAGE2_PROVIDER_GATE={report['overall_status']}")
    print(f"PROBES={passed}/54_PASS;FAIL={failed}")
    for row in results:
        print(f"{row['symbol']} {row['timeframe']} {row['status']} {row.get('staleness_ms', row.get('reason', ''))}")
    return report


if __name__ == "__main__":
    try:
        result = run(
            Path(sys.argv[1]) if len(sys.argv) > 1 else Path("signal_autopilot/data/stage1b_universe_27.json"),
            Path(sys.argv[2]) if len(sys.argv) > 2 else Path("artifacts/stage2-provider-gate.v1.json"),
        )
        raise SystemExit(0 if result["overall_status"] == "PASS" else 2)
    except Exception as exc:
        print(f"STAGE2_PROVIDER_GATE_FATAL:{type(exc).__name__}:{exc}", file=sys.stderr)
        raise SystemExit(3)
