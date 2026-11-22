#!/usr/bin/env python3
"""Acquire historical Binance Vision USD-M futures daily metrics and funding archives."""
from __future__ import annotations
import argparse, concurrent.futures as cf, hashlib, io, json, logging, time, zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import pandas as pd

SYMBOLS=("BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT","LINKUSDT","LTCUSDT","BCHUSDT","NEARUSDT","INJUSDT","UNIUSDT","FILUSDT","ARBUSDT","ENAUSDT","SUIUSDT","TAOUSDT","WLDUSDT","ZECUSDT","AAVEUSDT","QNTUSDT","RSRUSDT","ONEUSDT")
METRIC_COLUMNS=("create_time","symbol","sum_open_interest","sum_open_interest_value","count_toptrader_long_short_ratio","sum_toptrader_long_short_ratio","count_long_short_ratio","sum_taker_long_short_vol_ratio")
FUNDING_COLUMNS=("calc_time","funding_interval_hours","last_funding_rate")
ROOT="https://data.binance.vision/data/futures/um"

@dataclass
class Result:
    dataset:str; symbol:str; period:str; status:str; http_status:int|None
    rows:int; bytes_downloaded:int; sha256:str|None; error:str|None

def months(start:date,end:date):
    d=date(start.year,start.month,1); last=date(end.year,end.month,1)
    while d<=last:
        yield d
        d=date(d.year+(d.month==12),1 if d.month==12 else d.month+1,1)

def read_zip(url:str, timeout:int=35):
    req=Request(url,headers={"User-Agent":"CFSS-Derivatives-History/1.0","Accept":"application/zip"})
    with urlopen(req,timeout=timeout) as r:
        payload=r.read(); status=r.status
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        files=[n for n in z.namelist() if n.lower().endswith(".csv")]
        if len(files)!=1: raise ValueError(f"EXPECTED_ONE_CSV_GOT_{len(files)}")
        raw=z.read(files[0])
    return payload,status,raw

def get_metrics(symbol:str,day:date,retries:int=3):
    stamp=day.isoformat(); url=f"{ROOT}/daily/metrics/{symbol}/{symbol}-metrics-{stamp}.zip"
    error=None; http=None
    for attempt in range(retries):
        try:
            payload,http,raw=read_zip(url)
            df=pd.read_csv(io.BytesIO(raw))
            if not set(METRIC_COLUMNS).issubset(df.columns): raise ValueError("METRICS_SCHEMA_MISMATCH")
            if df.empty: raise ValueError("EMPTY_METRICS")
            df=df[list(METRIC_COLUMNS)].copy()
            df["create_time"]=pd.to_datetime(df["create_time"],utc=True,errors="raise")
            for c in METRIC_COLUMNS[2:]:
                df[c]=pd.to_numeric(df[c],errors="coerce")
            df=df.sort_values("create_time")
            # One point-in-time end-of-day observation; no interpolation or zero-fill.
            row=df.iloc[-1].to_dict()
            row["available_at_ms"]=int(row["create_time"].timestamp()*1000)
            row["source_day"]=stamp
            return Result("metrics",symbol,stamp,"PASS",http,1,len(payload),hashlib.sha256(payload).hexdigest(),None),row
        except HTTPError as e:
            http=e.code; error=f"HTTP_{e.code}"
            if e.code==404: break
        except (URLError,TimeoutError,OSError,ValueError,zipfile.BadZipFile,pd.errors.ParserError) as e:
            error=f"{type(e).__name__}:{e}"
        if attempt+1<retries: time.sleep(0.5*(attempt+1))
    return Result("metrics",symbol,stamp,"FAIL",http,0,0,None,error),None

def get_funding(symbol:str,month:date,retries:int=3):
    ym=month.strftime("%Y-%m"); url=f"{ROOT}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip"
    error=None; http=None
    for attempt in range(retries):
        try:
            payload,http,raw=read_zip(url)
            df=pd.read_csv(io.BytesIO(raw))
            if not set(FUNDING_COLUMNS).issubset(df.columns): raise ValueError("FUNDING_SCHEMA_MISMATCH")
            df=df[list(FUNDING_COLUMNS)].copy()
            df["calc_time"]=pd.to_numeric(df["calc_time"],errors="raise").astype("int64")
            df["funding_interval_hours"]=pd.to_numeric(df["funding_interval_hours"],errors="raise")
            df["last_funding_rate"]=pd.to_numeric(df["last_funding_rate"],errors="raise")
            df["symbol"]=symbol
            df["available_at_ms"]=df["calc_time"]
            df["calc_time_utc"]=pd.to_datetime(df["calc_time"],unit="ms",utc=True)
            return Result("funding",symbol,ym,"PASS",http,len(df),len(payload),hashlib.sha256(payload).hexdigest(),None),df
        except HTTPError as e:
            http=e.code; error=f"HTTP_{e.code}"
            if e.code==404: break
        except (URLError,TimeoutError,OSError,ValueError,zipfile.BadZipFile,pd.errors.ParserError) as e:
            error=f"{type(e).__name__}:{e}"
        if attempt+1<retries: time.sleep(0.5*(attempt+1))
    return Result("funding",symbol,ym,"FAIL",http,0,0,None,error),pd.DataFrame()

