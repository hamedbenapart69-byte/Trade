#!/usr/bin/env python3
"""Point-in-time alpha discovery on verified daily PIT data; no synthetic fallback."""
from __future__ import annotations
import argparse, json
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES = [
    "vol_z20", "funding_pct", "oi_chg_24h", "oi_chg_72h",
    "pctB_50", "btc_corr_break", "ret_1d", "ret_7d",
    "range_pos_20", "ema_gap_20_50", "volume_ratio_20",
    "btc_relative_mom_7d"
]
FEATURE_HYPOTHESES = {
    "vol_z20": {"hypothesis":"Unusual volume may proxy participation shocks.","falsification":"Mean daily cross-sectional Rank IC is non-positive or unstable OOS."},
    "funding_pct": {"hypothesis":"Extreme funding percentile may proxy crowded derivatives positioning.","falsification":"No stable OOS contribution when real funding observations are present."},
    "oi_chg_24h": {"hypothesis":"Daily open-interest expansion may identify new positioning.","falsification":"OOS contribution is non-positive after costs when real OI is present."},
    "oi_chg_72h": {"hypothesis":"Three-day open-interest expansion may separate persistent positioning from noise.","falsification":"OOS contribution is non-positive after costs when real OI is present."},
    "pctB_50": {"hypothesis":"Position within a 50-day Bollinger envelope may distinguish continuation from reversion.","falsification":"Rank IC sign is unstable across chronological folds."},
    "btc_corr_break": {"hypothesis":"A change in rolling BTC correlation may identify idiosyncratic decoupling.","falsification":"No stable cross-sectional association across chronological folds."},
    "ret_1d": {"hypothesis":"One-day return may capture short-horizon cross-sectional momentum.","falsification":"Mean daily Rank IC is non-positive or reverses across folds."},
    "ret_7d": {"hypothesis":"Seven-day return may capture intermediate-horizon momentum.","falsification":"Mean daily Rank IC is non-positive or reverses across folds."},
    "range_pos_20": {"hypothesis":"Close location within the prior 20-day high-low range may capture breakout persistence.","falsification":"Mean daily Rank IC is non-positive or unstable OOS."},
    "ema_gap_20_50": {"hypothesis":"The 20/50 EMA spread may proxy medium-term trend state.","falsification":"Mean daily Rank IC is non-positive or unstable OOS."},
    "volume_ratio_20": {"hypothesis":"Current volume relative to its 20-day mean may capture participation expansion.","falsification":"Mean daily Rank IC is non-positive after costs or unstable OOS."},
    "btc_relative_mom_7d": {"hypothesis":"Seven-day asset return relative to BTC may capture cross-sectional relative strength.","falsification":"Mean daily Rank IC is non-positive or unstable OOS."}
}
ALIASES = {
    "timestamp":["timestamp","datetime","date","time","ts"],
    "symbol":["symbol","ticker","instrument_id","pair"],
    "close":["close","c","close_price"], "volume":["volume","vol","base_volume"],
    "funding":["funding_rate","funding","fundingrate"],
    "oi":["open_interest","oi","openinterest","open_interest_value"],
    "high":["high","h"], "low":["low","l"]
}
ROUND_TRIP_COST = 0.0012

