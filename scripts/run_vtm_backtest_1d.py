#!/usr/bin/env python3
"""VTM 1D point-in-time research backtest. No exchange account or order execution."""
from __future__ import annotations
import concurrent.futures, csv, hashlib, io, json, math, re, time, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
from statistics import NormalDist
import numpy as np
import pandas as pd

BUCKET="https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"
BASE="https://data.binance.vision/"
ROOT="data/futures/um/monthly/klines/"
MONTHS=pd.period_range("2022-07","2026-10",freq="M").astype(str).tolist()
STARTS={"2023":{"start":date(2023,1,1),"end":date(2023,12,31)},
        "2024_2026":{"start":date(2024,1,1),"end":date(2026,10,31)}}
MULTIPLIERS=(1.8,2.0,2.2)
FEE_SIDE=0.0004
SLIPPAGE_SIDE=0.0002
RISK_PER_TRADE=0.0025
MAX_GROSS=1.0
TARGET_VOL=0.10
VOL_LOOKBACK=20
MAX_HOLD=10
OUT=Path("results/vtm_1d")

def get(url:str)->bytes:
    err=None
    for k in range(4):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"VTM-Research/1.0"})
            with urllib.request.urlopen(req,timeout=45) as r: return r.read()
        except Exception as e: err=e; time.sleep(min(2**k,10))
    raise RuntimeError(f"GET failed {url}: {err}")

def list_keys(prefix:str)->list[str]:
    keys=[]; token=None
    ns={"s":"http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        q={"list-type":"2","prefix":prefix}
        if token:q["continuation-token"]=token
        root=ET.fromstring(get(BUCKET+"?"+urllib.parse.urlencode(q)))
        keys += [x.findtext("s:Key",default="",namespaces=ns) for x in root.findall("s:Contents",ns)]
        if root.findtext("s:IsTruncated",default="false",namespaces=ns).lower()!="true":break
        token=root.findtext("s:NextContinuationToken",default="",namespaces=ns)
        if not token:raise RuntimeError("S3 pagination token missing")
    return keys

def symbols()->list[str]:
    ns={"s":"http://s3.amazonaws.com/doc/2006-03-01/"}
    root=ET.fromstring(get(BUCKET+"?"+urllib.parse.urlencode({"list-type":"2","prefix":ROOT,"delimiter":"/"})))
    out=set()
    for x in root.findall("s:CommonPrefixes",ns):
        p=x.findtext("s:Prefix",default="",namespaces=ns)
        sym=p[len(ROOT):].strip("/").upper()
        if sym.endswith("USDT") and "_" not in sym and re.fullmatch(r"[A-Z0-9]+",sym):out.add(sym)
    return sorted(out)

def read_symbol(sym:str):
    keys=list_keys(f"{ROOT}{sym}/1d/")
    pat=re.compile(re.escape(f"{ROOT}{sym}/1d/{sym}-1d-")+r"(\d{4}-\d{2})\.zip$")
    rows={}
    for key in keys:
        m=pat.fullmatch(key)
        if not m or m.group(1) not in MONTHS:continue
        raw=get(BASE+key)
        checksum=get(BASE+key+".CHECKSUM").decode().strip().split()[0].lower()
        if hashlib.sha256(raw).hexdigest()!=checksum:raise ValueError(f"SHA256 mismatch: {key}")
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=[n for n in z.namelist() if n.endswith(".csv")]
            if len(names)!=1:raise ValueError(f"Unexpected ZIP members: {key}")
            for r in csv.reader(io.TextIOWrapper(z.open(names[0]),encoding="utf-8")):
                if not r or not r[0].isdigit():continue
                d=datetime.fromtimestamp(int(r[0])/1000,tz=timezone.utc).date()
                if date(2022,7,1)<=d<=date(2026,10,31):
                    rows[d]=(float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[7]))
    return sym,rows

def adx14(rows):
    idx=sorted(rows); h=pd.Series({d:rows[d][1] for d in idx}); l=pd.Series({d:rows[d][2] for d in idx}); c=pd.Series({d:rows[d][3] for d in idx})
    up=h.diff(); dn=-l.diff()
    plus=pd.Series(np.where((up>dn)&(up>0),up,0.0),index=h.index)
    minus=pd.Series(np.where((dn>up)&(dn>0),dn,0.0),index=h.index)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    p=100*plus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr
    n=100*minus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr
    dx=100*(p-n).abs()/(p+n).replace(0,np.nan)
    return dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()

