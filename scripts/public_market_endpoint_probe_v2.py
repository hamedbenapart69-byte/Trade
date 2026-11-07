#!/usr/bin/env python3
"""Probe additional public perpetual-market APIs without credentials."""
from __future__ import annotations
import json, time, urllib.error, urllib.parse, urllib.request

UA="FuturesSignalAutopilot/5.0 endpoint-probe"
TARGETS=[
 ("okx_swap_instruments","GET","https://www.okx.com/api/v5/public/instruments",{"instType":"SWAP"},None),
 ("okx_swap_ticker","GET","https://www.okx.com/api/v5/market/ticker",{"instId":"BTC-USDT-SWAP"},None),
 ("okx_swap_candles","GET","https://www.okx.com/api/v5/market/candles",{"instId":"BTC-USDT-SWAP","bar":"1H","limit":"3"},None),
 ("okx_funding","GET","https://www.okx.com/api/v5/public/funding-rate",{"instId":"BTC-USDT-SWAP"},None),
 ("okx_open_interest","GET","https://www.okx.com/api/v5/public/open-interest",{"instType":"SWAP","instId":"BTC-USDT-SWAP"},None),
 ("okx_long_short","GET","https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",{"ccy":"BTC","period":"1H"},None),
 ("gate_usdt_contracts","GET","https://api.gateio.ws/api/v4/futures/usdt/contracts",{},None),
 ("gate_usdt_ticker","GET","https://api.gateio.ws/api/v4/futures/usdt/tickers",{"contract":"BTC_USDT"},None),
 ("gate_usdt_candles","GET","https://api.gateio.ws/api/v4/futures/usdt/candlesticks",{"contract":"BTC_USDT","interval":"1h","limit":"3"},None),
 ("gate_usdt_funding","GET","https://api.gateio.ws/api/v4/futures/usdt/funding_rate",{"contract":"BTC_USDT"},None),
 ("hyperliquid_meta","POST","https://api.hyperliquid.xyz/info",{},{"type":"metaAndAssetCtxs"}),
 ("hyperliquid_candles","POST","https://api.hyperliquid.xyz/info",{},{"type":"candleSnapshot","req":{"coin":"BTC","interval":"1h","startTime":1794000000000,"endTime":1794010000000}}),
]
def req_one(name,method,base,params,body):
 url=base
 headers={"User-Agent":UA,"Accept":"application/json"}
 data=None
 if method=="GET" and params:url+="?"+urllib.parse.urlencode(params)
 if method=="POST":headers["Content-Type"]="application/json";data=json.dumps(body).encode()
 request=urllib.request.Request(url,data=data,headers=headers,method=method)
 start=time.time()
 try:
  with urllib.request.urlopen(request,timeout=15) as resp:
   obj=json.loads(resp.read(2_000_000).decode());elapsed=round((time.time()-start)*1000)
   out={"name":name,"http_status":resp.status,"elapsed_ms":elapsed,"json":True}
   if name=="okx_swap_instruments":
    rows=obj.get("data",[]);btc=next((x for x in rows if x.get("instId")=="BTC-USDT-SWAP"),{})
    out.update({"code":obj.get("code"),"instrument_count":len(rows),"btc_contract":{k:btc.get(k) for k in ("instId","instType","ctType","state","baseCcy","quoteCcy","settleCcy","ctVal","ctValCcy","tickSz","lotSz","minSz")} if btc else None})
   elif name.startswith("okx_"):out.update({"code":obj.get("code"),"sample":obj.get("data",[])[:2]})
   elif name=="gate_usdt_contracts":
    rows=obj if isinstance(obj,list) else [];btc=next((x for x in rows if x.get("name")=="BTC_USDT"),{})
    out.update({"contract_count":len(rows),"btc_contract":{k:btc.get(k) for k in ("name","type","quanto_multiplier","leverage_min","leverage_max","maintenance_rate","order_price_round","order_size_min","order_size_max","in_delisting")} if btc else None})
   elif name.startswith("gate_"):out["sample"]=obj[:2] if isinstance(obj,list) else obj
   elif name=="hyperliquid_meta":
    assets=obj[0].get("universe",[]) if isinstance(obj,list) and obj else []
    btc=next((x for x in assets if x.get("name")=="BTC"),{})
    out.update({"asset_count":len(assets),"btc_asset":btc,"ctx_sample":obj[1][0] if isinstance(obj,list) and len(obj)>1 and obj[1] else None})
   else:out["sample"]=obj[:2] if isinstance(obj,list) else obj
   return out
 except urllib.error.HTTPError as e:return {"name":name,"http_status":e.code,"error":"http_error","elapsed_ms":round((time.time()-start)*1000)}
 except Exception as e:return {"name":name,"error":type(e).__name__,"detail":str(e)[:160],"elapsed_ms":round((time.time()-start)*1000)}
print(json.dumps({"probe_version":2,"generated_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"results":[req_one(*x) for x in TARGETS]},indent=2))
