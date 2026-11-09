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
MIN_BARS_FOR_ENGINE = 1300
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


class LiveOHLCVFetcher:
    """دریافت ۱۵m از Binance Futures عمومی؛ در خطا fallback به صرافی‌های عمومی CCXT."""

    def __init__(self, limit: int = 1500, timeout: float = 25.0):
        self.limit = max(int(limit), MIN_BARS_FOR_ENGINE)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.exchanges: dict[str, Any] = {}
        self.market_cache: dict[str, dict[str, Any]] = {}
        self.provider_names = ("okx", "bybit", "binanceusdm", "bitget", "mexc", "kucoinfutures")

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

        for _ in range(4):
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
            if len(batch) < min(1000, remaining):
                break
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

    def fetch_symbol(self, symbol: str) -> list[dict[str, Any]]:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        errors: list[str] = []

        try:
            rows = self._binance(symbol, now_ms)
            LOG.info("%s data_source=BINANCE_FAPI_PUBLIC_KLINE bars=%d", symbol, len(rows))
            return rows
        except Exception as exc:
            errors.append(f"binance:{type(exc).__name__}:{str(exc)[:120]}")
            LOG.warning("%s Binance public klines unavailable: %s", symbol, errors[-1])

        for provider in self.provider_names:
            if provider == "binanceusdm":
                continue
            try:
                rows = self._from_ccxt(provider, symbol, now_ms)
                LOG.info("%s data_source=%s bars=%d", symbol, rows[-1]["data_source"], len(rows))
                return rows
            except Exception as exc:
                errors.append(f"{provider}:{type(exc).__name__}:{str(exc)[:120]}")
                LOG.warning("%s provider fallback failed: %s", symbol, errors[-1])

        raise RuntimeError("all_public_data_providers_failed|" + "|".join(errors))