def make_universe(data):
    days=pd.date_range("2023-01-01","2026-10-31",freq="D").date
    universe={}; counts=[]
    for d in days:
        members=[]
        for s,x in data.items():
            if d not in x:continue
            prior=[d-timedelta(days=i) for i in range(30,0,-1)]
            if any(q not in x for q in prior):continue
            if sum(x[q][4] for q in prior)/30>10_000_000:members.append(s)
        members.sort(); universe[d]=members
        counts.append({"date":d.isoformat(),"symbol_count":len(members)})
    return universe,counts

def features(data,btc_adx):
    out={}
    for s,x in data.items():
        ds=sorted(x); qv=pd.Series({d:x[d][4] for d in ds})
        volmean=qv.shift(1).rolling(20,min_periods=20).mean()
        prevhigh=pd.Series({d:x[d][1] for d in ds}).shift(1).rolling(10,min_periods=10).max()
        tr=[]
        prevc=None
        for d in ds:
            o,h,l,c,_=x[d]
            tr.append(max(h-l,abs(h-prevc),abs(l-prevc)) if prevc is not None else h-l)
            prevc=c
        atr=pd.Series(tr,index=ds).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        sig={}
        for i,d in enumerate(ds):
            o,h,l,c,_=x[d]
            rng=h-l
            body=(c-o)/rng if rng>0 else 0.0
            adx=btc_adx.get(d,np.nan)
            if (pd.notna(volmean.iloc[i]) and qv.iloc[i]>0 and qv.iloc[i]>2.0*volmean.iloc[i]
                and body>0.60 and c>prevhigh.iloc[i] and pd.notna(atr.iloc[i]) and pd.notna(adx) and adx>=20):
                sig[d]={"atr":float(atr.iloc[i]),"qv":float(qv.iloc[i])}
            out.setdefault(s,{})[d]=sig.get(d)
    return out

def simulate(data, universe, sigs, btc_adx, multiplier, period):
    start,end=period["start"],period["end"]
    # 6m train, 2m test, 1m step; score only the first month of each test window.
    first=start+pd.DateOffset(months=6)
    score_months=set(); t=first
    while t<=pd.Timestamp(end,tz="UTC"):
        score_months.add(t.strftime("%Y-%m"))
        t+=pd.DateOffset(months=1)
    dates=[d for d in sorted(universe) if start<=d<=end]
    pending={}; positions={}; equity=1.0; daily=[]; trades=[]
    prev_day=None; recent_returns=[]
    for d in dates:
        dayret=0.0
        # Signal from prior completed UTC day enters at today's open.
        for s,signal in pending.pop(d,[]):
            if s not in universe[d] or s in positions or d not in data[s]:continue
            o,h,l,c,_=data[s][d]
            stop=o-multiplier*signal["atr"]
            if stop<=0:continue
            stop_pct=(o-stop)/o
            vol= float(np.std(recent_returns[-VOL_LOOKBACK:],ddof=1)*math.sqrt(365)) if len(recent_returns)>=VOL_LOOKBACK else TARGET_VOL
            vol_scale=min(1.0,TARGET_VOL/max(vol,1e-9))
            risk_weight=RISK_PER_TRADE/stop_pct
            gross_now=sum(p["notional"]/max(equity,1e-9) for p in positions.values())
            notional=min(equity*risk_weight*vol_scale,max(0.0,equity*MAX_GROSS-equity*gross_now))
            if notional<=0:continue
            positions[s]={"entry":o,"prev":o,"stop":stop,"notional":notional,"bars":0,"entry_date":d,"gross_cost":2*(FEE_SIDE+SLIPPAGE_SIDE),"pnl":-notional*(FEE_SIDE+SLIPPAGE_SIDE)}
        for s,p in list(positions.items()):
            o,h,l,c,_=data[s][d]
            p["bars"]+=1
            exit_price=None; reason=None
            if o<=p["stop"]:exit_price=o;reason="SL_GAP"
            elif l<=p["stop"]:exit_price=p["stop"];reason="SL"
            elif p["bars"]>=MAX_HOLD:exit_price=c;reason="TIME_STOP"
            mark=exit_price if exit_price is not None else c
            base=p["prev"]
            pnl=p["notional"]*(mark/base-1.0)
            if exit_price is not None:pnl-=p["notional"]*(FEE_SIDE+SLIPPAGE_SIDE)
            p["pnl"]+=pnl; dayret+=pnl/max(equity,1e-9)
            p["prev"]=mark
            if exit_price is not None:
                net=p["pnl"]/p["notional"]
                trades.append({"symbol":s,"entry_date":p["entry_date"].isoformat(),"exit_date":d.isoformat(),"exit_reason":reason,"entry":p["entry"],"exit":exit_price,"stop":p["stop"],"net_return":net})
                del positions[s]
        equity*=max(0.000001,1.0+dayret)
        daily.append((d,dayret))
        recent_returns.append(dayret)
        # Signals are calculated on today's close; enter on next available UTC date.
        nd=d+timedelta(days=1)
        for s in universe[d]:
            z=sigs.get(s,{}).get(d)
            if z and nd in data.get(s,{}):pending.setdefault(nd,[]).append((s,z))
        prev_day=d
    # Liquidate any remaining positions at final close, explicitly included in trade list.
    if dates:
        d=dates[-1]
        for s,p in list(positions.items()):
            c=data[s][d][3]; pnl=p["notional"]*(c/p["prev"]-1)-p["notional"]*(FEE_SIDE+SLIPPAGE_SIDE)
            p["pnl"]+=pnl
            trades.append({"symbol":s,"entry_date":p["entry_date"].isoformat(),"exit_date":d.isoformat(),"exit_reason":"DATA_END","entry":p["entry"],"exit":c,"stop":p["stop"],"net_return":p["pnl"]/p["notional"]})
    return daily,trades

