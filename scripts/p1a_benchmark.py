#!/usr/bin/env python3
"""Compare Go concurrency prototype with the sequential CCXT reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_SYMBOLS = (
    "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,"
    "LINKUSDT,DOTUSDT,TRXUSDT,TONUSDT,SHIBUSDT,LTCUSDT,BCHUSDT,ETCUSDT,"
    "ATOMUSDT,NEARUSDT,APTUSDT,ARBUSDT,OPUSDT,INJUSDT,UNIUSDT,AAVEUSDT,"
    "FILUSDT,ICPUSDT,HBARUSDT,PEPEUSDT,SEIUSDT,SUIUSDT,TAOUSDT,RENDERUSDT,"
    "FTMUSDT,EOSUSDT,XTZUSDT,ALGOUSDT,CRVUSDT,MKRUSDT,COMPUSDT,IMXUSDT"
)


def run_json(command: list[str], payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    proc = subprocess.run(command, input=(json.dumps(payload) if payload is not None else None),
                          text=True, capture_output=True, check=False)
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(f"command_failed:{command[0]}:{proc.stderr[-1000:]}")
    return json.loads(proc.stdout), elapsed


def canonical(results: dict[str, Any]) -> dict[str, Any]:
    return {item["symbol"]: item for item in results.get("results", [])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-binary", required=True)
    parser.add_argument("--symbols", default=os.getenv("P1A_SYMBOLS") or DEFAULT_SYMBOLS)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default="p1a-benchmark.json")
    args = parser.parse_args()
    symbols = sorted({x.strip().upper() for x in args.symbols.split(",") if x.strip()})
    as_of_ms = int(time.time() * 1000)
    request = {"symbols": symbols, "timeframe": "15m", "limit": args.limit, "as_of_ms": as_of_ms}
    go, go_seconds = run_json([args.go_binary], request)
    py, py_seconds = run_json([sys.executable, "scripts/p1a_python_reference.py",
                               "--symbols", ",".join(symbols), "--limit", str(args.limit), "--as-of-ms", str(as_of_ms)])
    go_map, py_map = canonical(go), canonical(py)
    divergences = []
    for symbol in symbols:
        left, right = go_map.get(symbol), py_map.get(symbol)
        if left is None or right is None:
            divergences.append({"symbol": symbol, "reason": "MISSING_RESULT"})
        elif (left.get("status") != right.get("status") or left.get("provider") != right.get("provider")
              or left.get("volume_unit") != right.get("volume_unit")):
            divergences.append({"symbol": symbol, "reason": "PROVIDER_OR_STATUS_MISMATCH",
                                "go_provider": left.get("provider"), "python_provider": right.get("provider"),
                                "go_volume_unit": left.get("volume_unit"), "python_volume_unit": right.get("volume_unit")})
        elif left.get("candles") != right.get("candles"):
            divergences.append({"symbol": symbol, "reason": "CANDLE_BYTE_VALUE_MISMATCH",
                                "go_count": len(left.get("candles", [])),
                                "python_count": len(right.get("candles", []))})
    go_ok = sum(1 for x in go_map.values() if x.get("status") == "OK")
    py_ok = sum(1 for x in py_map.values() if x.get("status") == "OK")
    go_collection_seconds = go.get("collection_elapsed_ms", 0) / 1000
    py_collection_seconds = py.get("collection_elapsed_ms", 0) / 1000
    speedup = (py_collection_seconds / go_collection_seconds) if go_collection_seconds > 0 else None
    report = {
        "schema_version": "1.0.0",
        "classification": "LIVE_PUBLIC_API_BENCHMARK_NOT_PRODUCTION_EVIDENCE",
        "scope": "15m OHLCV fetch for explicit symbols only; excludes universe discovery, CoinGecko whitelist/liquidity/listing filters, funding, open interest and strategy compute. This is not a full MarketDataFetcher equivalence test.",
        "symbols_requested": len(symbols),
        "shared_as_of_ms": as_of_ms,
        "go": {"process_wall_seconds": round(go_seconds, 6), "collection_seconds": round(go_collection_seconds, 6), "symbols_ok": go_ok,
               "providers": sorted({x.get("provider") for x in go_map.values() if x.get("provider")})},
        "python_ccxt_reference": {"process_wall_seconds": round(py_seconds, 6), "collection_seconds": round(py_collection_seconds, 6), "symbols_ok": py_ok,
                                  "ccxt_version": __import__("ccxt").__version__},
        "speedup_python_over_go": round(speedup, 4) if speedup is not None else None,
        "timing_method": "collector_loop_only; excludes process startup and Python load_markets metadata setup",
        "equivalence": {"passed": len(divergences) == 0 and go_ok == py_ok,
                        "matched_symbols": len(symbols) - len(divergences),
                        "divergence_count": len(divergences), "divergences": divergences},
        "go_output_sha256": hashlib.sha256(json.dumps(go, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "python_output_sha256": hashlib.sha256(json.dumps(py, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "decision": "RESEARCH_ONLY" if divergences or speedup is None or speedup < 5 else "MICROBENCHMARK_THRESHOLD_MET_FULL_PIPELINE_GATE_STILL_REQUIRED",
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["equivalence"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
