#!/usr/bin/env python3
"""Research LRT-1D OHLCV sweep; backtest-guard provides CSCV/PBO and DSR."""
import json, math, os, zipfile
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from backtest_guard import pbo, deflated_sharpe_ratio

SYMBOLS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT","NEARUSDT","INJUSDT","UNIUSDT","FILUSDT","ARBUSDT","ENAUSDT","SUIUSDT","TAOUSDT","WLDUSDT","ZECUSDT","AAVEUSDT","QNTUSDT","RSRUSDT","ONEUSDT"]
THRESH=[.55,.60,.65,.70,.75]; ALIGN=[1,2,3]; DIR=["both","long_only"]
START=pd.Timestamp("2024-11-01",tz="UTC"); END=pd.Timestamp("2026-10-31",tz="UTC")
TRAIN,TEST,STEP=6,2,1; FEE,SLIP=.0004,.0002; HOLD,RR=7,2.0

def load():
 d=Path("data")
 if not list(d.glob("*_1d.parquet")):
  z=Path(os.getenv("DATA_ZIP","data/binance-vision-1d.zip"))
  if not z.exists(): raise FileNotFoundError("Dataset absent: data/*.parquet or data ZIP")
  d.mkdir(exist_ok=True)
  with zipfile.ZipFile(z) as a: a.extractall(d)
 out={}
 for s in SYMBOLS:
  f=d/f"{s}_1d.parquet"
  if not f.exists(): raise FileNotFoundError(f"Missing {f}")
  x=pd.read_parquet(f); x["date"]=pd.to_datetime(x.open_time,unit="ms",utc=True).dt.floor("D")
  x=x.sort_values("date").drop_duplicates("date").set_index("date").loc[START:END]
  if len(x)!=730: raise ValueError(f"{s}: expected 730 rows, found {len(x)}")
  out[s]=x[["open","high","low","close","volume"]].astype(float)
 return out

def rank(s,w=90):
 def r(a):
  v=a[np.isfinite(a)]
  return float(np.mean(v<=a[-1])) if len(v)>=30 and np.isfinite(a[-1]) else np.nan
 return s.rolling(w,min_periods=30).apply(r,raw=True)

