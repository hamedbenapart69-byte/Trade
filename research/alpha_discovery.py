#!/usr/bin/env python3
"""Point-in-time factor discovery; fails closed when PIT inputs are absent."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES=["vol_z20","funding_pct","oi_chg_24h","oi_chg_72h","pctB_50","btc_corr_break"]
ALIASES={
 "timestamp":["timestamp","datetime","date","time","ts"],
 "symbol":["symbol","ticker","instrument_id","pair"],
 "close":["close","c","close_price"],
 "volume":["volume","vol","base_volume"],
 "funding":["funding_rate","funding","fundingrate"],
 "oi":["open_interest","oi","openinterest","open_interest_value"],
 "high":["high","h"], "low":["low","l"],
}
def report_base(status,reason):
 return {"status":status,"reason":reason,"dataset":{"files":[],"rows":0,"symbols":0,"date_min":None,"date_max":None,"year_coverage":{}},
 "target":"forward_3d_return","features":FEATURES,"top5_rank_ic":[],"walk_forward":{"train_months":6,"test_months":2,"folds":0},
 "metrics":{"win_rate":None,"profit_factor":None,"pbo":None,"net_return":None,"trade_count":0},
 "costs":{"fee_pct":0.04,"slippage_pct":0.02,"round_trip_cost_pct":0.12}}
def read_data(root):
 paths=sorted([*root.rglob("*.parquet"),*root.rglob("*.csv")])
 if not paths: raise FileNotFoundError(f"No CSV/Parquet PIT dataset found under {root}")
 frames=[]
 for p in paths:
  df=pd.read_parquet(p) if p.suffix.lower()==".parquet" else pd.read_csv(p)
  df.columns=[str(c).lower().strip() for c in df.columns]
  for canonical,aliases in ALIASES.items():
   if canonical not in df:
    for a in aliases:
     if a in df: df[canonical]=df[a]; break
  required=["timestamp","symbol","close","volume"]
  missing=[c for c in required if c not in df]
  if missing: raise ValueError(f"{p}: missing required columns {missing}")
  df["timestamp"]=pd.to_datetime(df["timestamp"],utc=True,errors="coerce")
  df["symbol"]=df.symbol.astype(str).str.upper()
  df=df.dropna(subset=["timestamp","symbol","close"]).copy()
  df["source_file"]=str(p)
  frames.append(df)
 data=pd.concat(frames,ignore_index=True)
 data=data.sort_values(["symbol","timestamp","source_file"]).drop_duplicates(["symbol","timestamp"],keep="last")
 return data,paths
def build_features(data):
 out=[]
 for symbol,g in data.groupby("symbol",sort=False):
  g=g.sort_values("timestamp").copy()
  g["forward_3d_return"]=g.close.shift(-3)/g.close-1
  vol=g.volume.astype(float)
  g["vol_z20"]=(vol-vol.rolling(20,min_periods=20).mean())/vol.rolling(20,min_periods=20).std(ddof=0)
  if "funding" in g:
   g["funding_pct"]=g.funding.astype(float).rolling(90,min_periods=10).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1],raw=False)
  else:g["funding_pct"]=np.nan
  oi=pd.to_numeric(g.get("oi",np.nan),errors="coerce")
  g["oi_chg_24h"]=oi.pct_change(1)
  g["oi_chg_72h"]=oi.pct_change(3)
  mid=g.close.rolling(50,min_periods=50).mean()
  sd=g.close.rolling(50,min_periods=50).std(ddof=0)
  upper,lower=mid+2*sd,mid-2*sd
  g["pctB_50"]=(g.close-lower)/(upper-lower).replace(0,np.nan)
  out.append(g)
 df=pd.concat(out).sort_values(["timestamp","symbol"])
 btc=df[df.symbol.str.contains("BTC",regex=False)].groupby("timestamp").close.mean().rename("btc_close")
 df=df.join(btc,on="timestamp")
 df["asset_ret"]=df.groupby("symbol").close.pct_change()
 df["btc_ret"]=df.btc_close.pct_change()
 corr=[]
 for s,g in df.groupby("symbol",sort=False):
  c=g.asset_ret.rolling(30,min_periods=20).corr(g.btc_ret)
  g=g.copy(); g["rolling_btc_corr"]=c; g["btc_corr_break"]=c-c.shift(10)
  corr.append(g)
 return pd.concat(corr).sort_values(["timestamp","symbol"])
def ic_table(df):
 rows=[]
 for f in FEATURES:
  z=df[[f,"forward_3d_return"]].dropna()
  if len(z)<30: continue
  ic=z[f].corr(z.forward_3d_return)
  ric=z[f].rank().corr(z.forward_3d_return.rank())
  rows.append({"feature":f,"ic":float(ic) if pd.notna(ic) else None,"rank_ic":float(ric) if pd.notna(ric) else None,"n":len(z)})
 return sorted(rows,key=lambda x:abs(x["rank_ic"] or 0),reverse=True)
def metrics(returns):
 r=pd.Series(returns).dropna()
 if r.empty:return {"win_rate":None,"profit_factor":None,"net_return":None,"trade_count":0}
 wins=r[r>0]; losses=r[r<0]
 pf=float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else (None if not len(wins) else float("inf"))
 return {"win_rate":float((r>0).mean()),"profit_factor":pf,"net_return":float((1+r).prod()-1),"trade_count":len(r)}
def pbo_cscv(df,prob,netret):
 """CSCV rank-based PBO over 8 chronological blocks; unavailable for short samples."""
 n=len(df)
 if n<800:return None
 blocks=np.array_split(np.arange(n),8)
 outcomes=[]
 # Candidate strategies are probability thresholds; all evaluated on the same held-out rows.
 thresholds=[.50,.55,.60,.65]
 retmat=np.column_stack([netret*(prob>=t) for t in thresholds])
 for combo in range(70): # 8 choose 4
  is_idx=np.concatenate([blocks[i] for i in range(8) if (combo>>i)&1]) if False else None
 # Exhaustive balanced combinations (70) via combinations
 from itertools import combinations
 for train_blocks in combinations(range(8),4):
  test_blocks=[i for i in range(8) if i not in train_blocks]
  is_idx=np.concatenate([blocks[i] for i in train_blocks]); oos_idx=np.concatenate([blocks[i] for i in test_blocks])
  is_sh=[]; oos_sh=[]
  for j in range(retmat.shape[1]):
   a=retmat[is_idx,j]; b=retmat[oos_idx,j]
   is_sh.append(float(np.mean(a)/(np.std(a,ddof=1)+1e-12)))
   oos_sh.append(float(np.mean(b)/(np.std(b,ddof=1)+1e-12)))
  best=int(np.argmax(is_sh)); rank=(np.sum(np.array(oos_sh)<oos_sh[best])+0.5*np.sum(np.array(oos_sh)==oos_sh[best]))/len(oos_sh)
  outcomes.append(rank)
 return float(np.mean(np.array(outcomes)<0.5))
def run(data):
 data=build_features(data)
 ic=ic_table(data)
 # Time-aligned, chronological monthly walk-forward windows; 6m train, 2m test.
 data=data.replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES+["forward_3d_return"])
 months=sorted(data.timestamp.dt.to_period("M").unique())
 from lightgbm import LGBMClassifier
 folds=[]; allret=[]; allprob=[]; allraw=[]
 for i in range(6,len(months)-1,2):
  trmonths=months[i-6:i]; testmonths=months[i:i+2]
  train=data[data.timestamp.dt.to_period("M").isin(trmonths)]
  test=data[data.timestamp.dt.to_period("M").isin(testmonths)]
  if len(train)<500 or len(test)<100:continue
  y=(train.forward_3d_return>0).astype(int)
  if y.nunique()<2:continue
  model=LGBMClassifier(n_estimators=180,max_depth=4,num_leaves=15,learning_rate=.04,verbosity=-1,random_state=42)
  model.fit(train[FEATURES],y)
  prob=model.predict_proba(test[FEATURES])[:,1]
  # Only take positive-class predictions; fee/slippage applied as round-trip cost.
  gross=test.forward_3d_return.to_numpy()
  cost=.0012
  net=gross-cost
  strat=np.where(prob>=.5,net,0.0)
  folds.append({"train_start":str(trmonths[0]),"train_end":str(trmonths[-1]),"test_start":str(testmonths[0]),"test_end":str(testmonths[-1]),"train_n":len(train),"test_n":len(test),"trades":int((prob>=.5).sum())})
  allret.extend(strat.tolist());allprob.extend(prob.tolist());allraw.extend(net.tolist())
 if not folds: raise ValueError("No valid walk-forward folds; need adequate PIT history/coverage")
 # PBO candidate-threshold CSCV on combined OOS predictions; neutral rows remain zero.
 pbo=pbo_cscv(pd.DataFrame(index=range(len(allprob))),np.array(allprob),np.array(allraw))
 m=metrics(allret)
 m["pbo"]=pbo
 m["folds"]=len(folds)
 m["execution_cost_pct_per_round_trip"]=0.12
 return {"status":"COMPUTED","reason":None,"dataset":{"files":[],"rows":len(data),"symbols":int(data.symbol.nunique()),"date_min":str(data.timestamp.min()),"date_max":str(data.timestamp.max()),"year_coverage":{str(y):int((data.timestamp.dt.year==y).sum()) for y in sorted(data.timestamp.dt.year.unique())}},
 "target":"forward_3d_return","features":FEATURES,"top5_rank_ic":ic[:5],"walk_forward":{"train_months":6,"test_months":2,"folds":len(folds),"details":folds},"metrics":m,"costs":{"fee_pct":.04,"slippage_pct":.02,"round_trip_cost_pct":.12}}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--data",default="data/pit")
 ap.add_argument("--output",default="out/report.json")
 args=ap.parse_args()
 out=report_base("UNAVAILABLE","")
 try:
  df,files=read_data(Path(args.data))
  out=run(df);out["dataset"]["files"]=[str(p) for p in files]
 except Exception as e:
  out["status"]="UNAVAILABLE";out["reason"]=str(e)
  out["dataset"]["files"]=[]
 Path(args.output).parent.mkdir(parents=True,exist_ok=True)
 Path(args.output).write_text(json.dumps(out,indent=2,allow_nan=False,default=str)+"\n")
 print(json.dumps(out,indent=2,allow_nan=False,default=str))
 if out["status"]!="COMPUTED": raise SystemExit(2)
if __name__=="__main__":main()
