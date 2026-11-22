#!/usr/bin/env python3
"""Stage 2 live-source probe: CoinGecko derivatives, OKX SWAP, Bybit linear."""
import json, time, urllib.request, urllib.error
from datetime import datetime, timezone

TARGETS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT","NEARUSDT","INJUSDT","UNIUSDT","FILUSDT","ARBUSDT","ENAUSDT","SUIUSDT","TAOUSDT","WLDUSDT","ZECUSDT","AAVEUSDT","QNTUSDT","RSRUSDT","ONEUSDT"]
URLS={
 "CoinGecko":"https://api.coingecko.com/api/v3/derivatives?include_tickers=unexpired",
 "OKX":"https://www.okx.com/api/v5/public/instruments?instType=SWAP",
 "Bybit":"https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000"
}
def fetch(name,url):
 req=urllib.request.Request(url,headers={"User-Agent":"CFSS-Stage2-Source-Probe/1.0","Accept":"application/json"})
 started=time.time()
 try:
  with urllib.request.urlopen(req,timeout=20) as res:
   raw=res.read(2_000_000)
   elapsed=int((time.time()-started)*1000)
   try: body=json.loads(raw)
   except Exception: body={"body_preview":raw.decode("utf-8",errors="replace")[:500]}
   rows=body if isinstance(body,list) else (body.get("data",[]) if isinstance(body,dict) else [])
   if name=="OKX" and isinstance(body,dict): rows=body.get("data",[])
   if name=="Bybit" and isinstance(body,dict): rows=(body.get("result") or {}).get("list",[])
   matched=[]
   for row in rows:
    if not isinstance(row,dict): continue
    sym=row.get("symbol") or row.get("ticker") or row.get("market") or row.get("contract")
    candidates=set()
    if sym: candidates.add(str(sym).upper())
    for k in ("symbol","base","target"):
     if row.get(k): candidates.add(str(row[k]).upper())
    # OKX SWAP identifiers are BASE-USDT-SWAP; normalize exact USDT contracts only.
    inst=row.get("instId")
    if isinstance(inst,str) and inst.upper().endswith("-USDT-SWAP"):
     candidates.add(inst.upper().replace("-USDT-SWAP","")+"USDT")
    for c in list(candidates):
     if c.endswith("-USDT"): candidates.add(c.replace("-USDT","USDT"))
    if candidates.intersection(TARGETS): matched.append(row)
   return {"source":name,"url":url,"status_code":res.status,"elapsed_ms":elapsed,"rate_limit_headers":{k:v for k,v in res.headers.items() if "rate" in k.lower() or "limit" in k.lower() or "remaining" in k.lower()},"response_type":type(body).__name__,"row_count":len(rows),"matched_target_rows":len(matched),"matched_target_symbols":sorted({(r.get("symbol") or r.get("ticker") or r.get("market") or r.get("instId") or "") for r in matched}),"sample_first_5":rows[:5],"matched_sample_first_5":matched[:5],"error":None}
 except urllib.error.HTTPError as e:
  body=e.read(600).decode("utf-8",errors="replace")
  return {"source":name,"url":url,"status_code":e.code,"elapsed_ms":int((time.time()-started)*1000),"rate_limit_headers":{k:v for k,v in e.headers.items() if "rate" in k.lower() or "limit" in k.lower() or "remaining" in k.lower()},"response_type":"HTTP_ERROR","row_count":0,"matched_target_rows":0,"sample_first_5":[],"matched_sample_first_5":[],"error":body[:600]}
 except Exception as e:
  return {"source":name,"url":url,"status_code":None,"elapsed_ms":int((time.time()-started)*1000),"rate_limit_headers":{},"response_type":"NETWORK_ERROR","row_count":0,"matched_target_rows":0,"sample_first_5":[],"matched_sample_first_5":[],"error":f"{type(e).__name__}:{e}"}
def main():
 out={"schema":"stage2_source_probe.v1","started_at_utc":datetime.now(timezone.utc).isoformat(),"target_count":len(TARGETS),"target_symbols":TARGETS,"source_results":[fetch(k,v) for k,v in URLS.items()]}
 out["summary"]={r["source"]:{"http_status":r["status_code"],"rows":r["row_count"],"target_matches":r["matched_target_rows"]} for r in out["source_results"]}
 out["all_sources_http_200"]=all(r["status_code"]==200 for r in out["source_results"])
 print(json.dumps(out,ensure_ascii=False,indent=2))
 with open("artifacts/stage2-source-probe.v1.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
if __name__=="__main__": main()
