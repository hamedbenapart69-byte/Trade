#!/usr/bin/env python3
"""Repeated live OHLCV microbenchmark with exact Go/Python output comparison."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
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
TIME_MARKER = "__P1A_RESOURCE_METRICS__"


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def run_json(command: list[str], payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, float]]:
    wrapped = ["/usr/bin/time", "-f", TIME_MARKER + "%M,%U,%S", *command]
    started = time.perf_counter()
    proc = subprocess.run(
        wrapped,
        input=(json.dumps(payload) if payload is not None else None),
        text=True,
        capture_output=True,
        check=False,
    )
    wall_seconds = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(f"command_failed:{command[0]}:{proc.stderr[-1500:]}")
    metrics_line = next((line for line in proc.stderr.splitlines() if line.startswith(TIME_MARKER)), None)
    if metrics_line is None:
        raise RuntimeError("resource_metrics_missing")
    rss_kb, user_cpu, system_cpu = metrics_line[len(TIME_MARKER):].split(",")
    return json.loads(proc.stdout), {
        "process_wall_seconds": wall_seconds,
        "max_rss_kb": float(rss_kb),
        "user_cpu_seconds": float(user_cpu),
        "system_cpu_seconds": float(system_cpu),
    }


def canonical(results: dict[str, Any]) -> dict[str, Any]:
    return {item["symbol"]: item for item in results.get("results", [])}


def compare_outputs(go: dict[str, Any], py: dict[str, Any], symbols: list[str], trial: int) -> dict[str, Any]:
    go_map, py_map = canonical(go), canonical(py)
    divergences = []
    for symbol in symbols:
        left, right = go_map.get(symbol), py_map.get(symbol)
        if left is None or right is None:
            divergences.append({"trial": trial, "symbol": symbol, "reason": "MISSING_RESULT"})
            continue
        if (left.get("status") != right.get("status")
                or left.get("provider") != right.get("provider")
                or left.get("volume_unit") != right.get("volume_unit")):
            divergences.append({
                "trial": trial, "symbol": symbol, "reason": "PROVIDER_STATUS_OR_UNIT_MISMATCH",
                "go_provider": left.get("provider"), "python_provider": right.get("provider"),
                "go_volume_unit": left.get("volume_unit"), "python_volume_unit": right.get("volume_unit"),
            })
            continue
        left_candles, right_candles = left.get("candles", []), right.get("candles", [])
        if left_candles != right_candles:
            first_diff = None
            for index, (go_candle, py_candle) in enumerate(zip(left_candles, right_candles)):
                if go_candle != py_candle:
                    first_diff = {"index": index, "go": go_candle, "python": py_candle}
                    break
            divergences.append({
                "trial": trial, "symbol": symbol, "reason": "CANDLE_BYTE_VALUE_MISMATCH",
                "go_count": len(left_candles), "python_count": len(right_candles),
                "first_difference": first_diff,
            })
    go_ok = sum(1 for item in go_map.values() if item.get("status") == "OK")
    py_ok = sum(1 for item in py_map.values() if item.get("status") == "OK")
    return {
        "trial": trial,
        "go_symbols_ok": go_ok,
        "python_symbols_ok": py_ok,
        "matched_symbols": len(symbols) - len(divergences),
        "divergence_count": len(divergences),
        "divergences": divergences,
        "go_output_sha256": hashlib.sha256(json.dumps(go, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "python_output_sha256": hashlib.sha256(json.dumps(py, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }


def summarize_resource(samples: list[dict[str, float]]) -> dict[str, float]:
    return {
        "median_process_wall_seconds": round(statistics.median(x["process_wall_seconds"] for x in samples), 6),
        "p95_process_wall_seconds": round(percentile95([x["process_wall_seconds"] for x in samples]), 6),
        "median_max_rss_kb": round(statistics.median(x["max_rss_kb"] for x in samples), 2),
        "median_user_cpu_seconds": round(statistics.median(x["user_cpu_seconds"] for x in samples), 6),
        "median_system_cpu_seconds": round(statistics.median(x["system_cpu_seconds"] for x in samples), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--go-binary", required=True)
    parser.add_argument("--symbols", default=os.getenv("P1A_SYMBOLS") or DEFAULT_SYMBOLS)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--output", default="p1a-benchmark.json")
    args = parser.parse_args()
    symbols = sorted({x.strip().upper() for x in args.symbols.split(",") if x.strip()})
    if not symbols:
        raise SystemExit("symbols_required")
    if args.repetitions < 3 or args.repetitions > 10:
        raise SystemExit("repetitions_must_be_between_3_and_10")
    if args.warmups < 0 or args.warmups > 3:
        raise SystemExit("warmups_must_be_between_0_and_3")

    as_of_ms = int(time.time() * 1000)
    request = {"symbols": symbols, "timeframe": "15m", "limit": args.limit, "as_of_ms": as_of_ms}
    python_command = [
        sys.executable, "scripts/p1a_python_reference.py",
        "--symbols", ",".join(symbols), "--limit", str(args.limit), "--as-of-ms", str(as_of_ms),
    ]

    for _ in range(args.warmups):
        run_json([args.go_binary], request)
        run_json(python_command)

    go_samples: list[dict[str, float]] = []
    py_samples: list[dict[str, float]] = []
    trials = []
    all_divergences = []
    for trial in range(1, args.repetitions + 1):
        go, go_metrics = run_json([args.go_binary], request)
        py, py_metrics = run_json(python_command)
        go_samples.append(go_metrics)
        py_samples.append(py_metrics)
        comparison = compare_outputs(go, py, symbols, trial)
        comparison["go_collection_seconds"] = go.get("collection_elapsed_ms", 0) / 1000
        comparison["python_collection_seconds"] = py.get("collection_elapsed_ms", 0) / 1000
        comparison["speedup_python_over_go"] = (
            comparison["python_collection_seconds"] / comparison["go_collection_seconds"]
            if comparison["go_collection_seconds"] > 0 else None
        )
        trials.append(comparison)
        all_divergences.extend(comparison["divergences"])

    go_collection = [x["go_collection_seconds"] for x in trials]
    py_collection = [x["python_collection_seconds"] for x in trials]
    speedups = [x["speedup_python_over_go"] for x in trials if x["speedup_python_over_go"] is not None]
    median_speedup = statistics.median(speedups) if speedups else None
    equivalence_passed = (
        not all_divergences
        and all(x["go_symbols_ok"] == x["python_symbols_ok"] for x in trials)
    )
    report = {
        "schema_version": "1.0.0",
        "classification": "LIVE_PUBLIC_API_BENCHMARK_NOT_PRODUCTION_EVIDENCE",
        "scope": "15m OHLCV for explicit symbols only; excludes production universe discovery, CoinGecko whitelist, liquidity/listing-age filters, full 13-provider cascade, 1h production collector, funding, open interest and strategy compute.",
        "comparison_model": "bounded concurrent Go collector (8 workers) versus sequential Python CCXT reference; this measures collection architecture/concurrency, not language-only CPU speed.",
        "symbols_requested": len(symbols),
        "shared_as_of_ms": as_of_ms,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "go": {
            "collection_median_seconds": round(statistics.median(go_collection), 6),
            "collection_p95_seconds": round(percentile95(go_collection), 6),
            "throughput_symbols_per_second_median": round(len(symbols) / statistics.median(go_collection), 4),
            **summarize_resource(go_samples),
            "symbols_ok_median": statistics.median(x["go_symbols_ok"] for x in trials),
        },
        "python_ccxt_reference": {
            "collection_median_seconds": round(statistics.median(py_collection), 6),
            "collection_p95_seconds": round(percentile95(py_collection), 6),
            "throughput_symbols_per_second_median": round(len(symbols) / statistics.median(py_collection), 4),
            **summarize_resource(py_samples),
            "symbols_ok_median": statistics.median(x["python_symbols_ok"] for x in trials),
            "ccxt_version": __import__("ccxt").__version__,
        },
        "speedup_median_python_over_go": round(median_speedup, 4) if median_speedup is not None else None,
        "equivalence": {
            "passed": equivalence_passed,
            "divergence_count_total": len(all_divergences),
            "trials_with_zero_divergence": sum(1 for x in trials if x["divergence_count"] == 0),
            "trials": trials,
        },
        "decision": (
            "RESEARCH_ONLY"
            if not equivalence_passed or median_speedup is None or median_speedup < 5
            else "MICROBENCHMARK_5X_PASS_FULL_PIPELINE_PARITY_AND_10X_PRODUCTION_GATES_REQUIRED"
        ),
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if equivalence_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
