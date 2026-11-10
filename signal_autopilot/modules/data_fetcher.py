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
            exchange = ccxt.gateio({"enableRateLimit": True, "timeout": 25000,
                                    "options": {"defaultType": "swap"}})
        elif provider == "toobit":
            exchange = ccxt.toobit({"enableRateLimit": True, "timeout": 25000,
                                    "options": {"defaultType": "swap"}})
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
                    "blacklisted": 0, "rwa_or_noncrypto_classification": 0,
                    "listing_time_missing": 0, "history_too_short": 0, "history_verified": 0,
                    "too_new": 0, "volume_below_10m": 0, "invalid_volume": 0}
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
            "selected": min(len(accepted), self.limit), "minimum_listing_age_days": min_age_ms // 86_400_000,
            "minimum_quote_volume_24h_usd": min_volume, "whitelist_source": "CoinGecko top 1000",
            "rejected": rejected,
        }
        return accepted[:self.limit]

    @staticmethod
    def _fetch_ohlcv_paged(exchange, symbol: str, timeframe: str,
                           required_completed: int, interval_ms: int, now_ms: int):
        """دریافت تاریخچهٔ کامل با صفحه‌بندی؛ محدودیت سقف کندل هر صرافی را دور می‌زند."""
        page_size = 300  # سقف محافظه‌کارانه برای سازگاری با APIهای مختلف
        target_count = required_completed + 1  # یک کندل اضافه برای حذف کندل باز جاری
        cursor = now_ms - (target_count + 2) * interval_ms
        collected = {}
        max_pages = (target_count + page_size - 1) // page_size + 2

        for _ in range(max_pages):
            remaining = target_count - len(collected)
            if remaining <= 0:
                break
            request_limit = min(page_size, remaining)
            batch = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=cursor, limit=request_limit
            ) or []
            if not batch:
                break
            ordered = sorted(batch, key=lambda candle: int(candle[0]))
            previous_count = len(collected)
            for candle in ordered:
                if candle and candle[0] is not None:
                    collected[int(candle[0])] = candle
            newest = max(int(candle[0]) for candle in ordered if candle and candle[0] is not None)
            if len(collected) == previous_count or newest < cursor:
                break  # ارائه‌دهنده صفحهٔ تکراری داده یا cursor را رعایت نکرده است
            cursor = newest + interval_ms
            if len(collected) >= target_count or len(batch) < request_limit:
                break

        return [collected[key] for key in sorted(collected)][-target_count:]

    @staticmethod
    def _completed_ohlcv(candles, now_ms: int, interval_ms: int = 3_600_000):
        """مرتب‌سازی و حذف آخرین کندل بسته‌نشده با توجه به تایم‌فریم."""
        ordered = sorted(
            (c for c in candles if c[0] is not None),
            key=lambda candle: int(candle[0]),
        )
        return [c for c in ordered if int(c[0]) + interval_ms <= now_ms]

    def _fetch_from_provider(self, provider: str, whitelist: set[str]):
        exchange = self._new_exchange(provider)
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        candidates = self._eligible_markets(exchange, provider, whitelist, now_ms)
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
                "symbol": symbol, "last": ticker.get("last"), "quote_volume_24h": qv,
                "ticker_timestamp_utc": self._utc_ms(ticker_timestamp),
                "ticker_timestamp_source": ticker_timestamp_source, "ohlcv": None, "ohlcv_4h": None,
                "funding_rate": None, "funding_timestamp_utc": None, "funding_interval_hours": None,
                "open_interest": None, "open_interest_timestamp_utc": None,
                "availability": {"ohlcv": "UNAVAILABLE", "ohlcv_4h": "UNAVAILABLE",
                                 "funding": "UNAVAILABLE", "open_interest": "UNAVAILABLE"}, "errors": [],
            }
            try:
                candles = exchange.fetch_ohlcv(symbol, timeframe="1h", limit=210)
                completed = self._completed_ohlcv(candles, now_ms)
                row["ohlcv"] = [{
                    "timestamp": int(c[0]), "timestamp_utc": self._utc_ms(c[0]),
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                    "close": float(c[4]), "volume": float(c[5]),
                } for c in completed]
                if len(row["ohlcv"]) >= 200:
                    row["availability"]["ohlcv"] = "OK"
            except Exception as exc:
                row["errors"].append("ohlcv:" + type(exc).__name__)
            try:
                candles_4h = self._fetch_ohlcv_paged(
                    exchange, symbol, timeframe="4h", required_completed=700,
                    interval_ms=14_400_000, now_ms=now_ms,
                )
                completed_4h = self._completed_ohlcv(candles_4h, now_ms, interval_ms=14_400_000)
                row["ohlcv_4h"] = [{
                    "timestamp": int(c[0]), "timestamp_utc": self._utc_ms(c[0]),
                    "open": float(c[1]), "high": float(c[2]), "low": float(c[3]),
                    "close": float(c[4]), "volume": float(c[5]),
                } for c in completed_4h]
                if len(row["ohlcv_4h"]) >= 700:
                    row["availability"]["ohlcv_4h"] = "OK"
            except Exception as exc:
                row["errors"].append("ohlcv_4h:" + type(exc).__name__)
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
        providers = ["okx", "bybit", "binance", "bitget", "mexc", "kucoinfutures"]
        if os.getenv("DEBUG_BLOCK_OKX", "").strip() == "1":
            errors["okx"] = "DEBUG_BLOCK_OKX_FORCED"
            providers.remove("okx")
        qualified_counts = {}
        for provider in providers:
            try:
                rows = self._fetch_from_provider(provider, whitelist)
                results[provider] = rows
                qualified = sum(
                    1 for row in rows
                    if isinstance(row, dict)
                    and (row.get("availability") or {}).get("ohlcv") == "OK"
                    and (row.get("availability") or {}).get("ohlcv_4h") == "OK"
                )
                qualified_counts[provider] = qualified
                if qualified < 50:
                    errors[provider] = f"INSUFFICIENT_1H_4H_COVERAGE:{qualified}/50"
                if qualified >= 50:
                    chosen = provider
                    break
            except Exception as exc:
                errors[provider] = type(exc).__name__ + ":" + str(exc)[:180]
        else:
            chosen = max(qualified_counts, key=qualified_counts.get) if qualified_counts else None
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
            "symbols_with_1h_4h": qualified_counts.get(chosen, 0),
            "universe_under_50": qualified_counts.get(chosen, 0) < 50,
        }
