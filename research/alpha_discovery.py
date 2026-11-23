#!/usr/bin/env python3
"""Point-in-time alpha discovery on verified daily PIT data; no synthetic fallback."""
from __future__ import annotations
import argparse, json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = ["vol_z20","funding_pct","oi_chg_24h","oi_chg_72h","pctB_50","btc_corr_break"]
ALIASES = {
    "timestamp":["timestamp","datetime","date","time","ts"],
    "symbol":["symbol","ticker","instrument_id","pair"],
    "close":["close","c","close_price"], "volume":["volume","vol","base_volume"],
    "funding":["funding_rate","funding","fundingrate"],
    "oi":["open_interest","oi","openinterest","open_interest_value"],
    "high":["high","h"], "low":["low","l"]
}
ROUND_TRIP_COST = 0.0012

def read_data(root: Path):
    paths = sorted([*root.rglob("*.parquet"), *root.rglob("*.csv")])
    paths = [p for p in paths if not p.name.endswith(".manifest.csv")]
    if not paths:
        raise FileNotFoundError(f"No CSV/Parquet PIT data found under {root}")
    frames = []
    for path in paths:
        frame = pd.read_parquet(path) if path.suffix.lower()==".parquet" else pd.read_csv(path)
        frame.columns = [str(c).lower().strip() for c in frame.columns]
        for canonical, aliases in ALIASES.items():
            if canonical not in frame.columns:
                match = next((name for name in aliases if name in frame.columns), None)
                if match: frame[canonical] = frame[match]
        required = ["timestamp","symbol","close","volume"]
        missing = [c for c in required if c not in frame.columns]
        if missing: raise ValueError(f"{path}: missing required columns {missing}")
        frame["timestamp"] = pd.to_datetime(frame.timestamp, utc=True, errors="coerce")
        frame["symbol"] = frame.symbol.astype(str).str.upper()
        for c in ["close","volume","funding","oi","high","low"]:
            if c in frame: frame[c] = pd.to_numeric(frame[c], errors="coerce")
        frame = frame.dropna(subset=["timestamp","symbol","close"]).copy()
        frame["_source_file"] = str(path)
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data = data.sort_values(["symbol","timestamp","_source_file"])
    data = data.drop_duplicates(["symbol","timestamp"], keep="last")
    return data, paths

def _future_by_calendar_days(group: pd.DataFrame, column: str, days: int):
    future = group[["timestamp",column]].copy()
    future["timestamp"] = future.timestamp - pd.Timedelta(days=days)
    return group[["timestamp"]].merge(future, on="timestamp", how="left")[column].to_numpy()

def build_features(data: pd.DataFrame):
    parts=[]
    has_funding = "funding" in data.columns and data.funding.notna().any()
    has_oi = "oi" in data.columns and data.oi.notna().any()
    for symbol, group in data.groupby("symbol", sort=False):
        g=group.sort_values("timestamp").copy()
        future_close=_future_by_calendar_days(g,"close",3)
        g["forward_3d_return"]=future_close/g.close.to_numpy()-1
        vol=g.volume.astype(float)
        g["vol_z20"]=(vol-vol.rolling(20,min_periods=20).mean())/vol.rolling(20,min_periods=20).std(ddof=0)
        if has_funding and "funding" in g:
            g["funding_pct"]=g.funding.rolling(90,min_periods=20).apply(
                lambda x: float(pd.Series(x).rank(pct=True).iloc[-1]), raw=False)
        else: g["funding_pct"]=np.nan
        if has_oi and "oi" in g:
            oi_24=_future_by_calendar_days(g,"oi",1)
            oi_72=_future_by_calendar_days(g,"oi",3)
            g["oi_chg_24h"]=g.oi.to_numpy()/oi_24-1
            g["oi_chg_72h"]=g.oi.to_numpy()/oi_72-1
        else:
            g["oi_chg_24h"]=np.nan; g["oi_chg_72h"]=np.nan
        mid=g.close.rolling(50,min_periods=50).mean()
        sd=g.close.rolling(50,min_periods=50).std(ddof=0)
        upper,lower=mid+2*sd,mid-2*sd
        g["pctB_50"]=(g.close-lower)/(upper-lower).replace(0,np.nan)
        parts.append(g)
    df=pd.concat(parts,ignore_index=True).sort_values(["timestamp","symbol"])
    btc=df[df.symbol=="BTCUSDT"].groupby("timestamp").close.mean().rename("btc_close")
    if btc.empty:
        # Binance Vision USD-M symbols are commonly BTCUSDT; no substitute is inferred.
        df["btc_corr_break"]=np.nan
    else:
        df=df.join(btc,on="timestamp")
        df["asset_ret"]=df.groupby("symbol").close.pct_change()
        df["btc_ret"]=df.btc_close.pct_change()
        corr_parts=[]
        for _,g in df.groupby("symbol",sort=False):
            g=g.copy()
            corr=g.asset_ret.rolling(30,min_periods=20).corr(g.btc_ret)
            g["btc_corr_break"]=corr-corr.shift(10)
            corr_parts.append(g)
        df=pd.concat(corr_parts,ignore_index=True)
    return df, has_funding, has_oi

