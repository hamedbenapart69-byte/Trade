#!/usr/bin/env python3
"""Read-only connectivity/schema probe for public futures market-data endpoints."""
from __future__ import annotations
import json, time, urllib.error, urllib.parse, urllib.request

UA = "FuturesSignalAutopilot/5.0 endpoint-probe"
TARGETS = [
    ("binance_usdm_exchange_info", "https://fapi.binance.com/fapi/v1/exchangeInfo", None),
    ("binance_usdm_exchange_info_fapi1", "https://fapi1.binance.com/fapi/v1/exchangeInfo", None),
    ("bybit_linear_instruments", "https://api.bybit.com/v5/market/instruments-info", {"category":"linear","limit":"1000"}),
    ("bybit_linear_tickers", "https://api.bybit.com/v5/market/tickers", {"category":"linear","symbol":"BTCUSDT"}),
    ("bybit_linear_kline", "https://api.bybit.com/v5/market/kline", {"category":"linear","symbol":"BTCUSDT","interval":"60","limit":"3"}),
    ("bybit_funding_history", "https://api.bybit.com/v5/market/funding/history", {"category":"linear","symbol":"BTCUSDT","limit":"2"}),
    ("bybit_open_interest", "https://api.bybit.com/v5/market/open-interest", {"category":"linear","symbol":"BTCUSDT","intervalTime":"1h","limit":"2"}),
    ("bybit_long_short_ratio", "https://api.bybit.com/v5/market/account-ratio", {"category":"linear","symbol":"BTCUSDT"," period":"1h","limit":"2"}),
    ("coingecko_markets", "https://api.coingecko.com/api/v3/coins/markets", {"vs_currency":"usd","order":"market_cap_desc","per_page":"2","page":"1"}),
]

def probe(name, url, params):
    if params:
        clean={k.strip():v for k,v in params.items()}
        url += "?" + urllib.parse.urlencode(clean)
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json"})
    started=time.time()
    try:
        with urllib.request.urlopen(req,timeout=15) as resp:
            raw=resp.read(2_000_000)
            elapsed=round((time.time()-started)*1000)
            obj=json.loads(raw.decode("utf-8"))
            result={"name":name,"http_status":resp.status,"elapsed_ms":elapsed,"json":True}
            if name=="bybit_linear_instruments":
                rows=obj.get("result",{}).get("list",[])
                btc=next((x for x in rows if x.get("symbol")=="BTCUSDT"),{})
                result.update({"retCode":obj.get("retCode"),"instrument_count":len(rows),
                    "btc_contract":{k:btc.get(k) for k in ("symbol","contractType","status","baseCoin","quoteCoin","settleCoin","priceFilter","lotSizeFilter")} if btc else None})
            elif name=="bybit_linear_tickers":
                rows=obj.get("result",{}).get("list",[])
                result.update({"retCode":obj.get("retCode"),"btc_ticker":rows[0] if rows else None})
            elif name=="bybit_linear_kline":
                rows=obj.get("result",{}).get("list",[])
                result.update({"retCode":obj.get("retCode"),"sample_rows":rows[:2]})
            elif name=="bybit_funding_history":
                result.update({"retCode":obj.get("retCode"),"sample_rows":obj.get("result",{}).get("list",[])[:2]})
            elif name=="bybit_open_interest":
                result.update({"retCode":obj.get("retCode"),"sample_rows":obj.get("result",{}).get("list",[])[:2]})
            elif name=="bybit_long_short_ratio":
                result.update({"retCode":obj.get("retCode"),"sample_rows":obj.get("result",{}).get("list",[])[:2]})
            elif name.startswith("binance"):
                syms=obj.get("symbols",[])
                btc=next((x for x in syms if x.get("symbol")=="BTCUSDT"),{})
                result.update({"symbol_count":len(syms),"btc_contract":{k:btc.get(k) for k in ("symbol","pair","contractType","status","baseAsset","quoteAsset","marginAsset","filters")} if btc else None})
            else:
                result.update({"sample_count":len(obj) if isinstance(obj,list) else None,"sample":obj[:1] if isinstance(obj,list) else None})
            return result
    except urllib.error.HTTPError as e:
        return {"name":name,"http_status":e.code,"error":"http_error","elapsed_ms":round((time.time()-started)*1000)}
    except Exception as e:
        return {"name":name,"error":type(e).__name__,"detail":str(e)[:180],"elapsed_ms":round((time.time()-started)*1000)}

results=[probe(*x) for x in TARGETS]
print(json.dumps({"probe_version":1,"generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"results":results},indent=2))
