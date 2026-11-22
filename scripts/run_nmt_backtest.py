#!/usr/bin/env python3
"""NMT-1D Ichimoku trend-following research backtest. OHLCV only."""
from __future__ import annotations
import json, os, zipfile
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from backtest_guard import pbo, deflated_sharpe_ratio

SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT","NEARUSDT","INJUSDT","UNIUSDT","FILUSDT","ARBUSDT","ENAUSDT","SUIUSDT","TAOUSDT","WLDUSDT","ZECUSDT","AAVEUSDT","QNTUSDT","RSRUSDT","ONEUSDT"]
TENKAN_KIJUN=[(9,26),(7,22),(10,30)]
VOLUME_MULTIPLIERS=[1.2,1.5,2.0]
SL_MULTIPLIERS=[1.2,1.5,2.0]
CONFIGS=list(product(TENKAN_KIJUN,VOLUME_MULTIPLIERS,SL_MULTIPLIERS))
START=pd.Timestamp("2024-11-01",tz="UTC"); END=pd.Timestamp("2026-10-31",tz="UTC")
TRAIN_MONTHS,TEST_MONTHS,STEP_MONTHS=6,2,1
FEE_PER_SIDE,SLIPPAGE_PER_SIDE=.0004,.0002
TRAIL_ATR_MULTIPLIER=2.0; ATR_PERIOD=14; VOLUME_LOOKBACK=20
ICHIMOKU_DISPLACEMENT=26; SENKOU_B_PERIOD=52

def load_data()->dict[str,pd.DataFrame]:
    d=Path("data")
    if not list(d.glob("*_1d.parquet")) and not list(d.glob("*_1d.csv")):
        zpath=Path(os.getenv("DATA_ZIP","data/binance-vision-1d.zip"))
        if not zpath.exists(): raise FileNotFoundError("OHLCV input missing")
        d.mkdir(exist_ok=True)
        with zipfile.ZipFile(zpath) as z: z.extractall(d)
    out={}
    for s in SYMBOLS:
        pq=d/f"{s}_1d.parquet"; cp=d/f"{s}_1d.csv"
        if pq.exists(): x=pd.read_parquet(pq)
        elif cp.exists(): x=pd.read_csv(cp)
        else: raise FileNotFoundError(f"Missing OHLCV for {s}")
        x.columns=[str(c).lower() for c in x.columns]
        if "open_time" in x: x["date"]=pd.to_datetime(x.open_time,unit="ms",utc=True).dt.floor("D")
        elif "open_time_utc" in x: x["date"]=pd.to_datetime(x.open_time_utc,utc=True).dt.floor("D")
        elif "date" in x: x["date"]=pd.to_datetime(x.date,utc=True).dt.floor("D")
        else: raise ValueError(f"{s}: timestamp column missing")
        x=x.sort_values("date").drop_duplicates("date").set_index("date").loc[START:END]
        cols=["open","high","low","close","volume"]
        if any(c not in x for c in cols): raise ValueError(f"{s}: OHLCV columns missing")
        if len(x)!=730: raise ValueError(f"{s}: expected 730 bars, got {len(x)}")
        if x[cols].isna().any().any() or (x[["open","high","low","close"]]<=0).any().any() or (x.volume<0).any():
            raise ValueError(f"{s}: invalid or missing OHLCV values")
        out[s]=x[cols].astype(float)
    return out

def features(x:pd.DataFrame,tenkan_n:int,kijun_n:int)->pd.DataFrame:
    f=x.copy()
    ten=(f.high.rolling(tenkan_n).max()+f.low.rolling(tenkan_n).min())/2
    kij=(f.high.rolling(kijun_n).max()+f.low.rolling(kijun_n).min())/2
    # shift(26) aligns the forward-plotted cloud with the candle visible today.
    sa=((ten+kij)/2).shift(ICHIMOKU_DISPLACEMENT)
    sb=((f.high.rolling(SENKOU_B_PERIOD).max()+f.low.rolling(SENKOU_B_PERIOD).min())/2).shift(ICHIMOKU_DISPLACEMENT)
    tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1)
    f["tenkan"],f["kijun"]=ten,kij
    f["cloud_top"],f["cloud_bottom"]=pd.concat([sa,sb],axis=1).max(axis=1),pd.concat([sa,sb],axis=1).min(axis=1)
    f["atr"]=tr.rolling(ATR_PERIOD).mean()
    f["volume_mean_prev"]=f.volume.rolling(VOLUME_LOOKBACK).mean().shift(1)
    f["chikou_long"]=f.close>f.close.shift(26)
    f["chikou_short"]=f.close<f.close.shift(26)
    return f

