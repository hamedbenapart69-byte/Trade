"""CCXT Binance USD-M public data collector; no account credentials or trading methods."""
from __future__ import annotations

import json
import os
import hashlib
import io
import zipfile
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
                 http_client: httpx.Client | None = None, sleep: Callable = time.sleep,
                 provider: str = "binance"):
        self.data_dir = Path(data_dir)
        self.provider = provider.lower()
        if self.provider not in ("binance", "okx"):
            raise ValueError("unsupported_stage1_provider")
        if exchange is not None:
            self.exchange = exchange
        elif self.provider == "okx":
            self.exchange = ccxt.okx({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "swap"}})
        else:
            self.exchange = ccxt.binanceusdm({
                "enableRateLimit": True,
                "timeout": 20000,
                "options": {"defaultType": "future"},
            })
        self.http = http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        self._owns_http = http_client is None
        self.sleep = sleep
        self.base_url = os.getenv("BINANCE_FAPI_BASE_URL", DEFAULT_BASE).rstrip("/")
        self.provider_name = "OKX public market-data API" if self.provider == "okx" else "Binance USD-M public market-data API"

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

    def probe_okx(self) -> dict:
        base = "https://www.okx.com"
        checks = [
            ("instruments", "/api/v5/public/instruments", {"instType":"SWAP"}),
            ("tickers", "/api/v5/market/tickers", {"instType":"SWAP"}),
            ("candles", "/api/v5/market/candles", {"instId":"BTC-USDT-SWAP","bar":"1H","limit":"2"}),
            ("funding", "/api/v5/public/funding-rate", {"instId":"BTC-USDT-SWAP"}),
            ("open_interest", "/api/v5/public/open-interest", {"instType":"SWAP","instId":"BTC-USDT-SWAP"}),
            ("open_interest_history", "/api/v5/rubik/stat/contracts/open-interest-history",
             {"instId":"BTC-USDT-SWAP","period":"1H"}),
        ]
        results = []
        for name, path, params in checks:
            required = name != "open_interest_history"
            try:
                response = self.http.get(base + path, params=params)
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("data") if isinstance(payload,dict) else None
                passed = isinstance(rows,list) and payload.get("code") == "0" and (bool(rows) or not required)
                results.append({"dataset":name,"required":required,"passed":passed,
                                "http_status":response.status_code,"row_count":len(rows or [])})
            except Exception as exc:
                results.append({"dataset":name,"required":required,"passed":False,
                                "error":type(exc).__name__,"detail":str(exc)[:160]})
        required_rows = [x for x in results if x["required"]]
        return {"provider":"OKX public REST","passed":all(x["passed"] for x in required_rows),
                "required_passed":sum(x["passed"] for x in required_rows),
                "required_total":len(required_rows),"checks":results}

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

    def discover_symbols(self, target_count: int = 100, min_listing_ms: int | None = None) -> list[str]:
        self.exchange.load_markets()
        tickers = self.exchange.fetch_tickers()
        candidates = []
        btc_unified = None
        diagnostics = {"markets_total":len(self.exchange.markets),"active":0,"swap":0,"linear":0,
                       "quote_usdt":0,"settle_usdt":0,"contract":0,"listing_timestamp_present":0,
                       "old_enough":0,"positive_volume":0}
        for unified_symbol, market in self.exchange.markets.items():
            if market.get("base") == "BTC" and market.get("quote") == "USDT" and market.get("settle") == "USDT" and market.get("swap"):
                btc_unified = unified_symbol
            if not market.get("active"):
                continue
            diagnostics["active"] += 1
            if not market.get("swap"):
                continue
            diagnostics["swap"] += 1
            if not market.get("linear"):
                continue
            diagnostics["linear"] += 1
            if market.get("quote") != "USDT":
                continue
            diagnostics["quote_usdt"] += 1
            if market.get("settle") != "USDT":
                continue
            diagnostics["settle_usdt"] += 1
            if not market.get("contract"):
                continue
            diagnostics["contract"] += 1
            if min_listing_ms is not None:
                info = market.get("info") or {}
                listing_raw = info.get("listTime") if self.provider == "okx" else info.get("onboardDate")
                try:
                    listing_ms = int(listing_raw or 0)
                except (TypeError, ValueError):
                    listing_ms = 0
                if listing_ms > 0:
                    diagnostics["listing_timestamp_present"] += 1
                if listing_ms <= 0 or listing_ms > min_listing_ms:
                    continue
                diagnostics["old_enough"] += 1
            ticker = tickers.get(unified_symbol) or {}
            quote_volume = ticker.get("quoteVolume")
            if quote_volume is None:
                info = ticker.get("info") or {}
                raw_base_volume = info.get("volCcy24h") or ticker.get("baseVolume") or 0
                last_price = ticker.get("last") or info.get("last") or 0
                try:
                    # OKX swap volCcy24h is base-asset volume; convert to quote turnover for ranking.
                    quote_volume = float(raw_base_volume) * float(last_price)
                except (TypeError, ValueError):
                    quote_volume = 0
            try:
                volume = float(quote_volume or 0)
            except (TypeError, ValueError):
                volume = 0
            if volume > 0:
                diagnostics["positive_volume"] += 1
                candidates.append((volume, unified_symbol))
        self.universe_diagnostics = diagnostics
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
            batch = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor,
                                               limit=300 if self.provider == "okx" else 1500)
            if not batch:
                break
            batch = sorted(batch, key=lambda item: int(item[0]))
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
        funding_limit = 100 if self.provider == "okx" else 1000
        while cursor < until_ms:
            batch = self.exchange.fetch_funding_rate_history(symbol, since=cursor, limit=funding_limit)
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
            if len(batch) < funding_limit:
                break
        return [collected[k] for k in sorted(collected)]

    def fetch_open_interest_history(self, symbol: str, since_ms: int, until_ms: int) -> list[dict]:
        cursor = max(since_ms, until_ms - 30*MS_DAY)
        market_id = self.exchange.market(symbol)["id"]
        collected = {}
        while cursor < until_ms:
            if self.provider == "okx":
                rows = self.exchange.fetch_open_interest_history(symbol, timeframe="1h",
                                                                  since=cursor, limit=100)
                normalized = []
                for item in rows or []:
                    ts = int(item.get("timestamp") or 0)
                    amount = item.get("openInterestAmount", item.get("openInterest"))
                    value = item.get("openInterestValue")
                    if ts and amount is not None:
                        normalized.append({"timestamp":ts,"symbol":market_id,
                                           "open_interest":float(amount),
                                           "open_interest_value_usd":float(value) if value is not None else None})
            else:
                rows = self.exchange.request("openInterestHist", "fapiPublic", "GET",
                                             {"symbol":market_id,"period":"1h","limit":500,
                                              "startTime":cursor,"endTime":until_ms})
                normalized = [{"timestamp":int(item["timestamp"]),"symbol":market_id,
                               "open_interest":float(item["sumOpenInterest"]),
                               "open_interest_value_usd":float(item["sumOpenInterestValue"])}
                              for item in (rows or [])]
            if not normalized:
                break
            for item in normalized:
                if cursor <= item["timestamp"] <= until_ms:
                    collected[item["timestamp"]] = item
            last_ts = max(item["timestamp"] for item in normalized)
            if last_ts < cursor:
                raise RuntimeError(f"open_interest_pagination_stalled:{symbol}")
            cursor = last_ts + (MS_HOUR if self.provider == "okx" else 1)
            if len(normalized) < (100 if self.provider == "okx" else 2):
                break
        return [collected[k] for k in sorted(collected)]

    def probe_data_vision(self) -> dict:
        base = "https://data.binance.vision/data/futures/um"
        samples = {
            "btc_1h_klines": f"{base}/monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2026-10.zip",
            "btc_funding": f"{base}/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10.zip",
            "btc_daily_metrics": f"{base}/daily/metrics/BTCUSDT/BTCUSDT-metrics-2026-11-07.zip",
        }
        results = []
        for name, url in samples.items():
            try:
                checksum_response = self.http.get(url + ".CHECKSUM")
                checksum_response.raise_for_status()
                expected = checksum_response.text.strip().split()[0]
                response = self.http.get(url)
                response.raise_for_status()
                payload = response.content
                actual = hashlib.sha256(payload).hexdigest()
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    csv_name = next((x for x in archive.namelist() if x.lower().endswith(".csv")), None)
                    if not csv_name:
                        raise ValueError("archive_missing_csv")
                    with archive.open(csv_name) as stream:
                        first_lines = [line.decode("utf-8", "replace").strip() for _,line in zip(range(3),stream)]
                results.append({"dataset":name,"passed":actual==expected,"http_status":response.status_code,
                                "bytes":len(payload),"checksum_match":actual==expected,
                                "csv_file":csv_name,"first_rows":first_lines})
            except Exception as exc:
                results.append({"dataset":name,"passed":False,"error":type(exc).__name__,
                                "detail":str(exc)[:180]})
        return {"provider":"Binance Data Vision public archive",
                "passed":sum(x["passed"] for x in results),"total":len(results),"checks":results}

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
        probe = self.probe_okx() if self.provider == "okx" else self.probe_binance()
        bybit_probe = self.probe_bybit()
        if not probe["passed"]:
            raise RuntimeError(f"{self.provider}_probe_failed; see probe report")
        symbols = self.discover_symbols(target_count, min_listing_ms=since_ms)
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
                provider_dir = "okx_swap" if self.provider == "okx" else "binance_usdm"
                reports[market_id] = {
                    "ohlcv":gaps,
                    "funding":{"rows":len(funding),"first_timestamp_utc":self._utc(funding[0]["timestamp"]) if funding else None,
                           "last_timestamp_utc":self._utc(funding[-1]["timestamp"]) if funding else None,
                           "coverage_days":round((funding[-1]["timestamp"]-funding[0]["timestamp"])/MS_DAY,2) if len(funding)>1 else 0,
                           "coverage_of_requested_window_pct":round(100*((funding[-1]["timestamp"]-funding[0]["timestamp"])/max(now_ms-since_ms,1)),3) if len(funding)>1 else 0},
                    "open_interest":{"rows":len(oi),"coverage_days":round((oi[-1]["timestamp"]-oi[0]["timestamp"])/MS_DAY,2) if len(oi)>1 else 0,
                                     "label":"OKX_PUBLIC_HISTORY_WINDOW_30D" if self.provider == "okx" else "BINANCE_PUBLIC_HISTORY_LIMIT_30D"},
                    "files":{
                        "ohlcv":self._write_parquet(f"{provider_dir}/ohlcv_1h/{safe}.parquet",ohlcv),
                        "funding":self._write_parquet(f"{provider_dir}/funding/{safe}.parquet",funding),
                        "open_interest":self._write_parquet(f"{provider_dir}/open_interest_1h/{safe}.parquet",oi),
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
        missing_total = max(expected_total-actual_total,0)
        report={
            "stage":1,"version":f"v1_ccxt_parquet_{self.provider}","provider":self.provider_name,
            "generated_at_utc":datetime.now(timezone.utc).isoformat(),
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
            "primary_provider":self.provider,"primary_provider_probe":probe,
            "bybit_probe":bybit_probe,"symbols":reports,
            "limitations":{
                "open_interest":f"{self.provider_name} historical open-interest coverage is limited to the latest 30 days in this Stage 1 collector; not a 2-year series.",
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
