"""Stage 1a: public Binance Vision futures data with explicit funding fallbacks.

این ماژول فقط دادهٔ عمومی می‌خواند؛ هیچ حساب یا کلید معاملاتی استفاده نمی‌شود.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
import xml.etree.ElementTree as ET

import httpx

VISION = "https://data.binance.vision"
FAPI = "https://fapi.binance.com/fapi/v1/premiumIndex"
COINGECKO_DERIVATIVES = "https://api.coingecko.com/api/v3/derivatives"


class Stage1ADataProvider:
    def __init__(self, config: dict[str, Any], client: Any = None):
        self.config = config
        self.client = client or httpx.Client(timeout=25, follow_redirects=True)
        self._owns_client = client is None
        md = config.get("market_data") or {}
        strategy = md.get("provider_strategy") or {}
        self.target = int(strategy.get("target_symbols", 50))
        self.minimum = int(strategy.get("minimum_qualifying_symbols", 40))
        self.scan_limit = int(strategy.get("candidate_scan_limit", 150))
        self.min_volume = float(strategy.get("minimum_24h_quote_volume_usd", 10_000_000))
        self.blacklist = {str(x).upper() for x in (md.get("universe") or {}).get("blacklist_patterns", [])}
        self.errors: dict[str, str] = {}
        self.provider_counts = {"BINANCE_VISION": 0, "COINGECKO": 0, "KUCOIN_PROXY": 0}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(self, url: str, **kwargs):
        response = self.client.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _coingecko_assets(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, 5):
            response = self._get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency": "usd", "order": "market_cap_desc",
                        "per_page": 250, "page": page, "sparkline": "false"},
            )
            data = response.json()
            if not isinstance(data, list) or not data:
                break
            rows.extend(data)
        if len(rows) < 40:
            raise RuntimeError("COINGECKO_UNIVERSE_INCOMPLETE")
        return rows

    def _vision_symbols(self) -> set[str]:
        url = VISION + "/"
        params = {"list-type": "2", "delimiter": "/",
                  "prefix": "data/futures/um/daily/klines/"}
        symbols: set[str] = set()
        token = None
        for _ in range(5):
            query = dict(params)
            if token:
                query["continuation-token"] = token
            response = self._get(url, params=query)
            root = ET.fromstring(response.text)
            for item in root.findall(".//{*}CommonPrefixes/{*}Prefix"):
                match = re.search(r"/klines/([A-Z0-9]+USDT)/$", item.text or "")
                if match:
                    symbols.add(match.group(1))
            more = root.findtext(".//{*}IsTruncated")
            token = root.findtext(".//{*}NextContinuationToken")
            if more != "true" or not token:
                break
        if not symbols:
            raise RuntimeError("BINANCE_VISION_SYMBOL_LIST_EMPTY")
        return symbols

    @staticmethod
    def _daily_path(symbol: str, date: datetime) -> str:
        day = date.strftime("%Y-%m-%d")
        return f"data/futures/um/daily/klines/{symbol}/1h/{symbol}-1h-{day}.zip"

    def _download_daily_klines(self, symbol: str) -> tuple[list[list[str]], str]:
        today = datetime.now(timezone.utc).date()
        failures = []
        for offset in (1, 2, 3):
            day = datetime.combine(today - timedelta(days=offset), datetime.min.time(), tzinfo=timezone.utc)
            path = self._daily_path(symbol, day)
            try:
                response = self._get(f"{VISION}/{path}")
                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    name = next((n for n in archive.namelist() if n.lower().endswith(".csv")), None)
                    if not name:
                        raise ValueError("KLINE_ARCHIVE_NO_CSV")
                    rows = list(csv.reader(io.TextIOWrapper(archive.open(name), encoding="utf-8")))
                rows = [r for r in rows if len(r) >= 8 and r[0].isdigit()]
                if len(rows) >= 20:
                    return rows, path
                failures.append(f"{day.date()}:INSUFFICIENT_ROWS")
            except Exception as exc:
                failures.append(f"{day.date()}:{type(exc).__name__}")
        raise RuntimeError("BINANCE_VISION_KLINES_UNAVAILABLE:" + ",".join(failures))

    def _probe_aggtrades(self, symbol: str) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        for offset in (1, 2, 3):
            day = today - timedelta(days=offset)
            path = f"data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{day:%Y-%m-%d}.zip"
            try:
                response = self.client.head(f"{VISION}/{path}", timeout=20, follow_redirects=True)
                if response.status_code == 200:
                    return {"status": "AVAILABLE", "provider": "BINANCE_VISION", "path": path}
            except Exception:
                pass
        return {"status": "UNAVAILABLE", "provider": "NONE", "path": None}

    def _binance_funding(self, symbol: str) -> dict[str, Any]:
        response = self.client.get(FAPI, params={"symbol": symbol}, timeout=15)
        if response.status_code == 451:
            return {"status": "BLOCKED_451", "rate": None, "provider": "BINANCE_FAPI"}
        response.raise_for_status()
        body = response.json()
        value = body.get("lastFundingRate")
        if value is None:
            return {"status": "MISSING", "rate": None, "provider": "BINANCE_FAPI"}
        return {"status": "OK", "rate": float(value), "provider": "BINANCE_FAPI",
                "timestamp": body.get("time")}

    def _coingecko_funding_map(self) -> dict[str, float]:
        response = self._get(COINGECKO_DERIVATIVES)
        data = response.json()
        mapped = {}
        for row in data if isinstance(data, list) else []:
            symbol = str(row.get("symbol") or "").upper().replace("/", "").replace("-", "")
            rate = row.get("funding_rate")
            if symbol and rate is not None:
                try:
                    mapped[symbol] = float(rate) / 100.0
                except (TypeError, ValueError):
                    continue
        return mapped

    def _kucoin_proxy_funding(self, base: str) -> dict[str, Any]:
        try:
            import ccxt
            exchange = ccxt.kucoinfutures({"enableRateLimit": True, "timeout": 15000})
            try:
                markets = exchange.load_markets()
                match = next((s for s, m in markets.items()
                              if m.get("swap") and m.get("quote") == "USDT"
                              and str(m.get("base", "")).upper() == base), None)
                if not match:
                    return {"status": "UNAVAILABLE", "rate": None, "provider": "KUCOIN_FUTURES"}
                row = exchange.fetch_funding_rate(match)
                rate = row.get("fundingRate")
                if rate is None:
                    return {"status": "UNAVAILABLE", "rate": None, "provider": "KUCOIN_FUTURES"}
                return {"status": "PROXY", "rate": float(rate), "provider": "KUCOIN_FUTURES"}
            finally:
                exchange.close()
        except Exception as exc:
            return {"status": "UNAVAILABLE", "rate": None, "provider": "KUCOIN_FUTURES",
                    "error": type(exc).__name__}

    def _funding(self, symbol: str, cg_map: dict[str, float] | None) -> dict[str, Any]:
        try:
            result = self._binance_funding(symbol)
            if result["status"] == "OK":
                return result
            reason = result["status"]
        except Exception as exc:
            reason = "ERROR_" + type(exc).__name__
        if cg_map is None:
            try:
                cg_map = self._coingecko_funding_map()
            except Exception as exc:
                self.errors["coingecko_funding"] = type(exc).__name__ + ":" + str(exc)[:160]
                cg_map = {}
        if symbol in cg_map:
            self.provider_counts["COINGECKO"] += 1
            return {"status": "PROXY", "rate": cg_map[symbol], "provider": "COINGECKO",
                    "fallback_reason": reason}
        fallback = self._kucoin_proxy_funding(symbol.removesuffix("USDT"))
        fallback["fallback_reason"] = reason + "_AND_COINGECKO_MISSING"
        if fallback["status"] == "PROXY":
            self.provider_counts["KUCOIN_PROXY"] += 1
        return fallback

    def run(self) -> dict[str, Any]:
        assets = self._coingecko_assets()
        vision_symbols = self._vision_symbols()
        candidates = []
        seen = set()
        for asset in assets:
            base = str(asset.get("symbol") or "").upper()
            if not base or base in self.blacklist or base in seen:
                continue
            seen.add(base)
            symbol = base + "USDT"
            if symbol in vision_symbols:
                candidates.append((int(asset.get("market_cap_rank") or 10**9), symbol, base))
        candidates.sort()
        candidates = candidates[:self.scan_limit]
        coverage = []
        cg_funding = None
        for _, symbol, base in candidates:
            try:
                rows, path = self._download_daily_klines(symbol)
                quote_volume = sum(float(row[7]) for row in rows[-24:])
                if quote_volume < self.min_volume:
                    coverage.append({"symbol": symbol, "status": "REJECTED",
                                     "reason": "VOLUME_BELOW_THRESHOLD", "quote_volume_24h": quote_volume})
                    continue
                agg = self._probe_aggtrades(symbol)
                funding = self._funding(symbol, cg_funding)
                if funding.get("provider") == "COINGECKO" and cg_funding is None:
                    try:
                        cg_funding = self._coingecko_funding_map()
                    except Exception:
                        cg_funding = {}
                self.provider_counts["BINANCE_VISION"] += 1
                coverage.append({
                    "symbol": symbol, "status": "QUALIFYING",
                    "ohlcv_provider": "BINANCE_VISION", "ohlcv_status": "OK",
                    "ohlcv_path": path, "ohlcv_rows": len(rows),
                    "quote_volume_24h_usd": quote_volume,
                    "aggtrades": agg, "funding": funding,
                    "quality_label": "PROXY" if funding.get("status") == "PROXY" or agg["status"] != "AVAILABLE" else "REAL_DATA",
                })
            except Exception as exc:
                coverage.append({"symbol": symbol, "status": "DATA_UNAVAILABLE",
                                 "provider": "BINANCE_VISION",
                                 "reason": type(exc).__name__ + ":" + str(exc)[:180]})
        qualifying = [x for x in coverage if x["status"] == "QUALIFYING"]
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "provider_selected": "BINANCE_VISION" if qualifying else "NONE",
            "provider_counts": self.provider_counts,
            "target_symbols": self.target, "minimum_qualifying_symbols": self.minimum,
            "symbols_scanned": len(candidates), "symbols_qualifying": len(qualifying),
            "symbols_proxy": sum(x.get("quality_label") == "PROXY" for x in qualifying),
            "stage1a_status": "PASS" if len(qualifying) >= self.minimum else "FAIL",
            "coverage_per_symbol": coverage,
            "errors": self.errors,
            "manual_trade_only": True,
        }
