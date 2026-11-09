"""دریافت کندل‌های عمومی ۱۵ دقیقه‌ای با fallback بین صرافی‌ها؛ فقط دادهٔ read-only."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import ccxt
import httpx

LOG = logging.getLogger(__name__)
INTERVAL_MS = 15 * 60 * 1000
MIN_BARS_FOR_ENGINE = 500
BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"


def is_closed_candle(open_time_ms: int, interval_ms: int, now_ms: int) -> bool:
    """کندل فقط وقتی بسته است که زمان بازشدن + بازه از اکنون عبور کرده باشد."""
    return int(open_time_ms) + int(interval_ms) <= int(now_ms)


def _row_from_binance(raw: list[Any]) -> dict[str, Any]:
    return {
        "open_time": int(raw[0]),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "taker_buy_base": float(raw[9]),
        "data_source": "BINANCE_FAPI_PUBLIC_KLINE",
        "cvd_source": "KLINE_TAKER_BUY_PROXY",
    }


class OHLCVBundle(list):
    """لیست سازگار با مصرف‌کنندهٔ قبلی، همراه تاریخچهٔ آماری و داده‌های مشتقه."""

    def __init__(self, live_15m, stats_1h, okx_metrics):
        super().__init__(live_15m)
        self.stats_1h = stats_1h
        self.okx_metrics = okx_metrics


class LiveOHLCVFetcher:
    """دریافت ۱۵m از Binance Futures عمومی؛ در خطا fallback به صرافی‌های عمومی CCXT."""

    def __init__(self, limit: int = 500, stats_limit: int = 2500, timeout: float = 25.0):
        self.limit = max(int(limit), MIN_BARS_FOR_ENGINE)
        self.stats_limit = max(int(stats_limit), 2500)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.exchanges: dict[str, Any] = {}
        self.market_cache: dict[str, dict[str, Any]] = {}
        self.provider_names = ("okx", "bybit", "kucoinfutures", "mexc", "bitget")

    def close(self) -> None:
        self.client.close()
        for exchange in self.exchanges.values():
            try:
                exchange.close()
            except Exception:
                LOG.exception("Exchange close failed: %s", getattr(exchange, "id", "unknown"))

    def _binance(self, symbol: str, now_ms: int) -> list[dict[str, Any]]:
        response = self.client.get(
            BINANCE_KLINES_URL,
            params={"symbol": symbol, "interval": "15m", "limit": min(self.limit, 1500)},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("binance_klines_payload_not_list")

        rows = []
        for raw in payload:
            if not isinstance(raw, list) or len(raw) < 10:
                continue
            if int(raw[6]) < now_ms and is_closed_candle(int(raw[0]), INTERVAL_MS, now_ms):
                rows.append(_row_from_binance(raw))

        rows.sort(key=lambda item: item["open_time"])
        deduped = {row["open_time"]: row for row in rows}
        result = list(deduped.values())
        if len(result) < MIN_BARS_FOR_ENGINE:
            raise ValueError(f"binance_history_short:{len(result)}")
        return result[-self.limit:]

    def _exchange(self, provider: str):
        if provider in self.exchanges:
            return self.exchanges[provider]
        constructor = getattr(ccxt, provider)
        exchange = constructor({
            "enableRateLimit": True,
            "timeout": 30000,
            "options": {"defaultType": "swap"},
        })
        exchange.load_markets()
        self.exchanges[provider] = exchange
        return exchange

    @staticmethod
    def _find_market(exchange, symbol: str) -> dict[str, Any]:
        base = symbol[:-4] if symbol.endswith("USDT") else symbol
        candidates = []
        for market in exchange.markets.values():
            if not market.get("active", True):
                continue
            if not market.get("swap") or not market.get("linear"):
                continue
            if str(market.get("base", "")).upper() != base:
                continue
            if str(market.get("quote", "")).upper() != "USDT":
                continue
            if str(market.get("settle", "")).upper() != "USDT":
                continue
            candidates.append(market)
        if not candidates:
            raise ValueError(f"linear_usdt_perpetual_not_found:{symbol}")
        return candidates[0]

    def _from_ccxt(self, provider: str, symbol: str, now_ms: int) -> list[dict[str, Any]]:
        exchange = self._exchange(provider)
        market = self._find_market(exchange, symbol)
        since = (now_ms // INTERVAL_MS) * INTERVAL_MS - self.limit * INTERVAL_MS
        cursor = since
        collected: dict[int, list[Any]] = {}

        for _ in range(6):
            remaining = self.limit - len(collected)
            if remaining <= 0:
                break
            batch = exchange.fetch_ohlcv(
                market["symbol"],
                timeframe="15m",
                since=cursor,
                limit=min(1000, remaining),
            )
            if not batch:
                break
            newest = cursor
            for candle in batch:
                if len(candle) < 6 or candle[0] is None:
                    continue
                open_time = int(candle[0])
                if open_time + INTERVAL_MS <= now_ms:
                    collected[open_time] = candle
                newest = max(newest, open_time)
            next_cursor = newest + INTERVAL_MS
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            time.sleep(max(float(getattr(exchange, "rateLimit", 0)) / 1000, 0.05))

        candles = [collected[key] for key in sorted(collected)]
        if len(candles) < MIN_BARS_FOR_ENGINE:
            raise ValueError(f"{provider}_history_short:{len(candles)}")

        rows = []
        for candle in candles[-self.limit:]:
            rows.append({
                "open_time": int(candle[0]),
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
                "data_source": f"CCXT_{provider.upper()}_PUBLIC_OHLCV",
                # OHLCV عمومی CCXT، taker-buy volume را ارائه نمی‌کند؛ CVD جعل نمی‌شود.
                "cvd_source": "UNAVAILABLE_NEUTRAL_PROXY",
            })
        return rows

    def _okx_candles(self, symbol: str, timeframe: str, limit: int, now_ms: int) -> list[dict[str, Any]]:
        """دریافت صفحه‌ای کندل‌های بسته‌شدهٔ SWAP از OKX؛ هیچ کندل باز پذیرفته نمی‌شود."""
        base = symbol[:-4] if symbol.upper().endswith("USDT") else symbol.upper()
        inst_id = f"{base}-USDT-SWAP"
        interval_ms = 3_600_000 if timeframe == "1H" else 900_000
        collected: dict[int, dict[str, Any]] = {}
        cursor: int | None = None
        endpoint = "/api/v5/market/candles"
        page_size = 300
        for _ in range((limit + 99) // 100 + 5):
            params = {"instId": inst_id, "bar": timeframe, "limit": str(page_size)}
            if cursor is not None:
                params["after"] = str(cursor)
            response = self.client.get("https://www.okx.com" + endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "0":
                raise ValueError(f"okx_{timeframe}_candles_code:{payload.get('code')}:{payload.get('msg')}")
            data = payload.get("data") or []
            if not data and endpoint.endswith("/market/candles"):
                endpoint = "/api/v5/market/history-candles"
                page_size = 100
                continue
            if not data:
                break
            oldest = None
            for raw in data:
                if not isinstance(raw, list) or len(raw) < 9:
                    continue
                ts = int(raw[0])
                oldest = ts if oldest is None else min(oldest, ts)
                if raw[8] != "1" or not is_closed_candle(ts, interval_ms, now_ms):
                    continue
                collected[ts] = {
                    "open_time": ts, "open": float(raw[1]), "high": float(raw[2]),
                    "low": float(raw[3]), "close": float(raw[4]),
                    "volume": float(raw[6] if len(raw) > 6 and raw[6] not in ("", None) else raw[5]),
                    "volume_contracts": float(raw[5]),
                    "data_source": "OKX_PUBLIC_SWAP_CANDLE",
                    "cvd_source": "OKX_CVD_UNAVAILABLE_NEUTRAL_PROXY",
                }
            if oldest is None or (cursor is not None and oldest >= cursor):
                if endpoint.endswith("/market/candles"):
                    endpoint = "/api/v5/market/history-candles"
                    page_size = 100
                    continue
                break
            cursor = oldest
            if len(collected) >= limit:
                break
            if len(data) < page_size and endpoint.endswith("/market/history-candles"):
                break
            time.sleep(0.12)
        rows = [collected[key] for key in sorted(collected)]
        if len(rows) < limit:
            raise ValueError(f"okx_{timeframe}_history_short:{len(rows)}/{limit}")
        return rows[-limit:]

    def _ccxt_timeframe(self, symbol: str, timeframe: str, limit: int, now_ms: int) -> list[dict[str, Any]]:
        interval_ms = 3_600_000 if timeframe == "1h" else 900_000
        errors: list[str] = []
        for provider in ("okx", "bybit", "kucoinfutures", "mexc", "bitget"):
            try:
                exchange = self._exchange(provider)
                market = self._find_market(exchange, symbol)
                cursor = (now_ms // interval_ms) * interval_ms - limit * interval_ms
                collected: dict[int, list[Any]] = {}
                for _ in range((limit + 999) // 1000 + 3):
                    remaining = limit - len(collected)
                    if remaining <= 0:
                        break
                    batch = exchange.fetch_ohlcv(
                        market["symbol"], timeframe=timeframe, since=cursor,
                        limit=min(1000, remaining),
                    )
                    if not batch:
                        break
                    newest = cursor
                    for candle in batch:
                        if len(candle) < 6 or candle[0] is None:
                            continue
                        ts = int(candle[0])
                        if ts + interval_ms <= now_ms:
                            collected[ts] = candle
                        newest = max(newest, ts)
                    next_cursor = newest + interval_ms
                    if next_cursor <= cursor:
                        break
                    cursor = next_cursor
                    time.sleep(max(float(getattr(exchange, "rateLimit", 0)) / 1000, 0.05))
                if len(collected) >= limit:
                    rows = []
                    for candle in [collected[key] for key in sorted(collected)][-limit:]:
                        rows.append({
                            "open_time": int(candle[0]), "open": float(candle[1]),
                            "high": float(candle[2]), "low": float(candle[3]),
                            "close": float(candle[4]), "volume": float(candle[5]),
                            "data_source": f"CCXT_{provider.upper()}_PUBLIC_OHLCV",
                            "cvd_source": "UNAVAILABLE_NEUTRAL_PROXY",
                        })
                    return rows
                errors.append(f"{provider}_history_short:{len(collected)}/{limit}")
            except Exception as exc:
                errors.append(f"{provider}:{type(exc).__name__}:{str(exc)[:100]}")
        raise RuntimeError(f"ccxt_{timeframe}_fallback_failed|" + "|".join(errors))

    def _okx_metrics(self, symbol: str, now_ms: int) -> dict[str, Any]:
        base = symbol[:-4] if symbol.upper().endswith("USDT") else symbol.upper()
        inst_id = f"{base}-USDT-SWAP"
        metrics: dict[str, Any] = {
            "funding_rate": None, "oi_1h": None, "oi_1d": None,
            "long_short_ratio": None, "errors": {},
        }

        def get(path: str, params: dict[str, str], key: str):
            response = self.client.get("https://www.okx.com" + path, params=params)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "0":
                raise ValueError(f"okx_code:{payload.get('code')}:{payload.get('msg')}")
            return payload.get("data") or []

        try:
            data = get("/api/v5/public/funding-rate", {"instId": inst_id}, "funding")
            if data:
                metrics["funding_rate"] = float(data[0]["fundingRate"])
        except Exception as exc:
            metrics["errors"]["funding"] = f"{type(exc).__name__}:{str(exc)[:120]}"

        try:
            begin = str(now_ms - 30 * 60 * 60 * 1000)
            data = get("/api/v5/rubik/stat/contracts/open-interest-volume",
                       {"ccy": base, "period": "1H", "begin": begin, "end": str(now_ms)}, "oi_1h")
            metrics["oi_1h"] = data
        except Exception as exc:
            metrics["errors"]["oi_1h"] = f"{type(exc).__name__}:{str(exc)[:120]}"

        try:
            begin = str(now_ms - 100 * 24 * 60 * 60 * 1000)
            data = get("/api/v5/rubik/stat/contracts/open-interest-volume",
                       {"ccy": base, "period": "1D", "begin": begin, "end": str(now_ms)}, "oi_1d")
            metrics["oi_1d"] = data
        except Exception as exc:
            metrics["errors"]["oi_1d"] = f"{type(exc).__name__}:{str(exc)[:120]}"

        try:
            data = get("/api/v5/rubik/stat/contracts/long-short-account-ratio",
                       {"ccy": base, "period": "1H"}, "long_short")
            if data:
                metrics["long_short_ratio"] = float(data[0][1])
        except Exception as exc:
            metrics["errors"]["long_short_ratio"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        return metrics

    def fetch_symbol(self, symbol: str) -> OHLCVBundle:
        """هم‌زمان دو پنجرهٔ مستقل می‌گیرد: ۲۵۰۰ کندل 1H و ۵۰۰ کندل 15m."""
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        errors: list[str] = []
        try:
            stats_1h = self._okx_candles(symbol, "1H", self.stats_limit, now_ms)
            live_15m = self._okx_candles(symbol, "15m", self.limit, now_ms)
            source = "OKX_PUBLIC_SWAP_CANDLE"
        except Exception as exc:
            errors.append(f"okx_candles:{type(exc).__name__}:{str(exc)[:140]}")
            try:
                stats_1h = self._ccxt_timeframe(symbol, "1h", self.stats_limit, now_ms)
                live_15m = self._ccxt_timeframe(symbol, "15m", self.limit, now_ms)
                source = "CCXT_PUBLIC_OHLCV_FALLBACK"
            except Exception as fallback_exc:
                raise RuntimeError("all_dual_timeframe_sources_failed|" + "|".join(errors) +
                                   f"|fallback:{type(fallback_exc).__name__}:{str(fallback_exc)[:160]}")
        metrics = self._okx_metrics(symbol, now_ms)
        LOG.info(
            "%s dual_timeframe source=%s bars_1h=%d bars_15m=%d okx_funding=%s okx_oi_1h=%s okx_oi_1d=%s okx_lsr=%s",
            symbol, source, len(stats_1h), len(live_15m),
            metrics["funding_rate"] is not None, bool(metrics["oi_1h"]),
            bool(metrics["oi_1d"]), metrics["long_short_ratio"] is not None,
        )
        return OHLCVBundle(live_15m, stats_1h, metrics)
