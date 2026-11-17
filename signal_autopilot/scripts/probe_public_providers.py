"""Probe public provider endpoints from the server runner; no user connectivity required."""
from __future__ import annotations
import argparse, json, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROBES = [
 {"id":"okx_public_perpetual_ticker","provider":"OKX","category":"futures_market","url":"https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT-SWAP","format":"json"},
 {"id":"bybit_linear_ohlcv","provider":"Bybit","category":"futures_ohlcv","url":"https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=60&limit=2","format":"json"},
 {"id":"binance_usdm_ohlcv","provider":"Binance USD-M","category":"futures_ohlcv","url":"https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=2","format":"json"},
 {"id":"bitget_usdt_futures_ticker","provider":"Bitget","category":"futures_market","url":"https://api.bitget.com/api/v2/mix/market/ticker?productType=USDT-FUTURES&symbol=BTCUSDT","format":"json"},
 {"id":"kucoin_futures_ohlcv","provider":"KuCoin Futures","category":"futures_ohlcv","url":"https://api-futures.kucoin.com/api/v1/kline/query?symbol=XBTUSDTM&granularity=60","format":"json"},
 {"id":"coinboss_cross_exchange_oi","provider":"CoinBoss","category":"derivatives_aggregator","url":"https://www.coinboss.com/api/sd/oi?coin=BTC","format":"json","license_gate":"REVIEW_REQUIRED","cost_gate":"FREE_CURRENT_PERIOD_ONLY"},
 {"id":"defillama_chain_tvl","provider":"DefiLlama","category":"onchain_context","url":"https://api.llama.fi/v2/historicalChainTvl","format":"json"},
 {"id":"alternative_me_fear_greed","provider":"Alternative.me","category":"sentiment","url":"https://api.alternative.me/fng/?limit=1","format":"json","license_gate":"ATTRIBUTION_REQUIRED"},
 {"id":"coindesk_rss","provider":"CoinDesk RSS","category":"news","url":"https://www.coindesk.com/arc/outboundfeeds/rss/","format":"xml","license_gate":"PUBLISHER_TERMS_REVIEW_REQUIRED"},
]

def validate_payload(probe_id: str, raw: bytes, fmt: str) -> tuple[bool, str]:
 try:
  if fmt == "xml":
   root=ET.fromstring(raw); items=root.findall("./channel/item")
   return bool(items), "rss_items_present" if items else "rss_items_missing"
  payload=json.loads(raw.decode("utf-8"))
 except (UnicodeDecodeError,json.JSONDecodeError,ET.ParseError) as exc:
  return False, "parse_error:"+type(exc).__name__
 if probe_id=="okx_public_perpetual_ticker":
  ok=isinstance(payload,dict) and payload.get("code")=="0" and bool(payload.get("data"))
 elif probe_id=="bybit_linear_ohlcv":
  result=payload.get("result",{}) if isinstance(payload,dict) else {}
  ok=payload.get("retCode")==0 and bool(result.get("list")) if isinstance(result,dict) else False
 elif probe_id=="binance_usdm_ohlcv":
  ok=isinstance(payload,list) and bool(payload) and isinstance(payload[0],list) and len(payload[0])>=6
 elif probe_id=="bitget_usdt_futures_ticker":
  ok=isinstance(payload,dict) and payload.get("code")=="00000" and bool(payload.get("data"))
 elif probe_id=="kucoin_futures_ohlcv":
  ok=isinstance(payload,dict) and payload.get("code")=="200000" and bool(payload.get("data"))
 elif probe_id=="coinboss_cross_exchange_oi":
  ok=isinstance(payload,dict) and payload.get("success") is True and payload.get("asof") is not None
 elif probe_id=="defillama_chain_tvl":
  ok=isinstance(payload,list) and bool(payload) and isinstance(payload[-1],dict)
 elif probe_id=="alternative_me_fear_greed":
  data=payload.get("data",[]) if isinstance(payload,dict) else []
  ok=isinstance(data,list) and bool(data) and "value" in data[0] and "timestamp" in data[0]
 else:
  return False,"unknown_probe_id"
 return bool(ok),"schema_valid" if ok else "schema_invalid_or_empty"

def probe_one(probe: dict[str,str], opener: Callable[...,Any] | None=None, timeout: float=15.0) -> dict[str,Any]:
 opener=opener or urllib.request.urlopen
 started=time.perf_counter()
 record={"id":probe["id"],"provider":probe["provider"],"category":probe["category"],"url":probe["url"],
         "checked_at_utc":datetime.now(timezone.utc).isoformat(),"runtime":"github_actions",
         "license_gate":probe.get("license_gate","REVIEW_ENDPOINT_TERMS"),
         "cost_gate":probe.get("cost_gate","PUBLIC_ENDPOINT_COST_REQUIRES_RECHECK")}
 request=urllib.request.Request(probe["url"],headers={"User-Agent":"Trade-ProviderHealthProbe/1.0","Accept":"application/json, application/xml, text/xml"},method="GET")
 try:
  with opener(request,timeout=timeout) as response:
   status_code=int(getattr(response,"status",response.getcode()))
   raw=response.read()
  record["http_status"]=status_code
  record["latency_ms"]=round((time.perf_counter()-started)*1000,2)
  if status_code!=200:
   record.update(status="HTTP_ERROR",reason=f"http_{status_code}")
   if status_code in (403,451): record["status"]="BLOCKED_FROM_RUNNER"
   elif status_code==429: record["status"]="RATE_LIMITED"
   return record
  valid,reason=validate_payload(probe["id"],raw,probe["format"])
  record.update(status="RUNTIME_PASS" if valid else "RUNTIME_DEGRADED",reason=reason)
 except urllib.error.HTTPError as exc:
  record.update(http_status=exc.code,latency_ms=round((time.perf_counter()-started)*1000,2),
                status="BLOCKED_FROM_RUNNER" if exc.code in (403,451) else ("RATE_LIMITED" if exc.code==429 else "HTTP_ERROR"),
                reason=f"http_{exc.code}")
 except (urllib.error.URLError,TimeoutError,OSError) as exc:
  record.update(latency_ms=round((time.perf_counter()-started)*1000,2),status="NETWORK_ERROR",reason=type(exc).__name__)
 return record

def run_probes() -> dict[str,Any]:
 checked=datetime.now(timezone.utc).isoformat()
 results=[probe_one(probe) for probe in PROBES]
 counts={}
 for item in results: counts[item["status"]]=counts.get(item["status"],0)+1
 return {"generated_at_utc":checked,"runtime":"github_actions","user_location_used":False,
         "user_credentials_used":False,"trading_credentials_used":False,"probe_count":len(results),
         "status_counts":counts,"providers":results}

def main() -> int:
 parser=argparse.ArgumentParser()
 parser.add_argument("--output",type=Path,default=Path("provider_health.json"))
 args=parser.parse_args()
 report=run_probes()
 args.output.parent.mkdir(parents=True,exist_ok=True)
 args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"probe_count":report["probe_count"],"status_counts":report["status_counts"]},ensure_ascii=False))
 return 0

if __name__=="__main__": raise SystemExit(main())