def apply_pit_membership(data: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    """Mark daily rows using only the independently generated PIT membership table."""
    required = {"date", "symbol"}
    missing = sorted(required - set(membership.columns))
    if missing:
        raise ValueError(f"PIT membership missing columns: {missing}")
    members = membership[["date", "symbol"]].copy()
    members["date"] = pd.to_datetime(members["date"], utc=True, errors="coerce").dt.floor("D")
    members["symbol"] = members["symbol"].astype(str).str.upper().str.strip()
    if members[["date", "symbol"]].isna().any().any():
        raise ValueError("PIT membership contains invalid date/symbol keys")
    if members.duplicated(["date", "symbol"]).any():
        raise ValueError("PIT membership contains duplicate date/symbol keys")
    keys = members.assign(_pit_member=True)
    result = data.copy()
    result["_pit_date"] = result["timestamp"].dt.floor("D")
    result = result.merge(keys, left_on=["_pit_date", "symbol"],
                          right_on=["date", "symbol"], how="left", validate="many_to_one")
    result["_pit_member"] = result["_pit_member"].fillna(False).astype(bool)
    return result.drop(columns=["_pit_date", "date"])

def read_data(root: Path):
    paths = sorted([*root.rglob("*.parquet"), *root.rglob("*.csv")])
    paths = [p for p in paths if p.name.startswith("ohlcv_") or "ohlcv" in p.stem.lower()]
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
    membership_path = root / "universe_membership.csv"
    manifest_path = root / "universe_manifest.json"
    if not membership_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("PIT membership CSV and universe manifest are required; refusing unfiltered universe")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS" or manifest.get("dataset") != "vtm_pit_usdm_usdt_perpetual_universe_2023":
        raise ValueError("PIT universe manifest identity/status is not PASS")
    membership = pd.read_csv(membership_path)
    data = apply_pit_membership(data, membership)
    return data, paths

def _future_by_calendar_days(group: pd.DataFrame, column: str, days: int):
    future = group[["timestamp",column]].copy()
    future["timestamp"] = future.timestamp - pd.Timedelta(days=days)
    return group[["timestamp"]].merge(future, on="timestamp", how="left")[column].to_numpy()

def _past_by_calendar_days(group: pd.DataFrame, column: str, days: int):
    past = group[["timestamp",column]].copy()
    past["timestamp"] = past.timestamp + pd.Timedelta(days=days)
    return group[["timestamp"]].merge(past, on="timestamp", how="left")[column].to_numpy()

def build_features(data: pd.DataFrame):
    parts=[]
    has_funding = "funding" in data.columns and data.funding.notna().any()
    has_oi = "oi" in data.columns and data.oi.notna().any()
    for symbol, group in data.groupby("symbol", sort=False):
        g=group.sort_values("timestamp").copy()
        future_close=_future_by_calendar_days(g,"close",3)
        g["forward_3d_return"]=future_close/g.close.to_numpy()-1
        close=g.close.astype(float)
        vol=g.volume.astype(float)

        # Price/volume features use current and historical bars only.
        g["ret_1d"]=close.pct_change(1)
        g["ret_7d"]=close.pct_change(7)
        g["vol_z20"]=(vol-vol.rolling(20,min_periods=20).mean())/vol.rolling(20,min_periods=20).std(ddof=0)
        g["volume_ratio_20"]=vol/vol.rolling(20,min_periods=20).mean().replace(0,np.nan)

        ema20=close.ewm(span=20,adjust=False,min_periods=20).mean()
        ema50=close.ewm(span=50,adjust=False,min_periods=50).mean()
        g["ema_gap_20_50"]=ema20/ema50.replace(0,np.nan)-1

        if "high" in g.columns and "low" in g.columns:
            rolling_high=g.high.astype(float).rolling(20,min_periods=20).max()
            rolling_low=g.low.astype(float).rolling(20,min_periods=20).min()
            width=(rolling_high-rolling_low).replace(0,np.nan)
            g["range_pos_20"]=(close-rolling_low)/width
        else:
            g["range_pos_20"]=np.nan

        if has_funding and "funding" in g:
            g["funding_pct"]=g.funding.rolling(90,min_periods=20).apply(
                lambda x: float(pd.Series(x).rank(pct=True).iloc[-1]), raw=False)
        else:
            g["funding_pct"]=np.nan

        if has_oi and "oi" in g:
            oi_24=_past_by_calendar_days(g,"oi",1)
            oi_72=_past_by_calendar_days(g,"oi",3)
            g["oi_chg_24h"]=g.oi.to_numpy()/oi_24-1
            g["oi_chg_72h"]=g.oi.to_numpy()/oi_72-1
        else:
            g["oi_chg_24h"]=np.nan
            g["oi_chg_72h"]=np.nan

        mid=close.rolling(50,min_periods=50).mean()
        sd=close.rolling(50,min_periods=50).std(ddof=0)
        upper,lower=mid+2*sd,mid-2*sd
        g["pctB_50"]=(close-lower)/(upper-lower).replace(0,np.nan)
        parts.append(g)

    df=pd.concat(parts,ignore_index=True).sort_values(["timestamp","symbol"])
    btc_close=df[df.symbol=="BTCUSDT"].groupby("timestamp").close.mean().rename("btc_close")
    if btc_close.empty:
        df["btc_corr_break"]=np.nan
        df["btc_relative_mom_7d"]=np.nan
    else:
        btc_ret=btc_close.pct_change().rename("btc_ret")
        btc_ret_7d=btc_close.pct_change(7).rename("btc_ret_7d")
        df=df.join(btc_close,on="timestamp")
        df=df.join(btc_ret,on="timestamp")
        df=df.join(btc_ret_7d,on="timestamp")
        df["asset_ret"]=df.groupby("symbol").close.pct_change()
        df["asset_ret_7d"]=df.groupby("symbol").close.pct_change(7)
        df["btc_relative_mom_7d"]=df.asset_ret_7d-df.btc_ret_7d
        corr_parts=[]
        for _,g in df.groupby("symbol",sort=False):
            g=g.copy()
            corr=g.asset_ret.rolling(30,min_periods=20).corr(g.btc_ret)
            g["btc_corr_break"]=corr-corr.shift(10)
            corr_parts.append(g)
        df=pd.concat(corr_parts,ignore_index=True)
    return df, has_funding, has_oi

def ic_table(df, available):
    """Mean daily cross-sectional IC/Rank IC on PIT-member observations."""
    rows=[]
    for feature in available:
        sample=df[["timestamp",feature,"forward_3d_return"]].replace(
            [np.inf,-np.inf],np.nan).dropna()
        if len(sample)<30: continue
        daily=[]
        for _, cross_section in sample.groupby("timestamp",sort=True):
            if len(cross_section)<10: continue
            ic=cross_section[feature].corr(cross_section.forward_3d_return)
            rank_ic=cross_section[feature].rank().corr(
                cross_section.forward_3d_return.rank())
            if pd.notna(ic) and pd.notna(rank_ic):
                daily.append((float(ic),float(rank_ic)))
        if len(daily)<30: continue
        ic_values=np.asarray([x[0] for x in daily],dtype=float)
        rank_values=np.asarray([x[1] for x in daily],dtype=float)
        rows.append({
            "feature":feature,
            "ic":float(np.mean(ic_values)),
            "rank_ic":float(np.mean(rank_values)),
            "rank_ic_std":float(np.std(rank_values,ddof=1)),
            "n":int(len(sample)),
            "n_dates":int(len(daily))
        })
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
            "trade_count":int(len(returns)),"mean_trade_return":float(np.mean(returns)),
            "metric_scope":"OOS signal-level returns; overlapping 3-day signals are not a portfolio equity curve"}