def ic_table(df, available):
    rows=[]
    for feature in available:
        sample=df[[feature,"forward_3d_return"]].replace([np.inf,-np.inf],np.nan).dropna()
        if len(sample)<30: continue
        ic=sample[feature].corr(sample.forward_3d_return)
        rank_ic=sample[feature].rank().corr(sample.forward_3d_return.rank())
        rows.append({"feature":feature,"ic":float(ic) if pd.notna(ic) else None,
                     "rank_ic":float(rank_ic) if pd.notna(rank_ic) else None,"n":int(len(sample))})
    return sorted(rows,key=lambda row:abs(row["rank_ic"] or 0),reverse=True)

def pbo_cscv(oos: pd.DataFrame):
    """CSCV-style PBO proxy over four probability cutoffs and eight chronological blocks."""
    if oos.timestamp.nunique()<80: return None, {"status":"UNAVAILABLE","reason":"fewer than 80 OOS dates"}
    daily=[]
    for threshold in (.50,.55,.60,.65):
        selected=oos[oos.probability>=threshold]
        series=selected.groupby("timestamp").net_return.mean()
        daily.append(series.rename(str(threshold)))
    matrix=pd.concat(daily,axis=1).fillna(0.0).to_numpy().T
    if matrix.shape[1]<80: return None, {"status":"UNAVAILABLE","reason":"insufficient OOS daily returns"}
    blocks=np.array_split(np.arange(matrix.shape[1]),8)
    logits=[]
    for is_blocks in combinations(range(8),4):
        oos_blocks=[i for i in range(8) if i not in is_blocks]
        is_idx=np.concatenate([blocks[i] for i in is_blocks])
        oos_idx=np.concatenate([blocks[i] for i in oos_blocks])
        is_sh=np.array([np.mean(row[is_idx])/(np.std(row[is_idx],ddof=1)+1e-12) for row in matrix])
        oos_sh=np.array([np.mean(row[oos_idx])/(np.std(row[oos_idx],ddof=1)+1e-12) for row in matrix])
        chosen=int(np.argmax(is_sh))
        rank=(np.sum(oos_sh<oos_sh[chosen])+.5*np.sum(oos_sh==oos_sh[chosen]))/len(oos_sh)
        logits.append(np.log(np.clip(rank,1e-9,1-1e-9)/(1-np.clip(rank,1e-9,1-1e-9))))
    return float(np.mean(np.asarray(logits)<0)), {
        "status":"PBO_PROXY","method":"8 chronological blocks, 4/4 CSCV, four probability thresholds",
        "splits":len(logits),"candidate_strategies":4,
        "limitation":"Proxy: one LightGBM walk-forward prediction stream; not a full multi-model strategy-selection PBO."
    }

def trade_metrics(oos):
    if oos.empty:
        return {"win_rate":None,"profit_factor":None,"profit_factor_status":"NO_TRADES",
                "trade_count":0,"net_return":None}
    returns=oos.net_return.to_numpy(dtype=float)
    wins=returns[returns>0]; losses=-returns[returns<0]
    pf=float(wins.sum()/losses.sum()) if len(losses) and losses.sum()>0 else None
    return {"win_rate":float(np.mean(returns>0)),"profit_factor":pf,
            "profit_factor_status":"CALCULATED" if len(losses) else "NO_LOSSES_OR_NO_WINNINGS",
            "trade_count":int(len(returns)),"net_return":float(np.prod(1+returns)-1),
            "mean_trade_return":float(np.mean(returns))}

