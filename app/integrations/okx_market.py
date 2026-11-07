"""Read-only OKX USDT linear perpetual market-data adapter.

All instruments, prices, candles, funding and open-interest observations come from
the same venue so contract metadata cannot be mismatched with another venue's tape.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time
import httpx

from app.signals import Candle, DataError, INTERVALS


class OkxPublicMarketData:
    BASE = "https://www.okx.com"
    provider_name = "OKX public market-data API"
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=15.0, follow_redirects=True)
        self.own = client is None
        self.calls = 0
        self.last_call = 0.0
        self.last_by_path = {}
        self._instruments = None
        self._tickers = None
        self._indexes = None
        self._contracts = {}

    def _get(self, path: str, params: dict | None = None):
        now = time.monotonic()
        global_wait = 0.11 - (now - self.last_call)
        endpoint_interval = 0.41 if path == "/api/v5/rubik/stat/contracts/long-short-account-ratio" else 0.0
        endpoint_wait = endpoint_interval - (now - self.last_by_path.get(path, 0.0))
        wait = max(global_wait, endpoint_wait, 0.0)
        if wait > 0:
            time.sleep(wait)
        request_time = time.monotonic()
        self.last_call = request_time
        self.last_by_path[path] = request_time
        self.calls += 1
        try:
            response = self.client.get(self.BASE + path, params=params or {},
                headers={"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise DataError(f"okx_public_api_error:{path}:http_{status or type(exc).__name__}") from exc
        if not isinstance(payload, dict) or payload.get("code") != "0":
            raise DataError(f"okx_invalid_or_rejected_payload:{path}")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise DataError(f"okx_missing_data_array:{path}")
        return rows

    @staticmethod
    def _ms(value):
        try:
            n = int(value)
            return n if n > 10_000_000_000 else n * 1000
        except (TypeError, ValueError):
            return 0

    def discover(self):
        try:
            response = self.client.get("https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"false"},
                headers={"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise DataError("coingecko_discovery_unavailable") from exc
        if not isinstance(rows, list):
            raise DataError("invalid_coingecko_market_list")
        assets=[]
        for row in rows:
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            assets.append({"id":str(row.get("id","")),"symbol":str(row["symbol"]).upper(),
                "name":row.get("name"),"volume":float(row.get("total_volume") or 0),
                "market_cap_rank":row.get("market_cap_rank"),"current_price":float(row.get("current_price") or 0),
                "market_cap":float(row.get("market_cap") or 0)})
        return sorted(assets,key=lambda x:x["volume"],reverse=True)

    def _load_instruments(self):
        if self._instruments is None:
            rows=self._get("/api/v5/public/instruments",{"instType":"SWAP"})
            self._instruments={str(x.get("instId","")).upper():x for x in rows if isinstance(x,dict)}
        return self._instruments

    @staticmethod
    def _base_from_inst(inst_id):
        parts=str(inst_id).upper().split("-")
        return parts[0] if len(parts)==3 and parts[1]=="USDT" and parts[2]=="SWAP" else None

    def tracked_symbols(self):
        out=set()
        for inst_id,item in self._load_instruments().items():
            base=self._base_from_inst(inst_id)
            if base and item.get("instType")=="SWAP" and item.get("ctType")=="linear" and item.get("state")=="live" and item.get("settleCcy")=="USDT":
                out.add(base+"USDT")
        return out

    def contract_specs(self, symbols):
        instruments=self._load_instruments()
        out={}
        for symbol in symbols:
            sym=str(symbol).upper()
            if not sym.endswith("USDT"):
                continue
            base=sym[:-4]
            item=instruments.get(f"{base}-USDT-SWAP")
            if not item or item.get("instType")!="SWAP" or item.get("ctType")!="linear" or item.get("state")!="live" or item.get("settleCcy")!="USDT":
                continue
            try:
                tick=float(item["tickSz"]);step=float(item["lotSz"]);minimum=float(item["minSz"])
                multiplier=float(item["ctVal"]);max_leverage=float(item["lever"])
            except (KeyError,TypeError,ValueError):
                continue
            if min(tick,step,minimum,multiplier,max_leverage)<=0 or item.get("ctValCcy")!=base:
                continue
            max_sizes=[]
            for field in ("maxLmtSz","maxMktSz"):
                try:
                    value=float(item.get(field) or 0)
                    if value>0:max_sizes.append(value)
                except (TypeError,ValueError):
                    continue
            max_qty=min(max_sizes) if max_sizes else None
            out[sym]={"symbol":sym,"venue_symbol":item["instId"],"contract_type":"PERPETUAL",
                "status":"TRADING","base_asset":base,"quote_asset":"USDT","margin_asset":"USDT",
                "quantity_unit":"contracts","contract_multiplier":multiplier,"multiplier_currency":item["ctValCcy"],
                "tick_size":tick,"step_size":step,"min_qty":minimum,"min_notional":0.0,
                "max_qty":max_qty,"max_leverage":max_leverage,"source":"OKX public instruments API"}
            self._contracts[sym]=out[sym]
        return out

    def _load_tickers(self):
        if self._tickers is None:
            rows=self._get("/api/v5/market/tickers",{"instType":"SWAP"})
            self._tickers={str(x.get("instId","")).upper():x for x in rows if isinstance(x,dict)}
        return self._tickers

    def prices(self, symbols):
        tickers=self._load_tickers();out={}
        for symbol in symbols:
            base=str(symbol).upper()[:-4]
            row=tickers.get(f"{base}-USDT-SWAP")
            if not row:
                continue
            try:
                price=float(row["last"]);ts=self._ms(row.get("ts"))
                if price<=0 or not ts:
                    continue
                out[str(symbol).upper()]={"symbol":str(symbol).upper(),"price":price,"updatedAt":ts,
                    "high24h":float(row.get("high24h") or 0),"low24h":float(row.get("low24h") or 0),
                    "volume24h":float(row.get("volCcy24h") or 0),
                    "change24h":(price/float(row["open24h"])-1)*100 if float(row.get("open24h") or 0)>0 else None}
            except (TypeError,ValueError,KeyError,ZeroDivisionError):
                continue
        return out

    def candles(self, symbol, tf, limit=220):
        base=str(symbol).upper()[:-4]
        inst=f"{base}-USDT-SWAP"
        bar={"15m":"15m","1h":"1H","4h":"4H","1d":"1D"}.get(tf)
        if not bar:
            raise DataError("unsupported_okx_candle_interval")
        rows=self._get("/api/v5/market/candles",{"instId":inst,"bar":bar,"limit":str(min(int(limit),300))})
        out=[]
        interval=INTERVALS[tf]
        for row in reversed(rows):
            try:
                if len(row)<9:
                    raise ValueError("short candle row")
                ot=int(row[0]);vol_quote=float(row[7]);confirm=str(row[8])=="1"
                out.append(Candle(ot,float(row[1]),float(row[2]),float(row[3]),float(row[4]),
                    vol_quote,ot+interval-1,confirm))
            except (TypeError,ValueError,IndexError) as exc:
                raise DataError("invalid_okx_ohlcv_payload") from exc
        return out

    def _index_ticker(self, base):
        rows=self._get("/api/v5/market/index-tickers",{"quoteCcy":"USDT","instId":f"{base}-USDT"})
        return rows[0] if rows else {}

    def derivatives(self, symbols):
        out={}
        for symbol in symbols:
            sym=str(symbol).upper();base=sym[:-4];inst=f"{base}-USDT-SWAP"
            try:
                funding_rows=self._get("/api/v5/public/funding-rate",{"instId":inst})
                oi_rows=self._get("/api/v5/public/open-interest",{"instType":"SWAP","instId":inst})
                hist=self._get("/api/v5/rubik/stat/contracts/open-interest-history",{"instId":inst,"period":"1H"})
                ratio_rows=self._get("/api/v5/rubik/stat/contracts/long-short-account-ratio",{"ccy":base,"period":"1H"})
                mark_rows=self._get("/api/v5/public/mark-price",{"instType":"SWAP","instId":inst})
                ticker=self._load_tickers().get(inst,{})
                funding=funding_rows[0] if funding_rows else {}
                oi=oi_rows[0] if oi_rows else {}
                mark=mark_rows[0] if mark_rows else {}
                index=self._index_ticker(base)
                if not funding or not oi or not mark or not index or not ticker:
                    raise DataError("missing_okx_required_derivatives_fields")
                rate=float(funding["fundingRate"]);next_ts=self._ms(funding.get("nextFundingTime"))
                current_period_ts=self._ms(funding.get("fundingTime"))
                interval_hours=(next_ts-current_period_ts)/3_600_000 if next_ts and current_period_ts and next_ts>current_period_ts else 0
                oi_usd=float(oi.get("oiUsd") or 0);oi_ts=self._ms(oi.get("ts"))
                history=[]
                for h in hist:
                    if isinstance(h,list) and len(h)>=4:
                        history.append((self._ms(h[0]),float(h[3])))
                history.sort()
                def change_at(hours):
                    if not history or oi_usd<=0:return None
                    target=oi_ts-hours*3_600_000
                    candidates=[v for ts,v in history if ts<=target]
                    return (oi_usd/candidates[-1]-1)*100 if candidates and candidates[-1]>0 else None
                ratio=None;ratio_ts=0
                if ratio_rows:
                    row=ratio_rows[0]
                    if isinstance(row,list) and len(row)>1:
                        ratio=float(row[1]);ratio_ts=self._ms(row[0])
                ts_values=[self._ms(x) for x in (ticker.get("ts"),funding.get("ts"),oi.get("ts"),mark.get("ts"),index.get("ts"))]
                observed=min(x for x in ts_values if x>0) if all(x>0 for x in ts_values) else 0
                last=float(ticker.get("last") or 0);opened=float(ticker.get("open24h") or 0)
                out[sym]={"symbol":sym,"updatedAt":observed,"markPrice":float(mark["markPx"]),
                    "indexPrice":float(index["idxPx"]),"funding":{"rate":rate,"intervalHours":interval_hours,
                    "nextFundingTime":next_ts,"ratePct":rate*100},
                    "openInterest":{"contracts":float(oi.get("oi") or 0),"valueUsd":oi_usd,
                    "change4hPct":change_at(4),"change24hPct":change_at(24),
                    "priceChange24hPct":(last/opened-1)*100 if opened>0 else None},
                    "source":self.provider_name,"positioning":{"globalLongShortRatio":ratio,
                    "globalLongShortRatioObservedAtMs":ratio_ts,"topTraderLongShortRatio":None,
                    "topTraderLongShortRatioObservedAtMs":0,"takerBuySellRatio":None,
                    "takerBuySellRatioObservedAtMs":0,
                    "label":"okx_global_account_ratio" if ratio is not None else "unavailable"}}
            except (DataError,KeyError,TypeError,ValueError,IndexError) as exc:
                if isinstance(exc,DataError):
                    out[sym]={"symbol":sym,"error":str(exc)}
                else:
                    out[sym]={"symbol":sym,"error":"invalid_okx_derivatives_payload"}
        return out

    def smart_money(self):
        return {"traders":[],"positions":[],"signals":[],"traders_observed_at_ms":0,
            "positions_observed_at_ms":0,"signals_observed_at_ms":0,
            "note":"TraderSpy smart-money data not included in the OKX-native data path."}

    def close(self):
        if self.own:
            self.client.close()