def signals(f:pd.DataFrame,volume_mult:float)->tuple[pd.Series,pd.Series]:
    vok=f.volume>volume_mult*f.volume_mean_prev
    long=(f.close>f.cloud_top)&(f.tenkan>f.kijun)&f.chikou_long&vok
    short=(f.close<f.cloud_bottom)&(f.tenkan<f.kijun)&f.chikou_short&vok
    return long.fillna(False),short.fillna(False)

def simulate_symbol(f:pd.DataFrame,long_sig:pd.Series,short_sig:pd.Series,sl_mult:float,
                    entry_start:pd.Timestamp,entry_end:pd.Timestamp,exit_end:pd.Timestamp)->tuple[pd.Series,list[dict]]:
    dates=f.index; daily=pd.Series(0.0,index=dates,dtype=float); trades=[]; pos=None
    i=max(ICHIMOKU_DISPLACEMENT+SENKOU_B_PERIOD,30)+2
    while i<len(f) and dates[i]<=exit_end:
        dt=dates[i]; bar=f.iloc[i]
        if pos is None:
            if dt<entry_start or dt>=entry_end or i+1>=len(f) or dates[i+1]>exit_end:
                i+=1; continue
            side=1 if bool(long_sig.iloc[i]) else (-1 if bool(short_sig.iloc[i]) else 0)
            if side==0 or not np.isfinite(bar.atr) or bar.atr<=0:
                i+=1; continue
            en=i+1; eb=f.iloc[en]; entry=float(eb.open)*(1+side*SLIPPAGE_PER_SIDE)
            pos={"side":side,"entry":entry,"entry_date":dates[en],"entry_index":en,
                 "stop":entry-side*sl_mult*float(bar.atr),"high_water":entry,
                 "low_water":entry,"prev_mark":entry}
            i=en
            continue
        side=pos["side"]; prev=f.iloc[i-1]
        # Trailing stop only uses data available before today's candle.
        if np.isfinite(prev.atr) and prev.atr>0:
            if side==1: pos["stop"]=max(pos["stop"],pos["high_water"]-TRAIL_ATR_MULTIPLIER*float(prev.atr))
            else: pos["stop"]=min(pos["stop"],pos["low_water"]+TRAIL_ATR_MULTIPLIER*float(prev.atr))
        stop_hit=(bar.low<=pos["stop"]) if side==1 else (bar.high>=pos["stop"])
        if stop_hit:
            fill=min(float(bar.open),pos["stop"]) if side==1 else max(float(bar.open),pos["stop"])
            reason="ATR_INITIAL_OR_TRAILING_STOP"
        elif (side==1 and bar.close<bar.kijun) or (side==-1 and bar.close>bar.kijun):
            fill=float(bar.close); reason="KIJUN_CLOSE"
        else: fill=float(bar.close); reason=None
        day_ret=side*(fill/pos["prev_mark"]-1.0)
        if pos["entry_index"]==i: day_ret-=FEE_PER_SIDE+SLIPPAGE_PER_SIDE
        if reason is not None: day_ret-=FEE_PER_SIDE+SLIPPAGE_PER_SIDE
        daily.iloc[i]=day_ret
        if reason is not None:
            net=side*(fill/pos["entry"]-1.0)-2*(FEE_PER_SIDE+SLIPPAGE_PER_SIDE)
            trades.append({"symbol":f.attrs.get("symbol",""),"side":"LONG" if side==1 else "SHORT",
                "entry_date":pos["entry_date"].date().isoformat(),"exit_date":dt.date().isoformat(),
                "entry":pos["entry"],"exit":fill,"net_return":net,"exit_reason":reason})
            pos=None
        else:
            pos["prev_mark"]=float(bar.close); pos["high_water"]=max(pos["high_water"],float(bar.high))
            pos["low_water"]=min(pos["low_water"],float(bar.low))
        i+=1
    if pos is not None:
        last_idx=min(len(f)-1,int(f.index.searchsorted(exit_end,side="right")-1))
        if last_idx>=pos["entry_index"]:
            last=f.iloc[last_idx]; fill=float(last.close); dt=f.index[last_idx]
            daily.iloc[last_idx]+=pos["side"]*(fill/pos["prev_mark"]-1.0)-(FEE_PER_SIDE+SLIPPAGE_PER_SIDE)
            net=pos["side"]*(fill/pos["entry"]-1.0)-2*(FEE_PER_SIDE+SLIPPAGE_PER_SIDE)
            trades.append({"symbol":f.attrs.get("symbol",""),"side":"LONG" if pos["side"]==1 else "SHORT",
                "entry_date":pos["entry_date"].date().isoformat(),"exit_date":dt.date().isoformat(),
                "entry":pos["entry"],"exit":fill,"net_return":net,"exit_reason":"END_OF_WINDOW"})
    return daily,trades