def run(data):
    df,has_funding,has_oi=build_features(data)
    usable=[]
    for feature in FEATURES:
        if feature in df and df[feature].notna().sum()>=100:
            usable.append(feature)
    missing=[feature for feature in FEATURES if feature not in usable]
    if len(usable)<2:
        raise ValueError(f"Insufficient real feature coverage: usable={usable}; unavailable={missing}")
    ic=ic_table(df,usable)
    model_data=df.replace([np.inf,-np.inf],np.nan).dropna(subset=usable+["forward_3d_return"])
    months=sorted(model_data.timestamp.dt.to_period("M").unique())
    from lightgbm import LGBMClassifier
    folds=[]; oos_parts=[]
    for i in range(6,len(months)-1,2):
        train_months=months[i-6:i]; test_months=months[i:i+2]
        train=model_data[model_data.timestamp.dt.to_period("M").isin(train_months)]
        test=model_data[model_data.timestamp.dt.to_period("M").isin(test_months)]
        if len(train)<500 or len(test)<100: continue
        y=(train.forward_3d_return>0).astype(int)
        if y.nunique()<2: continue
        model=LGBMClassifier(n_estimators=180,max_depth=4,num_leaves=15,
            learning_rate=.04,verbosity=-1,random_state=42,n_jobs=-1)
        model.fit(train[usable],y)
        probabilities=model.predict_proba(test[usable])[:,1]
        selected=probabilities>=.50
        executed=test.loc[selected,["timestamp","symbol","forward_3d_return"]].copy()
        executed["probability"]=probabilities[selected]
        executed["gross_return"]=executed.forward_3d_return
        executed["net_return"]=executed.gross_return-ROUND_TRIP_COST
        oos_parts.append(executed)
        folds.append({"train_start":str(train_months[0]),"train_end":str(train_months[-1]),
            "test_start":str(test_months[0]),"test_end":str(test_months[-1]),
            "train_rows":int(len(train)),"test_rows":int(len(test)),
            "selected_trades":int(selected.sum()),"features":usable})
    if not folds: raise ValueError("No valid 6m/2m walk-forward folds in available PIT period")
    oos=pd.concat(oos_parts,ignore_index=True) if oos_parts else pd.DataFrame(
        columns=["timestamp","symbol","probability","net_return"])
    metrics=trade_metrics(oos)
    pbo,pbo_details=pbo_cscv(oos) if not oos.empty else (None,{"status":"UNAVAILABLE","reason":"no selected OOS trades"})
    metrics["pbo"]=pbo; metrics["pbo_details"]=pbo_details
    metrics["walk_forward_folds"]=len(folds)
    metrics["round_trip_cost_pct"]=0.12
    year_coverage={str(int(year)):int((model_data.timestamp.dt.year==year).sum())
                   for year in sorted(model_data.timestamp.dt.year.unique())}
    full=len(usable)==len(FEATURES)
    return {
        "status":"COMPUTED" if full else "PARTIAL_DATA",
        "reason":None if full else "Funding and/or open-interest observations are absent; reported model uses only verified available features.",
        "dataset":{"rows_after_feature_validation":int(len(model_data)),
            "raw_rows":int(len(data)),"symbols":int(data.symbol.nunique()),
            "date_min":str(data.timestamp.min()),"date_max":str(data.timestamp.max()),
            "year_coverage":year_coverage,"frequency":"daily UTC; target uses exact calendar t+3 close",
            "source_provenance":data.get("_source_file",pd.Series(dtype=str)).dropna().unique().tolist()},
        "target":"close(t+3 calendar days) / close(t) - 1",
        "features":{"requested":FEATURES,"used":usable,"unavailable":missing,
            "coverage":{"funding_available":bool(has_funding),"open_interest_available":bool(has_oi)}},
        "top5_rank_ic":ic[:5],
        "walk_forward":{"train_months":6,"test_months":2,"folds":len(folds),"details":folds},
        "lightgbm_metrics":metrics,
        "costs":{"fee_pct_per_side":0.04,"slippage_pct_per_side":0.02,
            "round_trip_cost_pct":0.12,"cost_model":"deducted once from each 3-day trade return"},
        "research_limitations":["PIT data coverage is limited to dates present in source artifacts.",
            "PBO is explicitly a proxy based on four probability thresholds.",
            "Funding/OI features are not imputed or synthesized."]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data",default="data/pit")
    ap.add_argument("--output",default="out/report.json")
    args=ap.parse_args()
    result={"status":"UNAVAILABLE","reason":None}
    try:
        data,paths=read_data(Path(args.data))
        result=run(data)
        result["dataset"]["files"]=[str(p) for p in paths]
    except Exception as exc:
        result["status"]="UNAVAILABLE"; result["reason"]=str(exc)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False,default=str)+"\n")
    print(json.dumps(result,indent=2,allow_nan=False,default=str))
    if result["status"]=="UNAVAILABLE": raise SystemExit(2)
if __name__=="__main__": main()