def feat(x):
 f=x.copy(); t=(f.high.rolling(9).max()+f.low.rolling(9).min())/2; k=(f.high.rolling(26).max()+f.low.rolling(26).min())/2
 f["tenkan"],f["kijun"]=t,k; f["ca"],f["cb"]=((t+k)/2).shift(26),((f.high.rolling(52).max()+f.low.rolling(52).min())/2).shift(26
 f["top"],f["bot"]=f[["ca","cb"]].max(axis=1),f[["ca","cb"]].min(axis=1)
 lo,hi=f.low.shift().rolling(20).min(),f.high.shift().rolling(20).max()
 f["swl"],f["sws"]=(f.low<lo)&(f.close>lo),(f.high>hi)&(f.close<hi)
 tr=pd.concat([f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()],axis=1).max(axis=1); f["atr"]=tr.rolling(14).mean()
 # Funding/positioning/OI unavailable in this OHLCV artifact; neutral values explicitly tagged PROXY.
 f["lfs1"]=(rank(f.atr/f.close)+(1-rank(f.volume)))/2; f["lfs2"],f["lfs3"],f["lfs5"]=.5,.5,.5; f["lfs4"]=1-rank(f.close.rolling(20).std()/f.close.rolling(20).mean()
 f["lfs"]=.25*f.lfs1+.2*f.lfs2+.2*f.lfs3+.2*f.lfs4+.15*f.lfs5
 return f

def confirm(f,a,s):
 c=f.tenkan>f.kijun if s==1 else f.tenkan<f.kijun
 if a>=2: c=c&( (f.close>f.top) if s==1 else (f.close<f.bot))
 if a>=3: c=c&((f.ca>f.cb) if s==1 else (f.ca<f.cb))
 return c

def sim(f,thr,a,d,start,end):
 ret=pd.Series(0.,index=f.index); tr=[]
 lc,sc=confirm(f,a,1),confirm(f,a,-1); i=60
 while i<len(f)-1:
  r=f.iloc[i]; dt=f.index[i]
  if dt<start or dt>=end or not np.isfinite(r.atr+r.lfs): i+=1; continue
  L=bool(r.swl and r.lfs>=thr and lc.iloc[i]); S=bool(r.sws and r.lfs>=thr and sc.iloc[i] and d=="both")
  if not(L or S): i+=1; continue
  side=1 if L else -1; en=i+1; entry=float(f.iloc[en].open)*(1+side*SLIP)
  stop=float(r.low-r.atr*.25) if side>0 else float(r.high+r.atr*.25); risk=abs(entry-stop)
  if risk<=0 or not np.isfinite(risk): i+=1; continue
  target=entry+side*RR*risk; last=min(en+HOLD-1,len(f)-1); ex,px,why=last,float(f.iloc[last].close),"TIME"
  for j in range(en,last+1):
   b=f.iloc[j]; sl=(b.low<=stop) if side>0 else (b.high>=stop); tp=(b.high>=target) if side>0 else (b.low<=target)
   if sl: ex,px,why=j,stop,"SL"; break
   if tp: ex,px,why=j,target,"TP"; break
  net=side*(px/entry-1)-2*(FEE+SLIP); ret.iloc[ex]+=net
  tr.append({"symbol":f.attrs.get("symbol",""),"net_return":net,"side":"LONG" if side>0 else "SHORT","exit":why})
  i=ex+1
 return ret,tr

def metrics(r,tr):
 r=np.nan_to_num(np.asarray(r,float)); eq=np.cumprod(1+r); dd=eq/np.maximum.accumulate(eq)-1; sd=np.std(r,ddof=1) if len(r)>1 else 0
 w=[t["net_return"] for t in tr if t["net_return"]>0]; l=[t["net_return"] for t in tr if t["net_return"]<=0]; gl=abs(sum(l))
 return {"win_rate":len(w)/len(tr) if tr else None,"profit_factor":sum(w)/gl if gl else (float("inf") if w else 0),"max_dd":float(dd.min()) if len(dd) else 0,"sharpe":float(np.mean(r)/sd*np.sqrt(365)) if sd else 0,"trades_count":len(tr),"net_return":float(eq[-1]-1) if len(eq) else 0}

def wf(idx):
 out=[]; ts=idx.min()+pd.DateOffset(months=TRAIN); last=idx.max()-pd.DateOffset(months=TEST-1)
 while ts<=last:
  te=ts+pd.DateOffset(months=TEST); out.append((ts-pd.DateOffset(months=TRAIN),ts,te)); ts+=pd.DateOffset(months=STEP)
 return out

def main():
 data=load(); fs={s:feat(x) for s,x in data.items()}
 for s,f in fs.items(): f.attrs["symbol"]=s
 configs=list(product(THRESH,ALIGN,DIR)); folds=wf(next(iter(fs.values())).index); foldout=[]; oos=[]; trades_oos=[]
 for n,(trstart,tstart,tend) in enumerate(folds):
  train_scores=[]
  for cfg in configs:
   rr=[]; tt=[]
   for sym,f in fs.items():
    r,t=sim(f,*cfg,trstart,tstart); rr.append(r); tt+=t
   p=pd.concat(rr,axis=1).mean(axis=1); p=p[(p.index>=trstart)& (p.index<tstart)]
   train_scores.append(metrics(p,tt)["sharpe"])
  chosen=int(np.argmax(train_scores)); cfg=configs[chosen]; rr=[]; tt=[]
  for sym,f in fs.items():
   r,t=sim(f,*cfg,tstart,tend); rr.append(r); tt+=t
  p=pd.concat(rr,axis=1).mean(axis=1); p=p[(p.index>=tstart)& (p.index<tend)]
  foldout.append({"fold":n,"train_start":trstart.date().isoformat(),"test_start":tstart.date().isoformat(),"test_end":tend.date().isoformat(),"selected_config":chosen,"oos":metrics(p,tt)})
  oos.append(p); trades_oos+=tt
 candidates=[]
 for cfg in configs:
  rr=[]
  for sym,f in fs.items(): r,_=sim(f,*cfg,START,END+pd.Timedelta(days=1)); rr.append(r)
 candidates.append(pd.concat(rr,axis=1).mean(axis=1).to_numpy())
 matrix=np.array(candidates); pbo_val=float(pbo(matrix.T,n_splits=8).pbo)
 selected=pd.concat(oos).reset_index(drop=True) if oos else pd.Series(dtype=float)
 dsr=float(deflated_sharpe_ratio(selected.to_numpy(),n_trials=len(configs))) if len(selected)>1 else 0
 z=float(norm.ppf(np.clip(dsr,1e-12,1-1e-12)))
 m=metrics(selected,trades_oos)
 summary={"status":"RESEARCH_GRADE_PROXY","symbol_count":len(data),"bars_per_symbol":730,"trials":30,"parameter_grid":[{"id":i,"lfs_threshold":c[0],"ichimoku_alignment":c[1],"direction_mode":c[2]} for i,c in enumerate(configs)],"walk_forward":{"train_months":TRAIN,"test_months":TEST,"step_months":STEP,"fold_count":len(folds),"fold_results":foldout},"pbo":pbo_val,"dsr_probability":dsr,"dsr_z":z,"selected_oos_metrics":m,"proxy_flags":{"LFS1":"PROXY: ATR/volume ranks, no orderbook","LFS2":"PROXY neutral: funding unavailable","LFS3":"PROXY neutral: long/short ratio unavailable","LFS4":"OHLCV volatility compression rank","LFS5":"PROXY neutral: OI unavailable"},"gates":{"pbo_lt_0_4":pbo_val<.4,"dsr_z_gt_1":z>1,"oos_win_rate_gt_55":m["win_rate"] is not None and m["win_rate"]>.55,"status":"NOT_VALIDATED"}}
 Path("results").mkdir(exist_ok=True); Path("results/backtest_summary.json").write_text(json.dumps(summary,indent=2,allow_nan=False))
 for i,c in enumerate(configs):
  Path(f"results/backtest_{i:02d}.json").write_text(json.dumps({"config_id":i,"parameters":{"lfs_threshold":c[0],"ichimoku_alignment":c[1],"direction_mode":c[2]},**metrics(matrix[i],[])},indent=2,allow_nan=False))
 print(json.dumps(summary,indent=2,allow_nan=False))

if __name__=="__main__": main()