def run_portfolio(data:dict[str,pd.DataFrame],feature_cache:dict,cfg:tuple,entry_start:pd.Timestamp,
                  entry_end:pd.Timestamp,exit_end:pd.Timestamp)->tuple[pd.Series,list[dict]]:
    (tn,kn),vm,sm=cfg; streams=[]; trades=[]
    for symbol in data:
        f=feature_cache[(symbol,tn,kn)]
        ls,ss=signals(f,vm); r,t=simulate_symbol(f,ls,ss,sm,entry_start,entry_end,exit_end)
        streams.append(r.rename(symbol)); trades.extend(t)
    return pd.concat(streams,axis=1).mean(axis=1),trades

def metrics(r:pd.Series,trades:list[dict])->dict:
    a=np.asarray(r.fillna(0.0),dtype=float); eq=np.cumprod(1+a)
    dd=eq/np.maximum.accumulate(eq)-1 if len(eq) else np.array([])
    sd=float(np.std(a,ddof=1)) if len(a)>1 else 0.0
    wins=[t["net_return"] for t in trades if t["net_return"]>0]
    losses=[t["net_return"] for t in trades if t["net_return"]<=0]; gl=abs(sum(losses))
    return {"win_rate":len(wins)/len(trades) if trades else None,
        "profit_factor":sum(wins)/gl if gl>0 else (None if wins else 0.0),
        "max_dd":float(dd.min()) if len(dd) else 0.0,
        "sharpe":float(np.mean(a)/sd*np.sqrt(365)) if sd else 0.0,
        "trades_count":len(trades),"net_return":float(eq[-1]-1) if len(eq) else 0.0}

def make_folds(index:pd.DatetimeIndex)->list[tuple[pd.Timestamp,pd.Timestamp,pd.Timestamp]]:
    out=[]; te=index.min()+pd.DateOffset(months=TRAIN_MONTHS)
    last=index.max()-pd.DateOffset(months=TEST_MONTHS-1)
    while te<=last:
        out.append((te-pd.DateOffset(months=TRAIN_MONTHS),te,te+pd.DateOffset(months=TEST_MONTHS)))
        te+=pd.DateOffset(months=STEP_MONTHS)
    return out

