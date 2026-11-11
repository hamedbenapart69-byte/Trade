#!/usr/bin/env python3
"""Sequential CCXT reference collector for the bounded P1-A OHLCV benchmark."""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from typing import Any

import ccxt


def canonical_symbol(exchange: Any, raw: str) -> str | None:
    base = raw[:-4]
    wanted = base + "/USDT:USDT"
    market = exchange.markets.get(wanted)
    if market and market.get("swap") and market.get("linear"):
        return wanted
    for symbol, item in exchange.markets.items():
        if (str(item.get("id", "")).upper() == raw.upper()
                and item.get("swap") and item.get("linear")
                and str(item.get("quote", "")).upper() == "USDT"):
            return symbol
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--as-of-ms", type=int, required=True)
    args = parser.parse_args()
    symbols = sorted({x.strip().upper() for x in args.symbols.split(",") if x.strip()})
    now_ms = args.as_of_ms
    providers: list[tuple[str, Any]] = []
    errors: dict[str, str] = {}
    for name, cls in (("okx", ccxt.okx), ("bybit", ccxt.bybit)):
        try:
            ex = cls({"enableRateLimit": True, "timeout": 15000,
                      "options": {"defaultType": "swap"}})
            ex.load_markets()
            providers.append((name, ex))
        except Exception as exc:
            errors[name] = type(exc).__name__
    results = []
    collection_started = time.perf_counter()
    for raw in symbols:
        item = {"symbol": raw, "timeframe": "15m", "provider": "",
                "data_classification": "UNAVAILABLE", "status": "UNAVAILABLE",
                "candles": [], "errors": []}
        for name, ex in providers:
            unified = canonical_symbol(ex, raw)
            if not unified:
                item["errors"].append(name + ":market_not_found")
                continue
            try:
                rows = ex.fetch_ohlcv(unified, timeframe="15m", limit=args.limit)
                candles = []
                seen = set()
                for row in rows:
                    if len(row) < 6:
                        raise ValueError("MALFORMED_OHLCV_ROW")
                    timestamp = int(row[0])
                    if timestamp % 900000 != 0:
                        raise ValueError("INVALID_CANDLE_TIMESTAMP")
                    if timestamp in seen:
                        raise ValueError("DUPLICATE_TIMESTAMP")
                    seen.add(timestamp)
                    candle = {
                        "timestamp": timestamp, "open": float(row[1]),
                        "high": float(row[2]), "low": float(row[3]),
                        "close": float(row[4]), "volume": float(row[5]),
                    }
                    values = [candle["open"], candle["high"], candle["low"],
                              candle["close"], candle["volume"]]
                    if not all(math.isfinite(v) for v in values):
                        raise ValueError("NON_FINITE_CANDLE_VALUE")
                    if (min(candle["open"], candle["high"], candle["low"], candle["close"]) <= 0
                            or candle["volume"] < 0
                            or candle["high"] < max(candle["open"], candle["close"], candle["low"])
                            or candle["low"] > min(candle["open"], candle["close"], candle["high"])):
                        raise ValueError("INVALID_OHLC_VALUE")
                    if timestamp + 900000 <= now_ms:
                        candles.append(candle)
                candles.sort(key=lambda x: x["timestamp"])
                for left, right in zip(candles, candles[1:]):
                    if right["timestamp"] - left["timestamp"] != 900000:
                        raise ValueError("DATA_GAP_OR_INTERVAL_ERROR")
                candles = candles[-args.limit:]
                if candles:
                    item.update(provider=name, data_classification="REAL", status="OK", candles=candles)
                    break
                item["errors"].append(name + ":no_closed_candles")
            except Exception as exc:
                item["errors"].append(name + ":" + str(exc))
        results.append(item)
    collection_elapsed_ms = int((time.perf_counter() - collection_started) * 1000)
    for _, ex in providers:
        try:
            ex.close()
        except Exception:
            pass
    json.dump({"schema_version": "1.0.0", "timeframe": "15m",
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "collection_elapsed_ms": collection_elapsed_ms,
               "results": results, "provider_init_errors": errors},
              sys.stdout, separators=(",", ":"), allow_nan=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
