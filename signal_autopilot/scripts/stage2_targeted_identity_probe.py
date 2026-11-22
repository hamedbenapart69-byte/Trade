#!/usr/bin/env python3
"""Stage 2 targeted OKX instrument identity probe for HOT and PEPE contracts."""
import json, time, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone

TARGETS = [
    ("HOT-USDT-SWAP", "HOTUSDT"),
    ("1000PEPE-USDT-SWAP", "1000PEPEUSDT"),
    ("PEPE-USDT-SWAP", "1000PEPEUSDT"),
]
BASE = "https://www.okx.com/api/v5/public/instruments?instType=SWAP&instId="

def probe(inst_id, expected):
    url = BASE + urllib.parse.quote(inst_id, safe="")
    req = urllib.request.Request(url, headers={"User-Agent":"CFSS-Stage2-Identity-Probe/1.0","Accept":"application/json"})
    start=time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw=response.read(500000)
            body=json.loads(raw)
            rows=body.get("data",[]) if isinstance(body,dict) else []
            elapsed=int((time.time()-start)*1000)
            row=rows[0] if rows else None
            valid=response.status==200 and body.get("code")=="0" and row is not None and row.get("instId")==inst_id
            metadata={}
            if row:
                for key in ("instId","instType","ctType","ctVal","ctValCcy","settleCcy","quoteCcy","baseCcy","uly","state","tickSz","lotSz"):
                    if key in row: metadata[key]=row[key]
            # Eligibility is strict: OKX SWAP + USDT settlement + USDT quote + exact instrument ID.
            eligible=bool(valid and metadata.get("instType")=="SWAP" and metadata.get("settleCcy")=="USDT" and metadata.get("quoteCcy")=="USDT")
            # PEPE substitute is deliberately never eligible for the Binance 1000x contract.
            if expected=="1000PEPEUSDT" and inst_id!="1000PEPE-USDT-SWAP": eligible=False
            return {"requested_instId":inst_id,"target_symbol":expected,"http_status":response.status,"elapsed_ms":elapsed,"okx_code":body.get("code"),"okx_msg":body.get("msg"),"row_count":len(rows),"exact_identity_match":bool(valid),"metadata":metadata,"eligible_as_target":eligible,"error":None}
    except urllib.error.HTTPError as exc:
        payload=exc.read(500).decode("utf-8",errors="replace")
        return {"requested_instId":inst_id,"target_symbol":expected,"http_status":exc.code,"elapsed_ms":int((time.time()-start)*1000),"okx_code":None,"okx_msg":None,"row_count":0,"exact_identity_match":False,"metadata":{},"eligible_as_target":False,"error":payload}
    except Exception as exc:
        return {"requested_instId":inst_id,"target_symbol":expected,"http_status":None,"elapsed_ms":int((time.time()-start)*1000),"okx_code":None,"okx_msg":None,"row_count":0,"exact_identity_match":False,"metadata":{},"eligible_as_target":False,"error":type(exc).__name__+":"+str(exc)}

def main():
    results=[probe(inst, target) for inst,target in TARGETS]
    hot=next(r for r in results if r["requested_instId"]=="HOT-USDT-SWAP")
    pepe1000=next(r for r in results if r["requested_instId"]=="1000PEPE-USDT-SWAP")
    pepe=next(r for r in results if r["requested_instId"]=="PEPE-USDT-SWAP")
    # Universe starts at 25 confirmed OKX instruments; HOT adds one only with metadata identity.
    universe=25+(1 if hot["eligible_as_target"] else 0)
    if pepe1000["eligible_as_target"]: universe+=1
    decision={"minimum_universe":25,"confirmed_universe":universe,"hot_added":hot["eligible_as_target"],"1000pepe_added":pepe1000["eligible_as_target"],"pepe_contract_mismatch_excluded":pepe["exact_identity_match"],"stage2_provider_gate": "PASS_CANDIDATE" if universe>=25 else "FAIL"}
    out={"schema":"stage2_targeted_identity_probe.v1","checked_at_utc":datetime.now(timezone.utc).isoformat(),"results":results,"decision":decision}
    print(json.dumps(out,ensure_ascii=False,indent=2))
    with open("artifacts/stage2-targeted-identity-probe.json","w",encoding="utf-8") as f: json.dump(out,f,ensure_ascii=False,indent=2)
if __name__=="__main__": main()
