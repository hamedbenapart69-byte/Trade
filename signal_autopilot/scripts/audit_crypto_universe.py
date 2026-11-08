"""Live audit of the crypto-only USDT perpetual universe."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.data_fetcher import MarketDataFetcher


def main() -> None:
    fetcher = MarketDataFetcher(limit=100)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": "CRYPTO_USDT_MARGined_PERPETUALS_ONLY",
        "providers": {},
    }
    try:
        whitelist = fetcher._coingecko_top_symbols()
        selected_provider = None
        selected_exchange = None
        selected = []
        union_by_symbol = {}
        providers = ["okx", "bybit", "binance", "bitget", "mexc", "kucoinfutures"]
        if os.getenv("DEBUG_BLOCK_OKX", "").strip() == "1":
            report["providers"]["okx"] = {"simulated_blocked": True, "reason": "DEBUG_BLOCK_OKX_FORCED"}
            providers.remove("okx")
        for provider in providers:
            try:
                exchange = fetcher._new_exchange(provider)
                rows = fetcher._eligible_markets(
                    exchange, provider, whitelist,
                    int(datetime.now(timezone.utc).timestamp() * 1000),
                )
                btc_market = exchange.markets.get("BTC/USDT:USDT") or {}
                for row in rows:
                    prior = union_by_symbol.get(row[1])
                    if prior is None or row[0] > prior[0]:
                        union_by_symbol[row[1]] = row
                report["providers"][provider] = {
                    "eligible_count": len(rows),
                    "diagnostics": fetcher.universe_diagnostics.get(provider, {}),
                    "btc_listing_metadata": {
                        "created": btc_market.get("created"),
                        "info_keys": sorted((btc_market.get("info") or {}).keys()),
                        "candidate_time_fields": {
                            key: (btc_market.get("info") or {}).get(key)
                            for key in ("listTime", "listingTime", "onboardDate", "launchTime",
                                        "createdTime", "createTime", "firstOpenDate", "createdAt",
                                        "openTime", "limitOpenTime", "isRwa")
                            if (btc_market.get("info") or {}).get(key) is not None
                        },
                    },
                }
                if provider == "okx" and len(rows) >= 50:
                    selected_provider, selected_exchange, selected = provider, exchange, rows
                    break
                if provider == "bybit":
                    if len(rows) >= len(selected):
                        selected_provider, selected_exchange, selected = provider, exchange, rows
                elif len(rows) > len(selected):
                    selected_provider, selected_exchange, selected = provider, exchange, rows
            except Exception as exc:
                report["providers"][provider] = {
                    "error": type(exc).__name__, "detail": str(exc)[:200]
                }
        report["coingecko_unique_whitelist_symbols"] = len(whitelist)
        report["selected_provider"] = selected_provider
        report["selected_count"] = len(selected)
        union_rows = sorted(union_by_symbol.values(), key=lambda row: row[0], reverse=True)
        report["unique_cross_exchange_union_count"] = len(union_rows)
        report["unique_cross_exchange_union_first_10"] = [
            {"symbol": symbol, "quote_volume_24h_usd": round(volume, 2)}
            for volume, symbol, _ in union_rows[:10]
        ]
        report["first_10"] = [
            {"symbol": symbol, "quote_volume_24h_usd": round(volume, 2)}
            for volume, symbol, _ in selected[:10]
        ]
        report["policy_checks"] = {
            "all_quote_usdt_linear_swaps": bool(selected_provider) and all(
                selected_exchange.market(symbol).get("swap")
                and selected_exchange.market(symbol).get("linear")
                and selected_exchange.market(symbol).get("quote") == "USDT"
                and selected_exchange.market(symbol).get("settle") == "USDT"
                for _, symbol, _ in selected
            ),
            "all_coin_gecko_whitelisted": all(
                selected_exchange.market(symbol).get("base", "").upper() in whitelist
                for _, symbol, _ in selected
            ),
            "all_over_10m_usd_volume": all(volume >= 10_000_000 for volume, _, _ in selected),
            "all_listed_at_least_730_days": all(
                (fetcher._listing_time_ms(selected_exchange.market(symbol), selected_provider) or 0)
                <= int(datetime.now(timezone.utc).timestamp() * 1000) - 730 * 86_400_000
                for _, symbol, _ in selected
            ),
            "count_at_least_50": len(selected) >= 50,
            "cross_exchange_union_at_least_50": len(union_rows) >= 50,
        }
        report["pass"] = all(report["policy_checks"].values())
        out = Path("data/universe_audit.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if not report["pass"]:
            raise SystemExit("CRYPTO_UNIVERSE_AUDIT_FAIL")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
