"""Read-only Toobit USDT-M linear perpetual market-data adapter."""
from __future__ import annotations

import time
import httpx

from app.signals import Candle, DataError, INTERVALS

CG = "https://api.coingecko.com/api/v3"


class ToobitPublicMarketData:
    BASE = "https://api.toobit.com"
    provider_name = "Toobit public USDT-M linear perpetual market data"

    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20, follow_redirects=False)
        self.own = client is None
        self.calls = 0
        self._exchange = None
        self._tickers = None
        self._marks = None
        self._indices = None
        self._funding = None
        self._book_tickers = None
        self._server_time = 0
        self._contracts = {}

    def _get(self, path: str, params: dict | None = None):
        try:
            response = self.client.get(
                self.BASE + path,
                params=params or {},
                headers={"Accept": "application/json", "User-Agent": "FuturesSignalAutopilot/6.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise DataError(f"toobit_public_api_error:{path}:http_{status or type(exc).__name__}") from exc
        self.calls += 1
        if isinstance(payload, dict) and payload.get("code") not in (None, 200, "200"):
            raise DataError(f"toobit_rejected_payload:{path}")
        return payload

    def _load_exchange(self):
        if self._exchange is None:
            payload = self._get("/api/v1/exchangeInfo")
            if not isinstance(payload, dict) or not isinstance(payload.get("contracts"), list):
                raise DataError("toobit_invalid_exchange_info")
            self._exchange = payload
            self._server_time = int(payload.get("serverTime") or 0)
        return self._exchange

    def server_time(self):
        if not self._server_time or abs(int(time.time() * 1000) - self._server_time) > 60_000:
            payload = self._get("/api/v1/time")
            self._server_time = int(payload.get("serverTime") or 0) if isinstance(payload, dict) else 0
        if not self._server_time:
            raise DataError("toobit_server_time_unavailable")
        return self._server_time

    @staticmethod
    def _base_symbol(symbol: str) -> str:
        value = str(symbol).upper()
        return value[:-4] if value.endswith("USDT") else value

    @staticmethod
    def _contract_symbol(base: str) -> str:
        return f"{base}-SWAP-USDT"

    def _linear_contracts(self):
        rows = self._load_exchange()["contracts"]
        result = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            underlying = str(item.get("underlying") or "").upper()
            if (
                item.get("status") != "TRADING"
                or item.get("inverse") is not False
                or item.get("marginToken") != "USDT"
                or item.get("quoteAsset") != "USDT"
                or not underlying
                or symbol != self._contract_symbol(underlying)
            ):
                continue
            result[underlying + "USDT"] = item
        return result

    def discover(self):
        try:
            response = self.client.get(
                CG + "/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc", "per_page": 100, "page": 1, "sparkline": "false"},
                headers={"Accept": "application/json", "User-Agent": "FuturesSignalAutopilot/6.0"},
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DataError("coingecko_discovery_unavailable") from exc
        if not isinstance(rows, list):
            raise DataError("invalid_coingecko_market_list")
        assets = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            assets.append({
                "id": str(row.get("id") or ""),
                "symbol": str(row["symbol"]).upper(),
                "name": row.get("name"),
                "volume": float(row.get("total_volume") or 0),
                "market_cap_rank": row.get("market_cap_rank"),
                "current_price": float(row.get("current_price") or 0),
                "market_cap": float(row.get("market_cap") or 0),
            })
        return sorted(assets, key=lambda item: item["volume"], reverse=True)

    def tracked_symbols(self):
        return set(self._linear_contracts())

    def contract_specs(self, symbols):
        available = self._linear_contracts()
        result = {}
        for raw in symbols:
            symbol = str(raw).upper()
            item = available.get(symbol)
            if not item:
                continue
            filters = {
                str(row.get("filterType")): row
                for row in item.get("filters", [])
                if isinstance(row, dict) and row.get("filterType")
            }
            try:
                price_filter = filters["PRICE_FILTER"]
                lot_filter = filters["LOT_SIZE"]
                tick = float(price_filter["tickSize"])
                multiplier = float(item["contractMultiplier"])
                # Toobit exchangeInfo expresses LOT_SIZE minQty/stepSize in underlying-token units.
                # The public futures order schema expresses quantity in contracts.
                step = float(lot_filter["stepSize"]) / multiplier
                minimum = float(lot_filter["minQty"]) / multiplier
                maximum = float(lot_filter["maxQty"]) / multiplier
                min_notional = float((filters.get("MIN_NOTIONAL") or {}).get("minNotional") or 0)
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                continue
            if min(tick, step, minimum, multiplier, maximum) <= 0:
                continue
            risk_limits = []
            for tier in item.get("riskLimits", []):
                try:
                    value = float(tier.get("value") or 0)
                    max_lev = float(tier.get("maxLeverage") or 0)
                    if value > 0 and max_lev > 0:
                        risk_limits.append({"value": value, "max_leverage": max_lev})
                except (TypeError, ValueError):
                    continue
            if not risk_limits:
                continue
            result[symbol] = {
                "symbol": symbol,
                "venue_symbol": item["symbol"],
                "contract_type": "PERPETUAL",
                "status": item["status"],
                "base_asset": str(item.get("underlying") or "").upper(),
                "quote_asset": "USDT",
                "margin_asset": "USDT",
                "quantity_unit": "contracts",
                "contract_multiplier": multiplier,
                "multiplier_currency": str(item.get("underlying") or "").upper(),
                "tick_size": tick,
                "step_size": step,
                "min_qty": minimum,
                "max_qty": maximum,
                "min_notional": min_notional,
                "min_trade_precision": item.get("minTradePrecision"),
                "risk_limits": sorted(risk_limits, key=lambda tier: tier["value"]),
                "source": "Toobit public exchangeInfo",
            }
        self._contracts.update(result)
        return result

    def _load_tickers(self):
        if self._tickers is None:
            rows = self._get("/quote/v1/contract/ticker/24hr")
            if not isinstance(rows, list):
                raise DataError("toobit_invalid_contract_tickers")
            self._tickers = {str(row.get("s") or "").upper(): row for row in rows if isinstance(row, dict)}
        return self._tickers

    def _load_marks(self):
        if self._marks is None:
            rows = self._get("/quote/v1/markPrice")
            if not isinstance(rows, list):
                raise DataError("toobit_invalid_mark_prices")
            self._marks = {str(row.get("symbolId") or "").upper(): row for row in rows if isinstance(row, dict)}
        return self._marks

    def _load_indices(self):
        if self._indices is None:
            payload = self._get("/quote/v1/index")
            index = payload.get("index") if isinstance(payload, dict) else None
            if not isinstance(index, dict):
                raise DataError("toobit_invalid_index_prices")
            self._indices = {str(key).upper(): float(value) for key, value in index.items()}
        return self._indices

    def _load_funding(self):
        if self._funding is None:
            rows = self._get("/api/v1/futures/fundingRate")
            if not isinstance(rows, list):
                raise DataError("toobit_invalid_funding_rates")
            self._funding = {str(row.get("symbol") or "").upper(): row for row in rows if isinstance(row, dict)}
        return self._funding

    def _load_book_tickers(self):
        if self._book_tickers is None:
            rows = self._get("/quote/v1/contract/ticker/bookTicker")
            if not isinstance(rows, list):
                raise DataError("toobit_invalid_book_tickers")
            self._book_tickers = {str(row.get("s") or "").upper(): row for row in rows if isinstance(row, dict)}
        return self._book_tickers

    def rank_symbols_by_volume(self, eligible):
        tickers = self._load_tickers()
        return sorted(
            eligible,
            key=lambda pair: float((tickers.get(self._contract_symbol(pair[0]["symbol"])) or {}).get("qv") or 0),
            reverse=True,
        )

    def prices(self, symbols):
        tickers = self._load_tickers()
        books = self._load_book_tickers()
        result = {}
        for raw in symbols:
            symbol = str(raw).upper()
            venue = self._contract_symbol(self._base_symbol(symbol))
            ticker = tickers.get(venue)
            book = books.get(venue)
            if not ticker or not book:
                continue
            try:
                last = float(ticker["c"])
                bid, ask = float(book["b"]), float(book["a"])
                bid_qty, ask_qty = float(book["bq"]), float(book["aq"])
                ts = int(ticker.get("t") or book.get("t") or 0)
                if min(last, bid, ask, bid_qty, ask_qty) <= 0 or not ts or ask < bid:
                    continue
                mid = (bid + ask) / 2
                multiplier = float((self._contracts.get(symbol) or {}).get("contract_multiplier") or 1)
                depth_payload = self._get("/quote/v1/depth", {"symbol": venue, "limit": 20})
                if not isinstance(depth_payload, dict):
                    raise DataError("toobit_invalid_orderbook")
                bid_depth = sum(float(p) * float(q) * multiplier for p, q in depth_payload.get("b", [])
                                if float(p) >= mid * 0.995)
                ask_depth = sum(float(p) * float(q) * multiplier for p, q in depth_payload.get("a", [])
                                if float(p) <= mid * 1.005)
                result[symbol] = {
                    "symbol": symbol,
                    "price": last,
                    "updatedAt": ts,
                    "high24h": float(ticker.get("h") or 0),
                    "low24h": float(ticker.get("l") or 0),
                    "volume24h": float(ticker.get("v") or 0),
                    "quoteVolume24h": float(ticker.get("qv") or 0),
                    "change24hPct": float(ticker.get("pcp") or 0) * 100,
                    "bid": bid,
                    "ask": ask,
                    "spreadBps": (ask - bid) / mid * 10_000,
                    "bidDepthUsd": bid_depth,
                    "askDepthUsd": ask_depth,
                    "source": "Toobit public futures ticker and order book",
                }
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                raise DataError("invalid_toobit_price_or_orderbook_payload") from exc
        return result

    def derivatives(self, symbols):
        tickers = self._load_tickers()
        marks = self._load_marks()
        indices = self._load_indices()
        funding_rows = self._load_funding()
        server_time = self.server_time()
        result = {}
        for raw in symbols:
            symbol = str(raw).upper()
            base = self._base_symbol(symbol)
            venue = self._contract_symbol(base)
            ticker = tickers.get(venue)
            mark = marks.get(venue)
            funding = funding_rows.get(venue)
            index = indices.get(base + "USDT")
            if not ticker or not mark or not funding or index is None:
                result[symbol] = {"symbol": symbol, "error": "missing_toobit_price_mark_index_or_funding"}
                continue
            try:
                oi_payload = self._get("/quote/v1/openInterest", {"symbol": venue})
                oi_rows = oi_payload.get("openInterestList", []) if isinstance(oi_payload, dict) else []
                oi_row = next((row for row in oi_rows if str(row.get("symbol") or "").upper() == venue), None)
                if not oi_row:
                    raise DataError("missing_toobit_open_interest")
                oi_size = float(oi_row["size"])
                last_price = float(ticker["c"])
                oi_usd = oi_size * last_price
                ratio_rows = self._get("/quote/v1/globalLongShortAccountRatio",
                                       {"symbol": venue, "period": "1h", "limit": 2})
                ratio_row = ratio_rows[-1] if isinstance(ratio_rows, list) and ratio_rows else {}
                ratio_ts = int(ratio_row.get("timeStamp") or 0)
                ratio = float(ratio_row["longShortRatio"]) if ratio_row.get("longShortRatio") is not None else None
                if ratio_ts and server_time - ratio_ts > 90 * 60_000:
                    ratio = None
                period = str(funding.get("period") or "").upper()
                interval_hours = float(period[:-1]) if period.endswith("H") else 0
                mark_price = float(mark["price"])
                index_price = float(index)
                mark_ts = int(mark.get("time") or 0)
                ticker_ts = int(ticker.get("t") or 0)
                observed = min(x for x in (mark_ts, ticker_ts, server_time) if x > 0)
                result[symbol] = {
                    "symbol": symbol,
                    "updatedAt": observed,
                    "markPrice": mark_price,
                    "indexPrice": index_price,
                    "funding": {
                        "rate": float(funding["rate"]),
                        "intervalHours": interval_hours,
                        "nextFundingTime": int(funding.get("nextFundingTime") or 0),
                    },
                    "openInterest": {
                        "valueUsd": oi_usd,
                        "sizeBaseAsset": oi_size,
                        "change4hPct": None,
                        "change24hPct": None,
                        "priceChange24hPct": float(ticker.get("pcp") or 0) * 100,
                    },
                    "positioning": {
                        "globalLongShortRatio": ratio,
                        "topTraderLongShortRatio": None,
                        "takerBuySellRatio": None,
                        "ratioObservedAt": ratio_ts,
                        "label": "toobit_global_account_ratio" if ratio is not None else "unavailable",
                    },
                    "source": "Toobit public USDT-M futures market data",
                }
            except DataError as exc:
                result[symbol] = {"symbol": symbol, "error": str(exc)}
            except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
                result[symbol] = {"symbol": symbol, "error": "invalid_toobit_derivatives_payload"}
        return result

    def candles(self, symbol, tf, limit=220):
        interval = INTERVALS.get(tf)
        if not interval:
            raise DataError("unsupported_toobit_candle_interval")
        base = self._base_symbol(symbol)
        venue = self._contract_symbol(base)
        rows = self._get("/quote/v1/klines", {"symbol": venue, "interval": tf, "limit": min(int(limit), 1000)})
        if not isinstance(rows, list):
            raise DataError("toobit_invalid_ohlcv_payload")
        now = self.server_time()
        result = []
        try:
            for row in rows:
                if not isinstance(row, list) or len(row) < 11:
                    raise ValueError("short kline row")
                opened = int(row[0])
                close_time = opened + interval - 1
                quote_volume = float(row[7])
                taker_buy_quote = float(row[10])
                result.append(Candle(
                    opened, float(row[1]), float(row[2]), float(row[3]), float(row[4]),
                    quote_volume, close_time, close_time < now,
                    taker_buy_quote_volume=taker_buy_quote,
                ))
            return sorted(result, key=lambda candle: candle.open_time)
        except (TypeError, ValueError, IndexError) as exc:
            raise DataError("invalid_toobit_ohlcv_payload") from exc

    def smart_money(self):
        return {
            "traders": [], "positions": [], "signals": [],
            "traders_observed_at_ms": 0, "positions_observed_at_ms": 0, "signals_observed_at_ms": 0,
            "note": "Toobit public market-data endpoints do not provide smart-money wallet identity or top-trader open positions.",
        }

    def close(self):
        if self.own:
            self.client.close()
