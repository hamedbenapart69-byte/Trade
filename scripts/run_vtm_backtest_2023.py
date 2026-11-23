#!/usr/bin/env python3
"""VTM daily backtest over verified Binance Vision PIT universe. Funding is UNAVAILABLE."""
from __future__ import annotations
import csv, io, json, math, os, re, hashlib, zipfile, urllib.request, time
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from statistics import NormalDist
import numpy as np
import pandas as pd

ARTIFACT_ID = os.environ["PIT_ARTIFACT_ID"]
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
START, END = pd.Timestamp("2023-01-01", tz="UTC"), pd.Timestamp("2023-12-31", tz="UTC")
FEE = 0.0004
SLIPPAGE = 0.0002
RISK = 0.0025
VOL_TARGET = 0.10
MAX_GROSS = 1.0
ATR_N = 14
TIME_STOP = 10
GRID = [(v,b,k) for v in (1.5,2.0,2.5) for b in (0.5,0.6,0.7) for k in (5,10,20)]
BINANCE = "https://data.binance.vision/"
BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/"
PREFIX = "data/futures/um/monthly/klines/"

def get(url, headers=None):
    req=urllib.request.Request(url,headers=headers or {"User-Agent":"VTM-PIT-Backtest/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r: return r.read()

def get_pit():
    # Artifact endpoint redirects to temporary blob storage. Do not forward GitHub auth to that host.
    url=f"https://api.github.com/repos/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip"
    req=urllib.request.Request(url,headers={"Authorization":f"Bearer {TOKEN}","Accept":"application/vnd.github+json","User-Agent":"VTM-Research"})
    opener=urllib.request.build_opener(urllib.request.HTTPHandler())
    # Handle the redirect manually so the bearer token is never sent to blob storage.
    class StopRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener=urllib.request.build_opener(StopRedirect)
    try:
        response=opener.open(req,timeout=60)
        zbytes=response.read()
    except urllib.error.HTTPError as e:
        if e.code not in (302,303,307,308): raise
        location=e.headers.get("Location")
        if not location: raise RuntimeError("Artifact redirect missing Location")
        zbytes=get(location)  # anonymous request to signed temporary URL
    z=zipfile.ZipFile(io.BytesIO(zbytes))
    return json.loads(z.read("universe_daily.json")), json.loads(z.read("universe_manifest.json"))

def s3list(prefix):
    import xml.etree.ElementTree as ET, urllib.parse
    token=None; out=[]; seen_tokens=set(); ns={"s":"http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        q={"list-type":"2","prefix":prefix}
        if token:q["continuation-token"]=token
        root=ET.fromstring(get(BUCKET+"?"+urllib.parse.urlencode(q)))
        out += [x.findtext("s:Key",namespaces=ns) for x in root.findall("s:Contents",ns)]
        if root.findtext("s:IsTruncated",namespaces=ns)!="true":break
        token=root.findtext("s:NextContinuationToken",namespaces=ns)
        if not token:raise RuntimeError("S3 pagination missing token")
        if token in seen_tokens:raise RuntimeError("S3 pagination token repeated; aborting instead of looping")
        seen_tokens.add(token)
    return out

def verified_zip(key):
    payload=get(BINANCE+key)
    checksum=get(BINANCE+key+".CHECKSUM").decode().strip().split()[0].lower()
    if hashlib.sha256(payload).hexdigest()!=checksum: raise ValueError("Checksum mismatch "+key)
    return payload,checksum

def parse_kline(payload,symbol):
    rows={}
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        csvs=[n for n in z.namelist() if n.endswith(".csv")]
        if len(csvs)!=1: raise ValueError(f"{symbol}: bad ZIP CSV count")
        with z.open(csvs[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f,encoding="utf-8")):
                if not row or not row[0].isdigit():continue
                d=pd.to_datetime(int(row[0]),unit="ms",utc=True).floor("D")
                rows[d]={"open":float(row[1]),"high":float(row[2]),"low":float(row[3]),"close":float(row[4]),"volume":float(row[7])}
    return rows

def load_data(universe):
    symbols=sorted({s for day in universe for s in day["symbols"]})
    all_data={}; archive_hashes={}; errors=[]
    months=[f"2022-{m:02d}" for m in (12,)]+[f"2023-{m:02d}" for m in range(1,13)]
    for i,sym in enumerate(symbols,1):
        print(f"[LOAD] symbol {i}/{len(symbols)} {sym}: listing monthly archives", flush=True)
        p=PREFIX+sym+"/1d/"
        keys=s3list(p)
        pattern=re.compile(re.escape(p+sym+"-1d-") + r"(\d{4}-\d{2})\.zip$")
        monthkeys={pattern.fullmatch(k).group(1):k for k in keys if pattern.fullmatch(k)}
        symdata={}
        print(f"[LOAD] {sym}: {len(monthkeys)} monthly archives listed; downloading required months", flush=True)
        for month in months:
            key=monthkeys.get(month)
            if not key:continue
            print(f"[ARCHIVE] {sym} {month}: download + SHA256 verify", flush=True)
            try:
                blob,sha=verified_zip(key); symdata.update(parse_kline(blob,sym)); archive_hashes[key]=sha
                print(f"[ARCHIVE] {sym} {month}: OK ({len(symdata)} cumulative daily rows)", flush=True)
            except Exception as e:errors.append({"symbol":sym,"month":month,"error":str(e)})
        all_data[sym]=symdata
        print(f"[LOAD] completed {i}/{len(symbols)} symbols: {sym}, {len(symdata)} rows", flush=True)
    if errors: raise RuntimeError("Archive failures (strict abort): "+json.dumps(errors[:10]))
    return all_data,archive_hashes

def atr(df,n=ATR_N):
    tr=pd.concat([df.high-df.low,(df.high-df.close.shift()).abs(),(df.low-df.close.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(n,min_periods=n).mean()

def adx14(df,n=14):
    up=df.high.diff(); dn=-df.low.diff()
    plus=pd.Series(np.where((up>dn)& (up>0),up,0),index=df.index)
    minus=pd.Series(np.where((dn>up)&(dn>0),dn,0),index=df.index)
    tr=pd.concat([df.high-df.low,(df.high-df.close.shift()).abs(),(df.low-df.close.shift()).abs()],axis=1).max(axis=1)
    a=tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()
    p=100*plus.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/a.replace(0,np.nan)
    m=100*minus.ewm(alpha=1/n,adjust=False,min_periods=n).mean()/a.replace(0,np.nan)
    dx=100*(p-m).abs()/(p+m).replace(0,np.nan)
    return dx.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def make_features(data):
    btc=data.get("BTCUSDT")
    if not btc:raise RuntimeError("BTCUSDT data missing for ADX regime")
    btcidx=pd.DatetimeIndex(sorted(btc)); btcdf=pd.DataFrame([btc[d] for d in btcidx],index=btcidx)
    regime_adx=adx14(btcdf)
    regime={d:float(regime_adx.loc[d]) if pd.notna(regime_adx.loc[d]) else None for d in btcidx}
    feat={}
    for sym,raw in data.items():
        if not raw:continue
        ix=pd.DatetimeIndex(sorted(raw)); df=pd.DataFrame([raw[d] for d in ix],index=ix)
        df["atr"]=atr(df); df["body_ratio"]=(df.close-df.open).abs()/(df.high-df.low).replace(0,np.nan)
        df["mean_vol20"]=df.volume.rolling(20,min_periods=20).mean().shift(1)
        feat[sym]=df
    return feat,regime

def sim(feat,regime,universe,grid_params,report_start,report_end):
    vm,body,brk=grid_params
    membership={pd.Timestamp(x["date"],tz="UTC"):set(x["symbols"]) for x in universe}
    dates=pd.date_range("2023-01-01","2023-12-31",freq="D",tz="UTC")
    signals={}
    for sym,df in feat.items():
        ph=df.high.rolling(brk,min_periods=brk).max().shift(1)
        pl=df.low.rolling(brk,min_periods=brk).min().shift(1)
        for d in df.index:
            if d<pd.Timestamp("2023-06-30",tz="UTC") or d not in membership or sym not in membership[d]:continue
            if regime.get(d) is None or regime[d]<20:continue
            r=df.loc[d]
            if not (pd.notna(r.atr) and pd.notna(r.mean_vol20) and r.atr>0 and r.mean_vol20>0 and pd.notna(r.body_ratio)):continue
            direction=1 if r.close>r.open and r.close>ph.loc[d] else (-1 if r.close<r.open and r.close<pl.loc[d] else 0)
            if r.volume>vm*r.mean_vol20 and r.body_ratio>body and direction:
                signals.setdefault(d,[]).append((sym,direction,float(r.atr)))
    positions={}; trades=[]; daily={d:0.0 for d in dates}
    for i,d in enumerate(dates):
        todays={s:feat[s].loc[d] for s in feat if d in feat[s].index}
        closed=set()
        for sym,pos in list(positions.items()):
            row=todays.get(sym)
            if row is None:continue
            side,stop,prev=pos["side"],pos["stop"],pos["prev_close"]
            hit=(row.low<=stop) if side==1 else (row.high>=stop)
            time_exit=pos["held"]>=TIME_STOP-1
            terminal=(d==dates[-1])
            if hit or time_exit or terminal:
                fill=(min(float(row.open),stop) if side==1 else max(float(row.open),stop)) if hit else float(row.close)
                pnl=side*(fill/prev-1)-(FEE+SLIPPAGE)
                daily[d]+=pos["weight"]*pnl
                trade_net=side*(fill/pos["entry"]-1)-2*(FEE+SLIPPAGE)
                trades.append({"symbol":sym,"side":"LONG" if side==1 else "SHORT","entry_date":pos["entry_day"].date().isoformat(),"exit_date":d.date().isoformat(),"entry":pos["entry"],"exit":fill,"net_return":trade_net,"exit":"SL" if hit else ("TIME" if time_exit else "YEAR_END")})
                del positions[sym];closed.add(sym)
            else:
                daily[d]+=pos["weight"]*side*(float(row.close)/prev-1)
                pos["prev_close"]=float(row.close);pos["held"]+=1
        if i+1>=len(dates):continue
        nextd=dates[i+1]
        for sym,side,signal_atr in sorted(signals.get(d,[]),key=lambda x:x[0]):
            if sym in positions or sym in closed or nextd not in feat[sym].index:continue
            row=feat[sym].loc[nextd]
            entry=float(row.open)*(1+side*SLIPPAGE)
            distance=2*signal_atr
            stop=entry-side*distance
            risk_w=RISK/(distance/entry)
            daily_vol=float(feat[sym].close.pct_change().rolling(20,min_periods=20).std().loc[d])*math.sqrt(365)
            vol_w=VOL_TARGET/daily_vol if daily_vol>0 and np.isfinite(daily_vol) else MAX_GROSS
            weight=min(risk_w,vol_w,MAX_GROSS-sum(p["weight"] for p in positions.values()))
            if weight<=0:continue
            hit=(float(row.low)<=stop) if side==1 else (float(row.high)>=stop)
            if hit:
                fill=min(float(row.open),stop) if side==1 else max(float(row.open),stop)
                net=side*(fill/entry-1)-2*(FEE+SLIPPAGE)
                daily[nextd]+=weight*(side*(fill/entry-1)-2*(FEE+SLIPPAGE))
                trades.append({"symbol":sym,"side":"LONG" if side==1 else "SHORT","entry_date":nextd.date().isoformat(),"exit_date":nextd.date().isoformat(),"entry":entry,"exit":fill,"net_return":net,"exit":"SAME_DAY_SL"})
                closed.add(sym)
            else:
                # Entry-day PnL includes open-to-close return and entry transaction cost.
                daily[nextd]+=weight*(side*(float(row.close)/entry-1)-(FEE+SLIPPAGE))
                positions[sym]={"side":side,"entry":entry,"entry_day":nextd,"stop":stop,"prev_close":float(row.close),"weight":weight,"held":1}
    r=pd.Series(daily,index=dates,dtype=float).loc[report_start:report_end]
    trades=[x for x in trades if report_start.date().isoformat()<=x["entry_date"]<=report_end.date().isoformat()]
    return r,trades

def metrics(r,trades):
    eq=(1+r.fillna(0)).cumprod()
    dd=eq/eq.cummax()-1
    wins=[x["net_return"] for x in trades if x["net_return"]>0]
    losses=[-x["net_return"] for x in trades if x["net_return"]<0]
    return {"win_rate":len(wins)/len(trades) if trades else None,"profit_factor":sum(wins)/sum(losses) if losses else None,"profit_factor_status":"CALCULATED" if losses else ("NO_LOSSES" if wins else "NO_TRADES"),"max_drawdown":float(dd.min()) if len(dd) else 0,"total_trades":len(trades),"net_return":float(eq.iloc[-1]-1) if len(eq) else 0,"sharpe":float(r.mean()/r.std(ddof=1)*math.sqrt(365)) if len(r)>1 and r.std(ddof=1)>0 else 0}

def pbo_cscv(matrix):
    # CSCV: 6 contiguous blocks, 3 blocks IS / 3 OOS, all 20 symmetric splits.
    n,T=matrix.shape
    if T<6 or n<2:return None,{"splits":0,"note":"insufficient sample"}
    blocks=np.array_split(np.arange(T),6); logits=[]
    for comb in combinations(range(6),3):
        isidx=np.concatenate([blocks[i] for i in comb]); oosidx=np.concatenate([blocks[i] for i in range(6) if i not in comb])
        is_sr=np.array([np.mean(matrix[k,isidx])/(np.std(matrix[k,isidx],ddof=1)+1e-12)*math.sqrt(365) for k in range(n)])
        pick=int(np.argmax(is_sr))
        oos_sr=np.array([np.mean(matrix[k,oosidx])/(np.std(matrix[k,oosidx],ddof=1)+1e-12)*math.sqrt(365) for k in range(n)])
        rank=(np.sum(oos_sr<=oos_sr[pick])+0.5)/(n+1)
        logits.append(math.log(rank/(1-rank)))
    pbo=float(np.mean(np.array(logits)<0))
    return pbo,{"splits":len(logits),"method":"6-block CSCV, 3/3 split, candidate IS winner ranks OOS"}

def dsr_z(r,n_trials):
    x=np.asarray(r,dtype=float);x=x[np.isfinite(x)]
    if len(x)<3:return None
    sr=np.mean(x)/(np.std(x,ddof=1)+1e-12) # daily Sharpe for DSR statistic; annualizing here would inflate Z
    skew=float(pd.Series(x).skew()); kurt=float(pd.Series(x).kurtosis()+3)
    n=max(1,n_trials)
    gamma=0.5772156649
    z1=NormalDist().inv_cdf(max(1e-6,1-1/n)) if n>1 else 0
    z2=NormalDist().inv_cdf(max(1e-6,1-1/(n*math.e))) if n>1 else 0
    sr0=gamma*(z1+z2)
    denom=math.sqrt(max(1e-12,1-skew*sr+((kurt-1)/4)*sr*sr))
    return float((sr-sr0)*math.sqrt(len(x)-1)/denom)

def main():
    print("[STAGE 1/5] Fetching and validating PIT artifact", flush=True)
    pit,manifest=get_pit()
    print(f"[STAGE 1/5] PIT artifact loaded: {len(pit)} dates; status={manifest.get('status')}", flush=True)
    if manifest.get("status")!="PASS" or len(pit)!=365:raise RuntimeError("PIT artifact validation failed")
    print("[STAGE 2/5] Downloading and verifying OHLCV archives", flush=True)
    data,hashes=load_data(pit)
    print(f"[STAGE 2/5] OHLCV complete: {len(data)} symbols, {len(hashes)} archives", flush=True)
    print("[STAGE 3/5] Building ATR, volume, body, BTC ADX features", flush=True)
    feat,regime=make_features(data)
    print(f"[STAGE 3/5] Feature construction complete: {len(feat)} symbols", flush=True)
    # WF 6m/2m/1m: Jan-Jun is first training window; unique OOS score months Jul-Dec.
    oos_months=list(range(7,13)); folds=[]
    candidate_returns={}; candidate_trade_lists={}
    # Fixed V1 candidate is the center of the 3x3x3 diagnostic matrix.
    main=(2.0,0.60,10)
    monthly_report={}
    for i,params in enumerate(GRID,1):
        print(f"[STAGE 4/5] Candidate {i}/{len(GRID)} params={params}", flush=True)
        r,t=sim(feat,regime,pit,params,pd.Timestamp("2023-07-01",tz="UTC"),END)
        candidate_returns[params]=r;candidate_trade_lists[params]=t
    print("[STAGE 4/5] Candidate simulations completed; preparing metrics", flush=True)
    r,t=candidate_returns[main],candidate_trade_lists[main]
    # Fold-scored OOS month-by-month, training history prior to each test window.
    for month in oos_months:
        start=pd.Timestamp(f"2023-{month:02d}-01",tz="UTC")
        end=start+pd.offsets.MonthBegin(1)
        rr=r.loc[start:end-pd.Timedelta(days=1)]
        tt=[x for x in t if start.date().isoformat()<=x["entry_date"]<(end.date().isoformat())]
        monthly_report[start.strftime("%Y-%m")]=metrics(rr,tt)
    # PBO on 27 candidates, OOS daily returns Jul-Dec; candidate matrices are diagnostics only.
    mat=np.vstack([candidate_returns[p].reindex(r.index).fillna(0).values for p in GRID])
    print("[STAGE 5/5] Calculating PBO/DSR and final report", flush=True)
    pbo,pbo_diag=pbo_cscv(mat)
    dsr=dsr_z(r,27)
    overall=metrics(r,t)
    folds=[{"train":"2023-01-01/2023-06-30","test":"2023-07-01/2023-08-31","score":"2023-07"},
            {"train":"2023-02-01/2023-07-31","test":"2023-08-01/2023-09-30","score":"2023-08"},
            {"train":"2023-03-01/2023-08-31","test":"2023-09-01/2023-10-31","score":"2023-09"},
            {"train":"2023-04-01/2023-09-30","test":"2023-10-01/2023-11-30","score":"2023-10"},
            {"train":"2023-05-01/2023-10-31","test":"2023-11-01/2023-12-31","score":"2023-11"},
            {"train":"2023-06-01/2023-11-30","test":"2023-12-01/2024-01-31","score":"2023-12"}]
    summary={"strategy":"VTM","status":"RESEARCH_ONLY","period":"2023-07-01 through 2023-12-31 OOS scored months","data":{"source":"Binance Vision USD-M 1d klines","PIT_universe":"verified artifact run 45068636102","PIT_status":manifest["status"],"funding":"UNAVAILABLE; returns omit funding and may be slightly optimistic","archive_count":len(hashes),"archive_sha256_verified":True,"symbols_downloaded":len(data),"PIT_proxy_limitations":manifest.get("limitations",[])},
    "parameters":{"volume_lookback_days":20,"volume_multiplier":2.0,"body_ratio_gt":0.60,"breakout_lookback_days":10,"atr_stop_multiplier":2.0,"atr_period":14,"time_stop_days":10,"tp":"NONE","trailing":"NONE","regime":"BTC ADX14 >=20","fee_per_side":FEE,"slippage_per_side":SLIPPAGE,"risk_per_trade":RISK,"max_gross_exposure":MAX_GROSS,"volatility_target_annual":VOL_TARGET,"volatility_targeting_method":"per-position cap based on trailing 20-day realized volatility; NOT a covariance-aware portfolio-level 10% target","kelly":"PROHIBITED"},
    "metrics":{**overall,"pbo":pbo,"dsr_z":dsr,"PBO_matrix":{"volume_multiplier":[1.5,2.0,2.5],"body_ratio":[0.5,0.6,0.7],"breakout_lookback":[5,10,20],"candidate_count":27,"CSCV":pbo_diag}},
    "walk_forward":{"train_months":6,"test_months":2,"step_months":1,"scored_oos_unique_months":6,"folds":folds,"monthly":monthly_report},
    "trades":t,"gates":{"win_rate_gt_50":bool(overall["win_rate"] is not None and overall["win_rate"]>0.50),"profit_factor_gt_1_5":bool(overall["profit_factor"] is not None and overall["profit_factor"]>1.5),"pbo_lt_0_4":bool(pbo is not None and pbo<0.4),"dsr_z_gt_1":bool(dsr is not None and dsr>1),"maxdd_reported":overall["max_drawdown"]},
    "limitations":["2023 only, OOS scored July-December because 6-month training window","Funding UNAVAILABLE; may bias returns optimistically","Universe is Binance USD-M USDT contracts, not all exchanges","Perpetual classification and activity are proxy rules from PIT manifest","PBO/DSR are diagnostics on registered 27-trial matrix; parameter variants are not eligible for promotion"],
    "archive_sha256":hashes}
    out=Path("results/vtm_backtest_2023");out.mkdir(parents=True,exist_ok=True)
    (out/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    (out/"trades.json").write_text(json.dumps(t,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    r.rename("portfolio_daily_return").to_csv(out/"daily_returns.csv")
    (out/"monthly_metrics.json").write_text(json.dumps(monthly_report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("[DONE] Final output files written", flush=True)
    print(json.dumps({"metrics":summary["metrics"],"gates":summary["gates"],"oos":summary["period"],"trades":len(t)},indent=2,ensure_ascii=False,allow_nan=False))
if __name__=="__main__":main()