def lrt_diagnosis(data:dict[str,pd.DataFrame])->dict:
    chosen={4:("2025-09-01","2025-11-01",.65,1),5:("2025-10-01","2025-12-01",.65,1),
            6:("2025-11-01","2026-01-01",.65,1),11:("2026-04-01","2026-06-01",.60,2),
            12:("2026-05-01","2026-07-01",.60,2),13:("2026-06-01","2026-08-01",.60,2)}
    rows=[]
    for fold,(start,end,threshold,alignment) in chosen.items():
        c={"raw_sweep":0,"after_lfs":0,"after_tenkan_kijun":0,"after_kumo":0}
        for x in data.values():
            f=x.copy(); ten=(f.high.rolling(9).max()+f.low.rolling(9).min())/2
            kij=(f.high.rolling(26).max()+f.low.rolling(26).min())/2
            ca=((ten+kij)/2).shift(26); cb=((f.high.rolling(52).max()+f.low.rolling(52).min())/2).shift(26)
            top=pd.concat([ca,cb],axis=1).max(axis=1); bot=pd.concat([ca,cb],axis=1).min(axis=1)
            lo=f.low.shift().rolling(20).min(); hi=f.high.shift().rolling(20).max()
            swl=(f.low<lo)&(f.close>lo); sws=(f.high>hi)&(f.close<hi)
            tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1)
            atr=tr.rolling(14).mean()
            def rank(s): return s.rolling(90,min_periods=30).apply(lambda a: float(np.mean(a[np.isfinite(a)]<=a[-1])) if np.isfinite(a[-1]) else np.nan,raw=True)
            lfs1=(rank(atr/f.close)+(1-rank(f.volume)))/2
            lfs4=1-rank(f.close.rolling(20).std()/f.close.rolling(20).mean())
            lfs=.25*lfs1+.2*.5+.2*.5+.2*lfs4+.15*.5
            mask=(f.index>=pd.Timestamp(start,tz="UTC"))&(f.index<pd.Timestamp(end,tz="UTC"))
            ql=swl[mask]; qs=sws[mask]; c["raw_sweep"]+=int(ql.sum()+qs.sum())
            ql=ql&(lfs[mask]>=threshold); qs=qs&(lfs[mask]>=threshold)
            c["after_lfs"]+=int(ql.sum()+qs.sum())
            ql=ql&(ten[mask]>kij[mask]); qs=qs&(ten[mask]<kij[mask])
            c["after_tenkan_kijun"]+=int(ql.sum()+qs.sum())
            if alignment>=2:
                ql=ql&(f.close[mask]>top[mask]); qs=qs&(f.close[mask]<bot[mask])
            c["after_kumo"]+=int(ql.sum()+qs.sum())
        rows.append({"fold":fold,"test_start":start,"test_end":end,"selected_lfs_threshold":threshold,
            "selected_alignment":alignment,"counts":c,
            "interpretation":"LFS gate eliminated all sweep candidates" if c["after_lfs"]==0 else
            ("Kumo gate eliminated remaining candidates" if c["after_kumo"]==0 else "Recheck prior zero-trade report")})
    return {"source_run_id":45060651042,"method":"Recomputed on the same 25-symbol OHLCV data and selected LRT configurations; diagnostic only.",
            "folds":rows}