def stats(daily,trades):
    r=np.array([x[1] for x in daily],dtype=float)
    wins=[t["net_return"] for t in trades if t["net_return"]>0]
    losses=[-t["net_return"] for t in trades if t["net_return"]<0]
    eq=np.cumprod(1+r) if len(r) else np.array([1.0])
    dd=eq/np.maximum.accumulate(eq)-1
    pf=sum(wins)/sum(losses) if losses else (float("inf") if wins else 0.0)
    return {"win_rate":len(wins)/len(trades) if trades else None,"profit_factor":pf if math.isfinite(pf) else "Infinity",
            "max_drawdown":float(dd.min()) if len(dd) else 0.0,"total_trades":len(trades),
            "net_return":float(eq[-1]-1),"annualized_sharpe":float(np.mean(r)/np.std(r,ddof=1)*math.sqrt(365)) if len(r)>1 and np.std(r,ddof=1)>0 else None}

def main():
    from backtest_guard import pbo,deflated_sharpe_ratio
    OUT.mkdir(parents=True,exist_ok=True)
    syms=symbols(); print(f"Candidate symbol folders: {len(syms)}",flush=True)
    data={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        fut={ex.submit(read_symbol,s):s for s in syms}
        for f in concurrent.futures.as_completed(fut):
            s,rows=f.result()
            if rows:data[s]=rows
            print(f"{s}: {len(rows)} bars",flush=True)
    if "BTCUSDT" not in data:raise RuntimeError("BTCUSDT daily history missing")
    universe,counts=make_universe(data)
    btcadx=adx14(data["BTCUSDT"])
    sigs=features(data,btcadx)
    all_results={}
    for pname,period in STARTS.items():
        candidates={}; trade_sets={}
        for mult in MULTIPLIERS:
            dly,tr=simulate(data,universe,sigs,btcadx,mult,period)
            score_months=set()
            t=pd.Timestamp(period["start"],tz="UTC")+pd.DateOffset(months=6)
            while t<=pd.Timestamp(period["end"],tz="UTC"):
                score_months.add(t.strftime("%Y-%m"));t+=pd.DateOffset(months=1)
            dly=[x for x in dly if x[0].strftime("%Y-%m") in score_months]
            tr=[x for x in tr if x["entry_date"][:7] in score_months]
            candidates[str(mult)]=dly;trade_sets[str(mult)]=tr
        main_daily=candidates["2.0"];main_trades=trade_sets["2.0"]
        idx=sorted(set(x[0] for x in main_daily))
        matrix=np.column_stack([[dict(candidates[str(m)]).get(d,0.0) for d in idx] for m in MULTIPLIERS])
        pbores=pbo(matrix,n_splits=8)
        dsrprob=deflated_sharpe_ratio(np.array([x[1] for x in main_daily]),n_trials=3,periods_per_year=365)
        dsrz=float(NormalDist().inv_cdf(float(np.clip(dsrprob,1e-12,1-1e-12))))
        met=stats(main_daily,main_trades)
        met.update({"pbo":float(pbores.pbo),"pbo_splits":pbores.n_splits_evaluated,"dsr_probability":float(dsrprob),"dsr_z":dsrz,
                    "candidate_multipliers":list(MULTIPLIERS),"oos_start":idx[0].isoformat() if idx else None,"oos_end":idx[-1].isoformat() if idx else None})
        all_results[pname]={"metrics":met,"candidate_metrics":{m:stats(candidates[m],trade_sets[m]) for m in candidates}}
    monthly={}
    for period in ("2023","2024_2026"):
        lo,hi=STARTS[period]["start"],STARTS[period]["end"]
        months=pd.period_range(lo,hi,freq="M")
        monthly[period]=[]
        for mo in months:
            ds=[x for x in counts if x["date"][:7]==str(mo)]
            monthly[period].append({"month":str(mo),"mean_universe":round(float(np.mean([x["symbol_count"] for x in ds])),2),"min":min(x["symbol_count"] for x in ds),"max":max(x["symbol_count"] for x in ds)})
    manifest={"status":"COMPLETED_WITH_LIMITATIONS","timeframe":"1D","symbols_with_data":len(data),"periods":{k:[v["start"].isoformat(),v["end"].isoformat()] for k,v in STARTS.items()},
              "bars_source":"Binance Vision USD-M daily Kline archives; SHA-256 checksum verified",
              "universe":"PIT: 30 prior UTC calendar days mean Quote Asset Volume > 10M USDT; current day excluded from liquidity mean; current-day bar required",
              "perpetual_classification":"USDT suffix/no dated-delivery suffix; naming proxy, not historical exchangeInfo snapshots",
              "entry":"Signal after daily close; next UTC daily open",
              "exit":"2x ATR14 stop (gap-aware) or 10 daily bars time stop; no TP/trailing",
              "regime":"BTCUSDT ADX14 >= 20",
              "costs":{"fee_per_side":FEE_SIDE,"slippage_per_side":SLIPPAGE_SIDE,"funding":"UNAVAILABLE_NOT_INCLUDED"},
              "risk":{"annual_vol_target":TARGET_VOL,"risk_per_trade":RISK_PER_TRADE,"max_gross":MAX_GROSS,"sizing":"stop-based; vol scaling from prior 20 portfolio daily returns"},
              "walk_forward":"6m train / 2m test / 1m step; unique first month of each test window scored; fixed strategy, no parameter fitting",
              "pbo":"CSCV over three pre-registered volume multipliers 1.8/2.0/2.2; only three candidates, low matrix breadth",
              "limitations":["Funding costs not included because the funding archive has not been acquired; net performance may be overstated.",
              "Perpetual contract status is a naming-convention proxy, not verified historical exchangeInfo.",
              "No 4H test in this run.","Only one long direction was coded from the previously specified long-entry rule; short-side rules were not supplied."]}
    payload={"manifest":manifest,"results":all_results,"monthly_universe":monthly}
    (OUT/"vtm_1d_summary.json").write_text(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    with (OUT/"vtm_1d_monthly_universe.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["period","month","mean_universe","min","max"]);w.writeheader()
        for p,rows in monthly.items():
            for x in rows:w.writerow({"period":p,**x})
    print(json.dumps(payload,indent=2,ensure_ascii=False,allow_nan=False),flush=True)

if __name__=="__main__":main()
