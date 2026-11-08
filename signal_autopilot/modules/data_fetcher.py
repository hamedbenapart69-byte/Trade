"""Read-only crypto USDT perpetual market data. No spot or tokenized-equity fallback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import httpx


class MarketDataFetcher:
    def __init__(self, limit: int = 100, config_path: str | Path | None = None):
        self.limit = limit
        self.config_path = Path(config_path) if config_path else Path(__file__).resolve().parents[1] / "config.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.universe = self.config["market_data"]["universe"]
        self.exchanges = []
        self.exchange = None
        self.universe_diagnostics = {}

    def close(self):
        for exchange in self.exchanges:
            try:
                exchange.close()
            except Exception:
                pass

    @staticmethod
    def _utc_ms(value):
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).isoformat() if value is not None else None

    @staticmethod
    def _listing_time_ms(market: dict, provider: str) -> int | None:
        info = market.get("info") or {}
        keys = ("listTime", "listingTime", "onboardDate", "launchTime", "createdTime")
        if provider == "okx":
            keys = ("listTime", "listingTime")
        elif provider == "bybit":
            keys = ("launchTime", "createdTime", "listTime")
        elif provider == "binance":
            keys = ("onboardDate", "launchTime", "createdTime")
        for key in keys:
            raw = info.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                # Exchange metadata timestamps are milliseconds for supported perpetual instruments.
                return value
        return None

    def _coingecko_top_symbols(self) -> set[str]:
        """Fail closed: whitelist comes only from CoinGecko's top-200 crypto assets."""
        response = httpx.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "order": "market_cap_desc",
                    "per_page": int(self.universe.get("whitelist_count", 200)), "page": 1,
                    "sparkline": "false"},
            timeout=20,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or len(rows) < 50:
            raise RuntimeError("coingecko_top200_whitelist_incomplete")
        counts = {}
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            if symbol:
                counts[symbol] = counts.get(symbol, 0) + 1
        # Ambiguous CoinGecko tickers are excluded to reduce symbol-collision risk.
        return {symbol for symbol, count in counts.items() if count == 1}

    def _new_exchange(self, provider: str):
        if provider == "okx":
            exchange = ccxt.okx({"enableRateLimit": True, "timeout": 25000,
                                 "options": {"defaultType": "swap"}})
        elif provider == "bybit":
            exchange = ccxt.bybit({"enableRateLimit": True, "timeout": 25000,
                                   "options": {"defaultType": "swap"}})
        elif provider == "binance":
            exchange = ccxt.binanceusdm({"enableRateLimit": True, "timeout": 25000,
                                         "options": {"defaultType": "future"}})
        else:
            raise ValueError("unsupported_futures_provider")
        self.exchanges.append(exchange)
        return exchange

    def _eligible_markets(self, exchange, provider: str, whitelist: set[str], now_ms: int):
        min_age_ms = int(self.universe.get("min_listing_age_days", 730)) * 86_400_000
        min_volume = float(self.universe.get("min_quote_volume_24h_usd", 10_000_000))
        quote = str(self.universe.get("quote", "USDT")).upper()
        settle = str(self.universe.get("settle", "USDT")).upper()
        blacklist = {str(x).upper() for x in self.universe.get("blacklist_patterns", [])}
        markets = exchange.load_markets()
        tickers = exchange.fetch_tickers()
        rejected = {"inactive": 0, "not_swap": 0, "not_linear": 0, "wrong_quote": 0,
                    "wrong_settle": 0, "not_contract": 0, "not_crypto_whitelist": 0,
                    "blacklisted": 0, "listing_time_missing": 0, "too_new": 0,
                    "volume_below_10m": 0, "invalid_volume": 0}
        accepted = []
        for symbol, market in markets.items():
            if not market.get("active"):
                rejected["inactive"] += 1
                continue
            if not market.get("swap"):
                rejected["not_swap"] += 1
                continue
            if not market.get("linear"):
                rejected["not_linear"] += 1
                continue
            if str(market.get("quote") or "").upper() != quote:
                rejected["wrong_quote"] += 1
                continue
            if str(market.get("settle") or "").upper() != settle:
                rejected["wrong_settle"] += 1
                continue
            if not market.get("contract"):
                rejected["not_contract"] += 1
                continue
            base = str(market.get("base") or "").upper()
            market_id = str(market.get("id") or "").upper()
            if base in blacklist or market_id in blacklist:
                rejected["blacklisted"] += 1
                continue
            if base not in whitelist:
                rejected["not_crypto_whitelist"] += 1
                continue
            listing_ms = self._listing_time_ms(market, provider)
            if listing_ms is None:
                rejected["listing_time_missing"] += 1
                continue
            if listing_ms > now_ms - min_age_ms:
                rejected["too_new"] += 1
                continue
            ticker = tickers.get(symbol) or {}
            qv = ticker.get("quoteVolume")
            if qv is None:
                info = ticker.get("info") or {}
                raw_base_volume = info.get("volCcy24h") or ticker.get("baseVolume")
                last_price = ticker.get("last") or info.get("last")
                try:
                    qv = float(raw_base_volume) * float(last_price)
                except (TypeError, ValueError):
                    qv = None
            try:
                volume = float(qv)
            except (TypeError, ValueError):
                volume = 0.0
            if volume < min_volume:
                rejected["volume_below_10m"] += 1
                continue
            if not (volume > 0):
                rejected["invalid_volume"] += 1
                continue
            accepted.append((volume, symbol, ticker))
        accepted.sort(key=lambda item: item[0], reverse=True)
        self.universe_diagnostics[provider] = {
            "markets_total": len(markets), "eligible_before_limit": len(accepted),
            "selected": min(len(accepted), self.limit), "minimum_listing_age_days": min_age_ms // 86_400_000,
            "minimum_quote_volume_24h_usd": min_volume, "whitelist_source": "CoinGecko top 200",
            "rejected": rejected,
        }
        return accepted[:self.limit]

    def _fetch_from_provider(self, provider: str, whitelist: set[str]):
        exchange = self._new_exchange(provider)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candidates = self._eligible_markets(exchange, provider, whitelist, now_ms)
        output = []
        for qv, symbol, ticker in candidates:
            row = {
                "symbol": symbol, "last": ticker.get("last"), "quote_volume_24h": qv,
                "ticker_timestamp_utc": self._utc_ms(ticker.get("timestamp")), "ohlcv": None,
                "funding_rate": None, "funding_timestamp_utc": None, "funding_interval_hours": None,
                "open_interest": None, "open_interest_timestamp_utc": None,
                "availability": {"ohlcv": "UNAVAILABLE", "funding": "UNAVAILABLE",
                                 "open_interest": "UNAVAILABLE"}, "errors": [],
            }
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=70)
                completed = [c for c in candles if c[0] is not None and int(c[0]) + 3_600_000 <= now_ms]
                row["ohlcv"] = [{
                    "timestamp": int(c[0]), "timestamp_utc": self._utc_ms(c[0]),
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                    "close": float(c[4]), "volume": float(c[5]),
                } for c in completed]
                if len(row["ohlcv"]) >= 52:
                    row["availability"]["ohlcv"] = "OK"
            except Exception as exc:
                row["errors"].append("ohlcv:" + type(exc).__name__)
            try:
                funding = exchange.fetch_funding_rate(symbol)
                rate = funding.get("fundingRate")
                # Never convert missing/invalid funding to zero.
                if rate is not None:
                    row["funding_rate"] = float(rate)
                    row["funding_timestamp_utc"] = self._utc_ms(funding.get("timestamp"))
                    interval = (exchange.market(symbol).get("info") or {}).get("fundingInterval")
                    try:
                        row["funding_interval_hours"] = float(interval) / 3_600_000 if interval else None
                    except (TypeError, ValueError):
                        row["funding_interval_hours"] = None
                    row["availability"]["funding"] = "OK"
                else:
                    row["errors"].append("funding:missing_rate")
            except Exception as exc:
                row["errors"].append("funding:" + type(exc).__name__)
            try:
                oi = exchange.fetch_open_interest(symbol)
                value = oi.get("openInterestAmount", oi.get("openInterestValue"))
                if value is not None:
                    row["open_interest"] = float(value)
                    row["open_interest_timestamp_utc"] = self._utc_ms(oi.get("timestamp"))
                    row["availability"]["open_interest"] = "OK"
            except Exception as exc:
                row["errors"].append("open_interest:" + type(exc).__name__)
            output.append(row)
        return output

    def fetch(self):
        # CoinGecko is used only to establish crypto-asset membership, never as spot-price fallback.
        whitelist = self._coingecko_top_symbols()
        errors = {}
        results = {}
        for provider in ("okx", "bybit", "binance"):
            try:
                rows = self._fetch_from_provider(provider, whitelist)
                results[provider] = rows
                if provider == "okx" and len(rows) >= 50:
                    chosen = provider
                    break
                if provider == "bybit":
                    chosen = max(results, key=lambda key: len(results[key]))
                    break
            except Exception as exc:
                errors[provider] = type(exc).__name__ + ":" + str(exc)[:180]
        else:
            chosen = max(results, key=lambda key: len(results[key])) if results else None
        rows = results.get(chosen, []) if chosen else []
        if not rows:
            return {
                "provider": "none", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "symbols_requested": self.limit, "symbols_processed": 0, "symbols": [],
                "fallback_used": True, "errors": errors or {"universe": "no_crypto_usdt_perpetual_passed_filters"},
                "universe_policy": "CRYPTO_USDT_MARGined_PERPETUALS_ONLY",
                "universe_diagnostics": self.universe_diagnostics,
            }
        return {
            "provider": chosen, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbols_requested": self.limit, "symbols_processed": len(rows), "symbols": rows,
            "fallback_used": chosen != "okx", "primary_error": errors.get("okx"),
            "universe_policy": "CRYPTO_USDT_MARGined_PERPETUALS_ONLY",
            "universe_diagnostics": self.universe_diagnostics,
            "coingecko_whitelist_count": len(whitelist),
            "universe_under_50": len(rows) < 50,
        }
