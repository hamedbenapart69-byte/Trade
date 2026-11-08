"""CCXT Binance USD-M public data collector; no account credentials or trading methods."""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import ccxt
import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from .quality import validate_ohlcv_rows, gap_report

MS_HOUR = 3_600_000
MS_DAY = 86_400_000
DEFAULT_BASE = "https://fapi.binance.com"


class Stage1Collector:
    def __init__(self, data_dir: str | Path = "data/stage1", exchange=None,
                 http_client: httpx.Client | None = None, sleep: Callable = time.sleep):
        self.data_dir = Path(data_dir)
        self.exchange = exchange or ccxt.binanceusdm({
            "enableRateLimit": True,
            "timeout": 20000,
            "options": {"defaultType": "future"},
        })
        self.http = http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        self._owns_http = http_client is None
        self.sleep = sleep
        self.base_url = os.getenv("BINANCE_FAPI_BASE_URL", DEFAULT_BASE).rstrip("/")

    def close(self):
        try:
            self.exchange.close()
        except Exception:
            pass
        if self._owns_http:
            self.http.close()

    def _write_parquet(self, relative: str, rows: list[dict]) -> str:
        path = self.data_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(rows)
        fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
        os.close(fd)
        try:
            pq.write_table(table, temp_name, compression="zstd")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return str(path)

    @staticmethod
    def _utc(ms: int | None) -> str | None:
        return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat() if ms else None

    def probe_binance(self, attempts: int = 5) -> dict:
        checks = [
            ("ping", "/fapi/v1/ping", {}),
            ("exchange_info", "/fapi/v1/exchangeInfo", {}),
            ("ticker_price", "/fapi/v1/ticker/price", {"symbol":"BTCUSDT"}),
            ("klines", "/fapi/v1/klines", {"symbol":"BTCUSDT","interval":"1h","limit":2}),
            ("open_interest", "/fapi/v1/openInterest", {"symbol":"BTCUSDT"}),
        ]
        results = []
        for name, path, params in checks:
            outcomes = []
            for attempt in range(attempts):
                started = time.monotonic()
                try:
                    response = self.http.get(self.base_url + path, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    valid = isinstance(payload, (dict, list))
                    outcomes.append({"attempt":attempt+1,"http_status":response.status_code,
                                     "json_valid":valid,"elapsed_ms":round((time.monotonic()-started)*1000)})
                    if valid:
                        break
                except Exception as exc:
                    outcomes.append({"attempt":attempt+1,"error":type(exc).__name__,
                                     "detail":str(exc)[:160],
                                     "elapsed_ms":round((time.monotonic()-started)*1000)})
                self.sleep(0.25)
            results.append({"endpoint":name,"attempts":outcomes,
                            "passed":bool(outcomes and outcomes[-1].get("json_valid"))})
        return {"provider":"Binance USD-M public REST","base_url":self.base_url,
                "generated_at_utc":datetime.now(timezone.utc).isoformat(),
                "passed":sum(x["passed"] for x in results),"total":len(results),"checks":results,
                "scope_note":"This probe reports the IP/network of the machine running it; a GitHub-hosted run does not prove reachability from an Iranian residential/mobile IP."}

    def probe_bybit(self) -> dict:
        url = "https://api.bybit.com/v5/market/time"
        try:
            response = self.http.get(url)
            response.raise_for_status()
            payload = response.json()
            ok = isinstance(payload, dict) and payload.get("retCode") == 0
            return {"provider":"Bybit public REST","passed":ok,"http_status":response.status_code,
                    "retCode":payload.get("retCode") if isinstance(payload,dict) else None}
        except Exception as exc:
            return {"provider":"Bybit public REST","passed":False,"error":type(exc).__name__,
                    "detail":str(exc)[:160]}

    def discover_symbols(self, target_count: int = 100) -> list[str]:
        self.exchange.load_markets()
        tickers = self.exchange.fetch_tickers()
        candidates = []
        btc_unified = None
        for unified_symbol, market in self.exchange.markets.items():
            if market.get("id") == "BTCUSDT":
                btc_unified = unified_symbol
            if not market.get("active") or not market.get("swap") or not market.get("linear"):
                continue
            if market.get("quote") != "USDT" or market.get("settle") != "USDT":
                continue
            if not market.get("contract"):
                continue
            ticker = tickers.get(unified_symbol) or {}
            quote_volume = ticker.get("quoteVolume")
            if quote_volume is None:
                info = ticker.get("info") or {}
                quote_volume = info.get("quoteVolume") or 0
            try:
                volume = float(quote_volume or 0)
            except (TypeError, ValueError):
                volume = 0
            if volume > 0:
                candidates.append((volume, unified_symbol))
        candidates.sort(reverse=True)
        selected = [symbol for _,symbol in candidates[:target_count]]
        if btc_unified and btc_unified not in selected:
            selected = [btc_unified] + selected[:max(target_count-1,0)]
        return list(dict.fromkeys(selected))

    def fetch_ohlcv(self, symbol: str, since_ms: int, until_ms: int, timeframe: str = "1h") -> list[dict]:
        timeframe_ms = self.exchange.parse_timeframe(timeframe) * 1000
        cursor = since_ms
        collected = []
        while cursor < until_ms:
            batch = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=1500)
            if not batch:
                break
            for item in batch:
                ts = int(item[0])
                if since_ms <= ts < until_ms:
                    collected.append({"timestamp":ts,"open":item[1],"high":item[2],
                                      "low":item[3],"close":item[4],"volume":item[5]})
            last_ts = int(batch[-1][0])
            next_cursor = last_ts + timeframe_ms
            if next_cursor <= cursor:
                raise RuntimeError(f"ohlcv_pagination_stalled:{symbol}")
            cursor = next_cursor
            if len(batch) < 2:
                break
        return validate_ohlcv_rows(collected)

    def fetch_funding(self, symbol: str, since_ms: int, until_ms: int) -> list[dict]:
        cursor = since_ms
        collected = {}
        market_id = self.exchange.market(symbol)["id"]
        while cursor < until_ms:
            batch = self.exchange.fetch_funding_rate_history(symbol, since=cursor, limit=1000)
            if not batch:
                break
            for item in batch:
                ts = int(item.get("timestamp") or 0)
                if since_ms <= ts < until_ms:
                    collected[ts] = {
                        "timestamp":ts,"symbol":market_id,
                        "funding_rate":float(item.get("fundingRate") or 0),
                        "mark_price":float(item.get("markPrice") or 0) if item.get("markPrice") else None,
                    }
            last_ts = max(int(x.get("timestamp") or 0) for x in batch)
            if last_ts < cursor:
                raise RuntimeError(f"funding_pagination_stalled:{symbol}")
            cursor = last_ts + 1
            if len(batch) < 2:
                break
        return [collected[k] for k in sorted(collected)]

    def fetch_open_interest_history(self, symbol: str, since_ms: int, until_ms: int) -> list[dict]:
        # Binance USD-M openInterestHist exposes only the latest month.
        start = max(since_ms, until_ms - 30*MS_DAY)
        market_id = self.exchange.market(symbol)["id"]
        rows = self.exchange.request("openInterestHist", "fapiPublic", "GET",
                                     {"symbol":market_id,"period":"1h","limit":500,
                                      "startTime":start,"endTime":until_ms})
        out=[]
        for item in rows or []:
            out.append({"timestamp":int(item["timestamp"]),"symbol":market_id,
                        "open_interest":float(item["sumOpenInterest"]),
                        "open_interest_value_usd":float(item["sumOpenInterestValue"])})
        return sorted(out,key=lambda x:x["timestamp"])

    def probe_fear_greed(self) -> dict:
        try:
            response = self.http.get("https://api.alternative.me/fng/",
                                     params={"limit":1,"format":"json"})
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data") if isinstance(payload,dict) else None
            value = int(rows[0]["value"]) if isinstance(rows,list) and rows else None
            return {"provider":"Alternative.me Fear & Greed","passed":value is not None and 0 <= value <= 100,
                    "http_status":response.status_code,"sample_count":len(rows or []),
                    "latest_value":value}
        except Exception as exc:
            return {"provider":"Alternative.me Fear & Greed","passed":False,
                    "error":type(exc).__name__,"detail":str(exc)[:160]}

    def fetch_fear_greed(self) -> list[dict]:
        response = self.http.get("https://api.alternative.me/fng/",
                                 params={"limit":0,"format":"json"})
        response.raise_for_status()
        payload = response.json()
        values = payload.get("data") if isinstance(payload,dict) else None
        if not isinstance(values,list):
            raise ValueError("fear_greed_invalid_payload")
        out=[]
        for item in values:
            ts=int(item["timestamp"])*1000
            value=int(item["value"])
            if not 0 <= value <= 100:
                raise ValueError("fear_greed_value_out_of_range")
            out.append({"timestamp":ts,"value":value,"classification":str(item.get("value_classification","")),
                        "source":"alternative.me"})
        return sorted({x["timestamp"]:x for x in out}.values(),key=lambda x:x["timestamp"])

    def run(self, target_count: int = 100, years: int = 2, now_ms: int | None = None) -> dict:
        now_ms = int(now_ms or time.time()*1000)
        since_ms = now_ms - int(years*365.25*MS_DAY)
        probe = self.probe_binance()
        bybit_probe = self.probe_bybit()
        if not probe["passed"]:
            raise RuntimeError("binance_probe_failed; see probe report")
        symbols = self.discover_symbols(target_count)
        reports = {}
        expected_ohlcv_rows = max(1, (now_ms-since_ms)//MS_HOUR)
        for symbol in symbols:
            try:
                market_id = self.exchange.market(symbol)["id"]
                ohlcv = self.fetch_ohlcv(symbol,since_ms,now_ms,"1h")
                funding = self.fetch_funding(symbol,since_ms,now_ms)
                oi = self.fetch_open_interest_history(symbol,since_ms,now_ms)
                safe = market_id.replace("/","_")
                gaps = gap_report(ohlcv)
                gaps["coverage_of_requested_window_pct"] = round(100*len(ohlcv)/expected_ohlcv_rows, 3)
                reports[market_id] = {
                    "ohlcv":gaps,
                    "funding":{"rows":len(funding),"first_timestamp_utc":self._utc(funding[0]["timestamp"]) if funding else None,
                               "last_timestamp_utc":self._utc(funding[-1]["timestamp"]) if funding else None},
                    "open_interest":{"rows":len(oi),"coverage_days":round((oi[-1]["timestamp"]-oi[0]["timestamp"])/MS_DAY,2) if len(oi)>1 else 0,
                                     "label":"BINANCE_PUBLIC_HISTORY_LIMIT_30D"},
                    "files":{
                        "ohlcv":self._write_parquet(f"binance_usdm/ohlcv_1h/{safe}.parquet",ohlcv),
                        "funding":self._write_parquet(f"binance_usdm/funding/{safe}.parquet",funding),
                        "open_interest":self._write_parquet(f"binance_usdm/open_interest_1h/{safe}.parquet",oi),
                    },
                }
            except Exception as exc:
                reports[self.exchange.market(symbol)["id"] if symbol in self.exchange.markets else symbol]={"error":type(exc).__name__,"detail":str(exc)[:240]}
        fng=[]
        fng_error=None
        try:
            fng=self.fetch_fear_greed()
            self._write_parquet("sentiment/fear_greed_daily.parquet",fng)
        except Exception as exc:
            fng_error=f"{type(exc).__name__}:{str(exc)[:180]}"
        good=[v for v in reports.values() if "error" not in v]
        expected_total = expected_ohlcv_rows * max(len(symbols),1)
        actual_total = sum(v["ohlcv"]["rows"] for v in good)
        missing_total = sum(max(expected_ohlcv_rows-v["ohlcv"]["rows"],0) for v in good)
        report={
            "stage":1,"version":"v1_ccxt_parquet","generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "requested_symbols":target_count,"active_symbols":len(symbols),"successful_symbols":len(good),
            "failed_symbols":len(reports)-len(good),"history_target_years":years,
            "ohlcv_coverage":{
                "symbols_with_no_gap_over_1h":sum(1 for v in good if v["ohlcv"]["no_gap_over_1h"]),
                "symbols_with_full_requested_window":sum(1 for v in good if v["ohlcv"]["coverage_of_requested_window_pct"] >= 99.9),
                "expected_rows_all_symbols":expected_total,"actual_rows_successful_symbols":actual_total,
                "missing_rows_estimate_successful_symbols":missing_total,
                "gap_rate_pct_successful_symbols":round(100*missing_total/max(expected_total,1),4),
            },
            "fear_greed":{"rows":len(fng),"first_timestamp_utc":self._utc(fng[0]["timestamp"]) if fng else None,
                          "last_timestamp_utc":self._utc(fng[-1]["timestamp"]) if fng else None,"error":fng_error},
            "binance_probe":probe,"bybit_probe":bybit_probe,"symbols":reports,
            "limitations":{
                "open_interest":"Binance USD-M historical open-interest statistics are limited to the latest 1 month; not a 2-year series.",
                "fear_greed":"Daily series, not hourly. No synthetic interpolation is performed.",
                "order_book":"No historical order-book snapshots stored in Stage 1.",
                "liquidations":"No verified historical liquidation feed stored in Stage 1.",
                "basis":"No continuous historical basis series stored in Stage 1.",
                "iran_access":"A probe executed on GitHub-hosted infrastructure does not establish reachability from the user's own Iranian IP/network."
            }
        }
        self.data_dir.mkdir(parents=True,exist_ok=True)
        report_path=self.data_dir/"stage1_report.json"
        report_path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        return report