def run(start:date,end:date,out:Path,workers:int):
    out.mkdir(parents=True,exist_ok=True)
    days=pd.date_range(start,end,freq="D").date
    jobs=[("metrics",s,d) for s in SYMBOLS for d in days]+[("funding",s,m) for s in SYMBOLS for m in months(start,end)]
    results=[]; metrics={s:[] for s in SYMBOLS}; funding={s:[] for s in SYMBOLS}
    def task(item):
        kind,s,p=item
        return get_metrics(s,p) if kind=="metrics" else get_funding(s,p)
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs=[pool.submit(task,j) for j in jobs]
        for n,f in enumerate(cf.as_completed(futs),1):
            res,data=f.result(); results.append(res)
            if data is not None:
                (metrics if res.dataset=="metrics" else funding)[res.symbol].append(data)
            if n%500==0: logging.info("completed %d/%d archive requests",n,len(jobs))
    symbol_reports=[]
    for s in SYMBOLS:
        m=pd.DataFrame(metrics[s]); f=pd.concat(funding[s],ignore_index=True) if funding[s] else pd.DataFrame()
        if not m.empty:
            m=m.sort_values("create_time").drop_duplicates("source_day",keep="last")
            m.to_csv(out/f"{s}_metrics_1d.csv",index=False); m.to_parquet(out/f"{s}_metrics_1d.parquet",index=False,compression="zstd")
        if not f.empty:
            f=f.sort_values("calc_time").drop_duplicates("calc_time",keep="last")
            f.to_csv(out/f"{s}_funding.csv",index=False); f.to_parquet(out/f"{s}_funding.parquet",index=False,compression="zstd")
        symbol_reports.append({"symbol":s,"metrics_days":len(m),"funding_rows":len(f),
          "metrics_first":m["source_day"].min() if not m.empty else None,
          "metrics_last":m["source_day"].max() if not m.empty else None,
          "funding_first":f["calc_time_utc"].min().isoformat() if not f.empty else None,
          "funding_last":f["calc_time_utc"].max().isoformat() if not f.empty else None})
    fails=[asdict(x) for x in results if x.status!="PASS"]
    metrics_expected=len(SYMBOLS)*len(days); funding_expected=len(SYMBOLS)*len(list(months(start,end)))
    metrics_pass=sum(x.status=="PASS" and x.dataset=="metrics" for x in results)
    funding_pass=sum(x.status=="PASS" and x.dataset=="funding" for x in results)
    report={"schema":"cfss.binance_vision_derivatives_1d.v1","source":"Binance Vision USD-M Futures",
      "start_date_utc":start.isoformat(),"end_date_utc":end.isoformat(),"created_at_utc":datetime.now(timezone.utc).isoformat(),
      "metrics_archive_pass":metrics_pass,"metrics_archive_expected":metrics_expected,
      "funding_archive_pass":funding_pass,"funding_archive_expected":funding_expected,
      "failed_archives":fails,"symbols":symbol_reports,
      "overall_status":"PASS" if metrics_pass==metrics_expected and funding_pass==funding_expected else "PARTIAL",
      "limitations":["Metrics are sampled at the last available 5-minute row of each UTC date.",
        "Use a conservative one-day availability lag when aligning metrics with daily candle decisions.",
        "Historical order-book depth is not included; LFS1 remains PROXY.",
        "Missing daily metrics/funding archives remain missing; no forward-fill or zero-fill."]}
    (out/"derivatives_manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument("--start-date",default="2024-11-01");p.add_argument("--end-date",default="2026-10-31");p.add_argument("--output",default="../artifacts/binance_vision_derivatives_1d");p.add_argument("--workers",type=int,default=16)
    a=p.parse_args()
    if not 1<=a.workers<=24: p.error("--workers must be 1..24")
    r=run(date.fromisoformat(a.start_date),date.fromisoformat(a.end_date),Path(a.output),a.workers)
    print(json.dumps({k:r[k] for k in ("overall_status","metrics_archive_pass","metrics_archive_expected","funding_archive_pass","funding_archive_expected","symbols")},indent=2))
    return 0 if r["overall_status"]=="PASS" else 2
if __name__=="__main__": raise SystemExit(main())
