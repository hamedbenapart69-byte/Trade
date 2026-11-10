"""Read-only crypto USDT perpetual market data. No spot or tokenized-equity fallback."""
from __future__ import annotations

import json
import os
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
        parsed_created = market.get("created")
        try:
            parsed_created = int(parsed_created) if parsed_created is not None else None
        except (TypeError, ValueError):
            parsed_created = None
        if parsed_created and parsed_created > 0:
            return parsed_created
        keys = ("listTime", "listingTime", "onboardDate", "launchTime", "createdTime",
                "createTime", "firstOpenDate", "createdAt", "openTime", "limitOpenTime")
        if provider == "okx":
            keys = ("listTime", "listingTime")
        elif provider == "bybit":
            keys = ("launchTime", "createdTime", "listTime")
        elif provider == "binance":
            keys = ("onboardDate", "launchTime", "createdTime")
        elif provider in ("bitget", "mexc"):
            keys = ("launchTime", "listTime", "createdTime", "createTime", "createdAt",
                    "openTime", "limitOpenTime")
        elif provider == "kucoinfutures":
            keys = ("firstOpenDate", "launchTime", "createdAt")
        elif provider == "gateio":
            keys = ("create_time", "createTime", "first_list_time", "launchTime")
        elif provider == "toobit":
            keys = ("launchTime", "onboardDate", "createTime", "createdAt")
        for key in keys:
            raw = info.get(key)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if value > 0:
                # Normalize exchange metadata timestamps: some venues publish seconds, others milliseconds.
                return value * 1000 if value < 1_000_000_000_000 else value
        return None

    def _coingecko_top_symbols(self) -> set[str]:
        """Fail closed: whitelist comes only from CoinGecko's configured top-ranked crypto assets."""
        requested = max(50, int(self.universe.get("whitelist_count", 500)))
        per_page = 250  # CoinGecko public API page size cap.
        rows = []
        for page in range(1, (requested + per_page - 1) // per_page + 1):
            response = httpx.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc",
                        "per_page": per_page, "page": page, "sparkline": "false"},
                timeout=20,
            )
            response.raise_for_status()
            page_rows = response.json()
            if not isinstance(page_rows, list) or not page_rows:
                break
            rows.extend(page_rows)
        if len(rows) < min(requested, 100):
            raise RuntimeError("coingecko_crypto_whitelist_incomplete")
        rows = rows[:requested]
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
        elif provider == "bitget":
            exchange = ccxt.bitget({"enableRateLimit": True, "timeout": 25000,
                                    "options": {"defaultType": "swap"}})
        elif provider == "mexc":
            exchange = ccxt.mexc({"enableRateLimit": True, "timeout": 25000,
                                  "options": {"defaultType": "swap"}})
        elif provider == "kucoinfutures":
            exchange = ccxt.kucoinfutures({"enableRateLimit": True, "timeout": 25000})
        elif provider == "gateio":
            # CCXT's current unified exchange id/class is "gate", not "gateio".
            exchange = ccxt.gate({"enableRateLimit": True, "timeout": 25000,
                                  "options": {"defaultType": "swap"}})
        elif provider == "phemex":
            exchange = ccxt.phemex({"enableRateLimit": True, "timeout": 25000,
                                    "options": {"defaultType": "swap"}})
        elif provider == "bingx":
            exchange = ccxt.bingx({"enableRateLimit": True, "timeout": 25000,
                                   "options": {"defaultType": "swap"}})
        elif provider == "toobit":
            exchange = ccxt.toobit({"enableRateLimit": True, "timeout": 25000,
                                    "options": {"defaultType": "swap"}})
        else:
            raise ValueError("unsupported_futures_provider")
        self.exchanges.append(exchange)
        return exchange

    def _eligible_markets(
        self, exchange, provider: str, whitelist: set[str], now_ms: int,
        exclude_bases: set[str] | None = None, target_count: int | None = None,
    ):
        exclude_bases = {str(x).upper() for x in (exclude_bases or set())}
        target_count = self.limit if target_count is None else max(0, int(target_count))
        min_age_ms = int(self.universe.get("min_listing_age_days", 730)) * 86_400_000
        min_volume = float(self.universe.get("min_quote_volume_24h_usd", 10_000_000))
        quote = str(self.universe.get("quote", "USDT")).upper()
        settle = str(self.universe.get("settle", "USDT")).upper()
        blacklist = {str(x).upper() for x in self.universe.get("blacklist_patterns", [])}
        markets = exchange.load_markets()
        tickers = exchange.fetch_tickers()
        rejected = {"inactive": 0, "not_swap": 0, "not_linear": 0, "wrong_quote": 0,
                    "wrong_settle": 0, "not_contract": 0, "not_crypto_whitelist": 0,
                    "blacklisted": 0, "rwa_or_noncrypto_classification": 0,
                    "listing_time_missing": 0, "history_too_short": 0, "history_verified": 0,
                    "too_new": 0, "volume_below_10m": 0, "invalid_volume": 0,
                    "already_covered": 0}
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
            if base in exclude_bases:
                rejected["already_covered"] += 1
                continue
            market_id = str(market.get("id") or "").upper()
            info = market.get("info") or {}
            is_rwa = str(info.get("isRwa", "")).strip().lower() in ("1", "true", "yes")
            classification = " ".join(str(info.get(key, "")) for key in
                                       ("category", "instCategory", "symbolType", "type", "underlying")).lower()
            noncrypto_class = any(word in classification for word in
                                  ("stock", "equity", "index", "etf", "forex", "fiat", "commodity", "rwa"))
            if is_rwa or noncrypto_class:
                rejected["rwa_or_noncrypto_classification"] += 1
                continue
            if base in blacklist or market_id in blacklist:
                rejected["blacklisted"] += 1
                continue
            if base not in whitelist:
                rejected["not_crypto_whitelist"] += 1
                continue
            ticker = tickers.get(symbol) or {}
            qv = ticker.get("quoteVolume")
            if qv is None:
                ticker_info = ticker.get("info") or {}
                raw_base_volume = ticker_info.get("volCcy24h") or ticker.get("baseVolume")
                last_price = ticker.get("last") or ticker_info.get("last")
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
            listing_ms = self._listing_time_ms(market, provider)
            if listing_ms is None:
                rejected["listing_time_missing"] += 1
                # Missing listing metadata is verified against historical daily OHLCV,
                # but only after the asset has passed the liquidity threshold.
                try:
                    cutoff_ms = now_ms - min_age_ms
                    history = exchange.fetch_ohlcv(symbol, timeframe="1d", since=cutoff_ms, limit=1)
                    if not history or int(history[0][0]) > cutoff_ms + 7 * 86_400_000:
                        rejected["history_too_short"] += 1
                        continue
                    rejected["history_verified"] += 1
                except Exception:
                    rejected["history_too_short"] += 1
                    continue
            elif listing_ms > now_ms - min_age_ms:
                rejected["too_new"] += 1
                continue
            accepted.append((volume, symbol, ticker))
        accepted.sort(key=lambda item: item[0], reverse=True)
        self.universe_diagnostics[provider] = {
            "markets_total": len(markets), "eligible_before_limit": len(accepted),
            "selected": min(len(accepted), target_count), "target_remaining": target_count,
            "minimum_listing_age_days": min_age_ms // 86_400_000,
            "minimum_quote_volume_24h_usd": min_volume, "whitelist_source": "CoinGecko top 1000",
            "rejected": rejected,
        }
        return accepted[:target_count]

    @staticmethod
    def _completed_ohlcv(candles, now_ms: int):
        """مرتب‌سازی کندل‌ها و حذف کندل یک‌ساعتهٔ هنوز بسته‌نشده."""
        ordered = sorted(
            (c for c in candles if c[0] is not None),
            key=lambda candle: int(candle[0]),
        )
        return [c for c in ordered if int(c[0]) + 3_600_000 <= now_ms]

    def _fetch_from_provider(
        self, provider: str, whitelist: set[str],
        exclude_bases: set[str] | None = None, target_count: int | None = None,
    ):
        exchange = self._new_exchange(provider)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candidates = self._eligible_markets(
            exchange, provider, whitelist, now_ms,
            exclude_bases=exclude_bases, target_count=target_count,
        )
        output = []
        for qv, symbol, ticker in candidates:
            ticker_timestamp = ticker.get("timestamp")
            ticker_timestamp_source = "EXCHANGE"
            if ticker_timestamp is None and ticker.get("datetime"):
                try:
                    ticker_timestamp = int(datetime.fromisoformat(
                        str(ticker["datetime"]).replace("Z", "+00:00")
                    ).timestamp() * 1000)
                except (TypeError, ValueError):
                    ticker_timestamp = None
            if ticker_timestamp is None:
                # KuCoin Futures may omit exchange ticker timestamps; receipt time is an explicit PROXY.
                ticker_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
                ticker_timestamp_source = "FETCH_TIME_PROXY"
            row = {
                "base": str(exchange.market(symbol).get("base") or "").upper(),
                "provider": provider,
                "symbol": symbol, "last": ticker.get("last"), "quote_volume_24h": qv,
                "ticker_timestamp_utc": self._utc_ms(ticker_timestamp),
                "ticker_timestamp_source": ticker_timestamp_source, "ohlcv": None,
                "funding_rate": None, "funding_timestamp_utc": None, "funding_interval_hours": None,
                "open_interest": None, "open_interest_timestamp_utc": None,
                "availability": {"ohlcv": "UNAVAILABLE", "funding": "UNAVAILABLE",
                                 "open_interest": "UNAVAILABLE"}, "errors": [],
            }
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=70)
                completed = self._completed_ohlcv(candles, now_ms)
                row["ohlcv"] = [{
                    "timestamp": int(c[0]), "timestamp_utc": self._utc_ms(c[0]),
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                    "close": float(c[4]), "volume": float(c[5]),
                } for c in completed]
                if len(row["ohlcv"]) >= 52:
                    row["availability"]["ohlcv"] = "OK"
            except Exception as exc:
                row["errors"].append("ohlcv:" + type(exc).__name__)
            if row["availability"]["ohlcv"] != "OK":
                if not any(item.startswith("ohlcv:") for item in row["errors"]):
                    row["errors"].append("ohlcv:insufficient_completed_history")
                output.append(row)
                continue
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

    @staticmethod
    def _provider_error_status(exc: Exception) -> str:
        """Classify public API failures without mislabeling regional blocks as rate limits."""
        message = str(exc).lower()
        if ("block access from your country" in message
                or "restricted location" in message
                or "451" in message):
            return "BLOCKED_REGION"
        if ("rate limit" in message or "too many requests" in message or "429" in message):
            return "RATE_LIMITED"
        return "ERROR"

    def fetch(self):
        # CoinGecko defines eligible crypto assets; exchange fallback fills
        # missing symbols one-by-one without mixing OHLCV across venues.
        whitelist = self._coingecko_top_symbols()
        errors: dict[str, str] = {}
        selected: dict[str, dict] = {}
        providers = [
            "okx", "bybit", "binance", "bitget", "mexc",
            "kucoinfutures", "gateio", "phemex", "bingx", "toobit",
        ]
        provider_diagnostics: dict[str, dict] = {}
        if os.getenv("DEBUG_BLOCK_OKX", "").strip() == "1":
            errors["okx"] = "DEBUG_BLOCK_OKX_FORCED"
            provider_diagnostics["okx"] = {
                "status": "BLOCKED", "error": "DEBUG_BLOCK_OKX_FORCED",
                "symbols_added": 0,
            }
            providers.remove("okx")

        for provider in providers:
            remaining = self.limit - len(selected)
            if remaining <= 0:
                break
            try:
                rows = self._fetch_from_provider(
                    provider, whitelist,
                    exclude_bases=set(selected),
                    target_count=remaining,
                )
                added = 0
                duplicates = 0
                ohlcv_unavailable = 0
                for row in rows:
                    symbol = str(row.get("symbol") or "")
                    base = str(row.get("base") or symbol.split("/", 1)[0]).upper()
                    if not base:
                        continue
                    if base in selected:
                        duplicates += 1
                        continue
                    if (row.get("availability") or {}).get("ohlcv") != "OK":
                        ohlcv_unavailable += 1
                        continue
                    row["base"] = base
                    row["provider"] = str(row.get("provider") or provider)
                    selected[base] = row
                    added += 1
                    if len(selected) >= self.limit:
                        break
                provider_diagnostics[provider] = {
                    **self.universe_diagnostics.get(provider, {}),
                    "rows_returned": len(rows),
                    "symbols_added": added,
                    "duplicates_skipped": duplicates,
                    "ohlcv_unavailable": ohlcv_unavailable,
                }
            except Exception as exc:
                errors[provider] = type(exc).__name__ + ":" + str(exc)[:180]
                provider_diagnostics[provider] = {
                    **self.universe_diagnostics.get(provider, {}),
                    "status": self._provider_error_status(exc),
                    "error": errors[provider],
                    "symbols_added": 0,
                }

        rows = list(selected.values())
        provider_sources = list(dict.fromkeys(row["provider"] for row in rows))
        chosen = (
            provider_sources[0] if len(provider_sources) == 1
            else ("multi-provider" if provider_sources else "none")
        )
        return {
            "provider": chosen,
            "provider_sources": provider_sources,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbols_requested": self.limit,
            "symbols_processed": len(rows),
            "symbols": rows,
            "fallback_used": len(provider_sources) > 1 or (bool(provider_sources) and provider_sources[0] != "okx"),
            "primary_error": errors.get("okx"),
            "errors": errors,
            "universe_policy": "CRYPTO_USDT_MARGined_PERPETUALS_ONLY",
            "universe_diagnostics": provider_diagnostics,
            "coingecko_whitelist_count": len(whitelist),
            "universe_under_50": len(rows) < min(50, self.limit),
        }