def main():
    data=load_data(); folds=make_folds(next(iter(data.values())).index)
    feature_cache={}
    for symbol,x in data.items():
        for tn,kn in TENKAN_KIJUN:
            f=features(x,tn,kn); f.attrs["symbol"]=symbol
            feature_cache[(symbol,tn,kn)]=f
    fold_rows=[]; oos_parts=[]; trade_map={}
    for n,(tr_start,te_start,te_end) in enumerate(folds):
        scores=[]
        for cfg in CONFIGS:
            r,t=run_portfolio(data,feature_cache,cfg,tr_start,te_start,te_start)
            scores.append(metrics(r.loc[(r.index>=tr_start)&(r.index<te_start)],t)["sharpe"])
        selected=int(np.nanargmax(np.nan_to_num(scores,nan=-1e9))); cfg=CONFIGS[selected]
        r,tr=run_portfolio(data,feature_cache,cfg,te_start,te_end,te_end-pd.Timedelta(days=1))
        fold_rows.append({"fold":n,"train_start":tr_start.date().isoformat(),"test_start":te_start.date().isoformat(),
            "test_end":te_end.date().isoformat(),"selected_config":selected,
            "selected_parameters":{"tenkan":cfg[0][0],"kijun":cfg[0][1],"volume_multiplier":cfg[1],"sl_atr_multiplier":cfg[2]},
            "oos_metrics":metrics(r.loc[(r.index>=te_start)&(r.index<te_end)],tr)})
        oos_parts.append(r.loc[(r.index>=te_start)&(r.index<te_end)])
        for t in tr: trade_map.setdefault((t["symbol"],t["entry_date"]),t)
    oos=pd.concat(oos_parts).sort_index(); oos=oos[~oos.index.duplicated(keep="first")]
    oos_trades=list(trade_map.values())
    candidate_returns=[]
    for cfg in CONFIGS:
        r,_=run_portfolio(data,feature_cache,cfg,START,END+pd.Timedelta(days=1),END)
        candidate_returns.append(r.loc[START:END].to_numpy())
    pbo_value=float(pbo(np.asarray(candidate_returns).T,n_splits=8).pbo)
    dsr_prob=float(deflated_sharpe_ratio(oos.to_numpy(),n_trials=len(CONFIGS)))
    dsr_z=float(norm.ppf(np.clip(dsr_prob,1e-12,1-1e-12)))
    overall=metrics(oos,oos_trades)
    gates={"pbo_lt_0_4":pbo_value<.4,"dsr_z_gt_1":dsr_z>1.0,
           "oos_win_rate_gt_55":overall["win_rate"] is not None and overall["win_rate"]>.55,
           "profit_factor_gt_1":overall["profit_factor"] is not None and overall["profit_factor"]>1.0}
    gates["status"]="PASS" if all(gates.values()) else "NOT_VALIDATED"
    summary={"strategy":"NMT-1D","status":"RESEARCH_ONLY","data_type":"REAL OHLCV",
        "symbol_count":len(data),"bars_per_symbol":730,"parameter_combinations":len(CONFIGS),
        "parameter_grid":{"tenkan_kijun":TENKAN_KIJUN,"volume_multiplier":VOLUME_MULTIPLIERS,
                          "sl_atr_multiplier":SL_MULTIPLIERS,"trailing_atr_multiplier":TRAIL_ATR_MULTIPLIER},
        "rules":{"long":"Close > visible Kumo; Tenkan > Kijun; Close > Close[26]; volume > multiplier x prior 20-day average.",
                 "short":"Close < visible Kumo; Tenkan < Kijun; Close < Close[26]; volume > multiplier x prior 20-day average.",
                 "initial_stop":"Selected SL ATR multiplier x ATR(14).",
                 "exit":"Kijun close reversal or 2.0 x ATR trailing stop; no fixed take-profit.",
                 "costs":"0.04% fee + 0.02% slippage per side."},
        "walk_forward":{"train_months":TRAIN_MONTHS,"test_months":TEST_MONTHS,"step_months":STEP_MONTHS,
                        "fold_count":len(folds),"fold_results":fold_rows,
                        "overlap_policy":"OOS daily returns deduplicated by date, earliest fold retained; trades deduplicated by symbol and entry date."},
        "pbo":pbo_value,"dsr_probability":dsr_prob,"dsr_z":dsr_z,"selected_oos_metrics":overall,"gates":gates,
        "notes":["The supplied grids form 27 combinations, not 30; no unsupplied values were invented.",
                 "No order-book, funding, OI, exchange account, or order execution is used.",
                 "Research only; not a live signal."]}
    out=Path("results"); out.mkdir(exist_ok=True)
    (out/"nmt1d_summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
    (out/"lrt_zero_trade_fold_diagnosis.json").write_text(json.dumps(lrt_diagnosis(data),indent=2,allow_nan=False))
    for i,cfg in enumerate(CONFIGS):
        r,tr=run_portfolio(data,feature_cache,cfg,START,END+pd.Timedelta(days=1),END)
        item={"config_id":i,"parameters":{"tenkan":cfg[0][0],"kijun":cfg[0][1],
            "volume_multiplier":cfg[1],"sl_atr_multiplier":cfg[2]},
            "full_period_metrics":metrics(r.loc[START:END],tr)}
        (out/f"nmt1d_config_{i:02d}.json").write_text(json.dumps(item,indent=2,allow_nan=False))
    print(json.dumps(summary,indent=2,allow_nan=False))

if __name__=="__main__": main()
