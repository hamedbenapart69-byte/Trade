"""Read-only public market data acquisition. No exchange credentials or trading methods."""
from __future__ import annotations
from datetime import datetime, timezone
import httpx
import ccxt

class MarketDataFetcher:
    def __init__(self, limit: int = 100):
        self.limit = limit
        self.exchange = ccxt.okx({"enableRateLimit": True, "timeout": 25000, "options": {"defaultType": "swap"}})

    def close(self):
        try: self.exchange.close()
        except Exception: pass

    @staticmethod
    def _utc_ms(value):
        return datetime.fromtimestamp(float(value)/1000, timezone.utc).isoformat() if value is not None else None

    def _coingecko_spot_fallback(self):
        response=httpx.get("https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency":"usd","order":"market_cap_desc","per_page":self.limit,"page":1},timeout=20)
        response.raise_for_status()
        return {"provider":"coingecko_spot_fallback","generated_at_utc":datetime.now(timezone.utc).isoformat(),
            "symbols_requested":self.limit,"symbols_processed":0,"fallback_used":True,
            "symbols":[{"symbol":(r.get("symbol") or "").upper()+"/USD:SPOT","last":r.get("current_price"),
                "ohlcv":None,"funding_rate":None,"open_interest":None,
                "availability":{"ohlcv":"UNAVAILABLE","funding":"UNAVAILABLE","open_interest":"UNAVAILABLE"},
                "errors":["spot_only_fallback_no_futures_data"]} for r in response.json()]}

    def fetch(self):
        try:
            markets=self.exchange.load_markets()
            tickers=self.exchange.fetch_tickers()
            candidates=[]
            for symbol,market in markets.items():
                if not (market.get("active") and market.get("swap") and market.get("linear") and market.get("quote")=="USDT" and market.get("settle")=="USDT"): continue
                ticker=tickers.get(symbol) or {}
                qv=ticker.get("quoteVolume")
                if qv is None:
                    info=ticker.get("info") or {}
                    try: qv=float(info.get("volCcy24h") or ticker.get("baseVolume") or 0)*float(ticker.get("last") or info.get("last") or 0)
                    except (TypeError,ValueError): qv=0
                candidates.append((float(qv or 0),symbol,ticker))
            candidates.sort(reverse=True,key=lambda x:x[0])
            output=[]
            for qv,symbol,ticker in candidates[:self.limit]:
                row={"symbol":symbol,"last":ticker.get("last"),"quote_volume_24h":qv,
                    "ticker_timestamp_utc":self._utc_ms(ticker.get("timestamp")),"ohlcv":None,
                    "funding_rate":None,"funding_timestamp_utc":None,"open_interest":None,
                    "open_interest_timestamp_utc":None,
                    "availability":{"ohlcv":"UNAVAILABLE","funding":"UNAVAILABLE","open_interest":"UNAVAILABLE"},"errors":[]}
                try:
                    candles=self.exchange.fetch_ohlcv(symbol,timeframe="1h",limit=70)
                    now_ms=int(datetime.now(timezone.utc).timestamp()*1000)
                    completed=[c for c in candles if c[0] is not None and int(c[0])+3_600_000<=now_ms]
                    row["ohlcv"]=[{"timestamp":int(c[0]),"timestamp_utc":self._utc_ms(c[0]),"open":float(c[1]),
                        "high":float(c[2]),"low":float(c[3]),"close":float(c[4]),"volume":float(c[5])} for c in completed]
                    if len(row["ohlcv"])>=52: row["availability"]["ohlcv"]="OK"
                except Exception as exc: row["errors"].append("ohlcv:"+type(exc).__name__)
                try:
                    f=self.exchange.fetch_funding_rate(symbol); row["funding_rate"]=f.get("fundingRate")
                    row["funding_timestamp_utc"]=self._utc_ms(f.get("timestamp"))
                    if row["funding_rate"] is not None: row["availability"]["funding"]="OK"
                except Exception as exc: row["errors"].append("funding:"+type(exc).__name__)
                try:
                    oi=self.exchange.fetch_open_interest(symbol)
                    row["open_interest"]=oi.get("openInterestAmount",oi.get("openInterestValue"))
                    row["open_interest_timestamp_utc"]=self._utc_ms(oi.get("timestamp"))
                    if row["open_interest"] is not None: row["availability"]["open_interest"]="OK"
                except Exception as exc: row["errors"].append("open_interest:"+type(exc).__name__)
                output.append(row)
            fg=None; fg_error=None
            try:
                r=httpx.get("https://api.alternative.me/fng/",params={"limit":1,"format":"json"},timeout=15)
                r.raise_for_status(); rows=r.json().get("data",[]); fg=rows[0] if rows else None
            except Exception as exc: fg_error=type(exc).__name__
            return {"provider":"okx","generated_at_utc":datetime.now(timezone.utc).isoformat(),
                "symbols_requested":self.limit,"symbols_processed":len(output),"symbols":output,
                "fear_greed":fg,"fear_greed_error":fg_error,"fallback_used":False}
        except Exception as okx_exc:
            try:
                fallback=self._coingecko_spot_fallback()
                fallback["primary_error"]=type(okx_exc).__name__
                return fallback
            except Exception as cg_exc:
                return {"provider":"none","generated_at_utc":datetime.now(timezone.utc).isoformat(),
                    "symbols_requested":self.limit,"symbols_processed":0,"symbols":[],"fallback_used":True,
                    "errors":{"okx":type(okx_exc).__name__,"coingecko":type(cg_exc).__name__}}