def deduplicate_oos_predictions(oos: pd.DataFrame) -> pd.DataFrame:
    """For overlapping test windows, keep the latest fold forecast per symbol/date."""
    if oos.empty:
        return oos.copy()
    required={"timestamp","symbol","fold_index"}
    if not required.issubset(oos.columns):
        raise ValueError("OOS deduplication requires timestamp, symbol and fold_index")
    return oos.sort_values(["timestamp","symbol","fold_index"]).drop_duplicates(
        ["timestamp","symbol"],keep="last").reset_index(drop=True)


def purged_training_window(data: pd.DataFrame, train_start: pd.Timestamp,
                           test_start: pd.Timestamp, purge_days: int = 3) -> pd.DataFrame:
    """Exclude training labels whose t+3 outcome could touch the test period."""
    cutoff = test_start - pd.Timedelta(days=purge_days)
    return data[(data.timestamp >= train_start) & (data.timestamp < cutoff)].copy()

def run(data):
    df,has_funding,has_oi=build_features(data)
    if "_pit_member" not in df.columns:
        raise ValueError("PIT membership filter missing; refusing non-PIT sample")
    pit_membership_rows = int(df["_pit_member"].sum())
    pit_membership_symbols = int(df.loc[df["_pit_member"], "symbol"].nunique())
    pit_membership_dates = int(df.loc[df["_pit_member"], "timestamp"].dt.floor("D").nunique())
    # Features are computed on all available historical bars; scored/modelled rows are PIT members only.
    df = df[df["_pit_member"]].copy()
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
    folds=[]; oos_parts=[]; fold_diagnostics=[]
    for i in range(6,len(months)-1,1):
        train_months=months[i-6:i]; test_months=months[i:i+2]
        train_start=train_months[0].start_time.tz_localize("UTC")
        test_start=months[i].start_time.tz_localize("UTC")
        test_end=(months[i+2].start_time.tz_localize("UTC") if i+2<len(months)
                  else (months[-1]+1).start_time.tz_localize("UTC"))
        train=purged_training_window(model_data, train_start, test_start, purge_days=3)
        test=model_data[(model_data.timestamp>=test_start)&(model_data.timestamp<test_end)]
        if len(train)<500 or len(test)<100:
            fold_diagnostics.append({"fold":i,"train_rows":int(len(train)),"test_rows":int(len(test)),"skip":"sample_below_minimum"})
            continue
        y=(train.forward_3d_return>0).astype(int)
        if y.nunique()<2:
            fold_diagnostics.append({"fold":i,"train_rows":int(len(train)),"test_rows":int(len(test)),"skip":"single_class_training_target"})
            continue
        model=LGBMClassifier(n_estimators=180,max_depth=4,num_leaves=15,
            learning_rate=.04,verbosity=-1,random_state=42,n_jobs=-1)
        model.fit(train[usable],y)
        probabilities=model.predict_proba(test[usable])[:,1]
        selected=probabilities>=.50
        executed=test.loc[selected,["timestamp","symbol","forward_3d_return"]].copy()
        executed["probability"]=probabilities[selected]
        executed["gross_return"]=executed.forward_3d_return
        executed["net_return"]=executed.gross_return-ROUND_TRIP_COST
        executed["fold_index"]=i
        oos_parts.append(executed)
        folds.append({"train_start":str(train_months[0]),"train_end":str(train_months[-1]),
            "test_start":str(test_months[0]),"test_end":str(test_months[-1]),
            "train_rows":int(len(train)),"test_rows":int(len(test)),
            "purge_days":3,"selected_trades":int(selected.sum()),"features":usable})
    if not folds:
        raise ValueError("No valid 6m/2m walk-forward folds; diagnostics=" + json.dumps({
            "available_months":[str(m) for m in months],
            "model_rows":int(len(model_data)),
            "feature_non_null":{f:int(model_data[f].notna().sum()) for f in usable},
            "fold_attempts":fold_diagnostics
        }))
    oos=pd.concat(oos_parts,ignore_index=True) if oos_parts else pd.DataFrame(
        columns=["timestamp","symbol","probability","net_return","fold_index"])
    oos=deduplicate_oos_predictions(oos)
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
            "raw_rows":int(len(data)),"pit_membership_rows":pit_membership_rows,
            "pit_membership_symbols":pit_membership_symbols,"pit_membership_dates":pit_membership_dates,
            "pit_membership_filter":"APPLIED: exact date/symbol join to universe_membership.csv",
            "symbols":int(data.symbol.nunique()),
            "date_min":str(data.timestamp.min()),"date_max":str(data.timestamp.max()),
            "year_coverage":year_coverage,"frequency":"daily UTC; target uses exact calendar t+3 close",
            "source_provenance":data.get("_source_file",pd.Series(dtype=str)).dropna().unique().tolist()},
        "target":"close(t+3 calendar days) / close(t) - 1",
        "features":{"requested":FEATURES,"used":usable,"unavailable":missing,
            "coverage":{"funding_available":bool(has_funding),"open_interest_available":bool(has_oi)}},
        "top5_rank_ic":ic[:5],
        "feature_hypotheses":{feature:FEATURE_HYPOTHESES[feature] for feature in usable},
        "rank_ic_scope":"Mean daily cross-sectional Spearman IC on PIT-member rows; dates require at least 10 symbols. Full 2023 descriptive statistic, not OOS-only and not used to select fitted model features.",
        "execution_assumption":{
            "status":"PROXY_NOT_EXECUTABLE",
            "entry":"close(t)",
            "exit":"close(t+3 calendar days)",
            "limitation":"This is a close-to-close predictive proxy, not the V21 next-bar-open execution model; no latency or bid/ask replay is claimed."
        },
        "walk_forward":{"train_months":6,"test_months":2,"step_months":1,"purge_days":3,"folds":len(folds),"details":folds},
        "lightgbm_metrics":metrics,
        "costs":{"fee_pct_per_side":0.04,"slippage_pct_per_side":0.02,
            "round_trip_cost_pct":0.12,"cost_model":"deducted once from each 3-day trade return"},
        "research_limitations":["Training rows are purged by the exact 3-calendar-day target horizon before each test fold.", "PIT membership is applied by exact UTC date/symbol key; features use prior available OHLCV history.", "PIT data coverage is limited to dates present in source artifacts.",
            "PBO is explicitly a proxy based on four probability thresholds.",
            "OOS predictions from overlapping 2-month test windows are deduplicated by timestamp/symbol, retaining the latest fold forecast.",
            "Execution metrics use close-to-close PROXY returns, not next-bar-open executable fills.",
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
