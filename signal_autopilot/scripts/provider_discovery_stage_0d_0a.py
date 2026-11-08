#!/usr/bin/env python3
"""Read-only Stage 0d.0a provider inventory; no production modules are modified."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.data_fetcher import MarketDataFetcher

def probe_url(name: str, url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Trade-Provider-Discovery/1.0"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return {"name": name, "status": response.status,
                    "elapsed_ms": round((time.time() - started) * 1000),
                    "content_length": response.headers.get("Content-Length")}
    except urllib.error.HTTPError as exc:
        return {"name": name, "status": exc.code, "elapsed_ms": round((time.time() - started) * 1000)}
    except Exception as exc:
        return {"name": name, "error": type(exc).__name__, "detail": str(exc)[:180],
                "elapsed_ms": round((time.time() - started) * 1000)}

def main() -> None:
    fetcher = MarketDataFetcher(limit=100)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_branch": "diagnostics/provider-discovery-v1",
        "production_code_modified": False,
        "current_config": fetcher.config["market_data"],
        "providers": {},
        "binance_vision": [],
        "notes": [
            "Eligible counts use the repository's CURRENT filters (730-day perpetual metadata/history fallback and $10M quote volume), not proposed v2.6.2 thresholds.",
            "The $50M subset is derived from current-filter survivors; it is not a production filter change.",
            "A successful plugin call does not prove GitHub Actions network access."
        ]
    }
    whitelist = set()
    try:
        whitelist = fetcher._coingecko_top_symbols()
        report["coingecko_unique_whitelist_count"] = len(whitelist)
    except Exception as exc:
        report["coingecko_whitelist_error"] = type(exc).__name__ + ":" + str(exc)[:180]

    provider_order = ["okx", "bybit", "binance", "bitget", "mexc", "kucoinfutures", "gateio", "toobit"]
    for provider in provider_order:
        try:
            exchange = fetcher._new_exchange(provider)
            markets = exchange.load_markets()
            tickers = exchange.fetch_tickers()
            rows = fetcher._eligible_markets(exchange, provider, whitelist, now_ms)
            report["providers"][provider] = {
                "markets_received": len(markets),
                "tickers_received": len(tickers),
                "eligible_current_filters_10m": len(rows),
                "eligible_if_volume_50m": sum(1 for volume, _, _ in rows if volume >= 50_000_000),
                "eligible_symbols_current_filters": [symbol for _, symbol, _ in rows],
                "diagnostics": fetcher.universe_diagnostics.get(provider, {}),
            }
        except Exception as exc:
            report["providers"][provider] = {
                "error": type(exc).__name__, "detail": str(exc)[:240]
            }

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        for kind, suffix in (
            ("klines_1h", f"klines/{symbol}/1h/{symbol}-1h-{month}.zip"),
            ("aggTrades", f"aggTrades/{symbol}/{symbol}-aggTrades-{month}.zip"),
        ):
            url = f"https://data.binance.vision/data/futures/um/monthly/{suffix}"
            report["binance_vision"].append(probe_url(f"{symbol}_{kind}", url))

    # Public USD-M FAPI market inventory from GitHub Runner.
    report["binance_fapi"] = probe_url(
        "binance_fapi_exchange_info",
        "https://fapi.binance.com/fapi/v1/exchangeInfo"
    )
    Path("provider-discovery-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    fetcher.close()

if __name__ == "__main__":
    main()
