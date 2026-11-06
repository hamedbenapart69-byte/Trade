"""V5 read-only futures signal engine: six deterministic engines, public data only."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor, sqrt
import json, time, uuid
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Query
from app import store

CG="https://api.coingecko.com/api/v3"
BN="https://fapi.binance.com"
STABLES={"USDT","USDC","DAI","BUSD","TUSD","FDUSD","USDE","USDS","USDD","FRAX","USDP","PYUSD","USTC","LUSD","GUSD","EURC","EURS","USD1","USDJ"}
WRAPPED={"WBTC","WETH","STETH","WSTETH","CBBTC","BTCB","WBETH","BETH","WBNB","RENBTC","TBTC"}
INTERVALS={"15m":900_000,"1h":3_600_000,"4h":14_400_000,"1d":86_400_000}

class DataError(RuntimeError): pass
class CandleError(ValueError): pass

@dataclass(frozen=True)
class Candle:
    open_time:int; open:float; high:float; low:float; close:float; volume:float; close_time:int

def ema(v:list[float],n:int)->list[float|None]:
    o=[None]*len(v)
    if len(v)<n:return o
    x=sum(v[:n])/n;o[n-1]=x;a=2/(n+1)
    for i in range(n,len(v)):x=v[i]*a+x*(1-a);o[i]=x
    return o

def rsi(v:list[float],n:int=14)->list[float|None]:
    o=[None]*len(v)
    if len(v)<=n:return o
    ds=[v[i]-v[i-1] for i in range(1,len(v))]
    g=sum(max(x,0) for x in ds[:n])/n;l=sum(max(-x,0) for x in ds[:n])/n
    o[n]=100 if l==0 else 100-100/(1+g/l)
    for i in range(n+1,len(v)):
        d=ds[i-1];g=(g*(n-1)+max(d,0))/n;l=(l*(n-1)+max(-d,0))/n
        o[i]=100 if l==0 else 100-100/(1+g/l)
    return o

def atr(cs:list[Candle],n:int=14)->list[float|None]:
    tr=[]
    for i,c in enumerate(cs):
        tr.append(c.high-c.low if i==0 else max(c.high-c.low,abs(c.high-cs[i-1].close),abs(c.low-cs[i-1].close)))
    o=[None]*len(cs)
    if len(tr)<n:return o
    x=sum(tr[:n])/n;o[n-1]=x
    for i in range(n,len(tr)):x=(x*(n-1)+tr[i])/n;o[i]=x
    return o

def macd_parts(v:list[float]):
    a,b=ema(v,12),ema(v,26);line=[x-y if x is not None and y is not None else None for x,y in zip(a,b)]
    valid=[x for x in line if x is not None];sigv=ema(valid,9);sig=[None]*len(line);j=0
    for i,x in enumerate(line):
        if x is not None:sig[i]=sigv[j];j+=1
    hist=[x-y if x is not None and y is not None else None for x,y in zip(line,sig)]
    return line,sig,hist

def macd_hist(v:list[float])->list[float|None]:return macd_parts(v)[2]

def bollinger(v:list[float],n:int=20,k:float=2.0):
    lo=[None]*len(v);mid=[None]*len(v);hi=[None]*len(v)
    for i in range(n-1,len(v)):
        w=v[i-n+1:i+1];m=sum(w)/n;sd=sqrt(sum((x-m)**2 for x in w)/n)
        mid[i]=m;hi[i]=m+k*sd;lo[i]=m-k*sd
    return lo,mid,hi

def stoch_rsi(v:list[float],n:int=14):
    rv=rsi(v,n);out=[None]*len(rv)
    for i in range(len(rv)):
        w=[x for x in rv[max(0,i-n+1):i+1] if x is not None]
        if len(w)==n and max(w)!=min(w):out[i]=(rv[i]-min(w))/(max(w)-min(w))*100
    return out

def validate_candles(cs:list[Candle],interval:int,now:int,min_count:int=210)->list[Candle]:
    if len(cs)<min_count:raise CandleError("insufficient_candles")
    if cs!=sorted(cs,key=lambda x:x.open_time):raise CandleError("candles_out_of_order")
    seen=set()
    for i,c in enumerate(cs):
        if c.open_time in seen:raise CandleError("duplicate_timestamp")
        seen.add(c.open_time)
        if any(not (x==x and abs(x)!=float("inf")) for x in (c.open,c.high,c.low,c.close,c.volume)):raise CandleError("non_finite_ohlcv")
        if min(c.open,c.high,c.low,c.close)<=0 or c.volume<0 or c.high<max(c.open,c.close,c.low) or c.low>min(c.open,c.close,c.high):raise CandleError("invalid_ohlc")
        if i and c.open_time-cs[i-1].open_time!=interval:raise CandleError("missing_or_irregular_candle")
    done=[c for c in cs if c.close_time<now]
    if len(done)<min_count or now-done[-1].close_time>interval+900_000:raise CandleError("stale_or_incomplete_candles")
    return done

def volume_ratio(cs:list[Candle])->float|None:
    if len(cs)<21:return None
    avg=sum(x.volume for x in cs[-21:-1])/20
    return cs[-1].volume/avg if avg>0 else None

def risk_calc(direction:str,entry:float,atr14:float,step:float|None,min_qty:float|None,min_notional:float|None=None)->dict:
    if entry<=0 or atr14<=0:raise DataError("non_positive_entry_or_atr")
    dist=1.5*atr14;stop=entry-dist if direction=="LONG" else entry+dist
    tp=entry+2*dist if direction=="LONG" else entry-2*dist
    stop_pct=dist/entry*100;max_notional=4/(stop_pct/100);qty=max_notional/entry
    if step and step>0:qty=floor(qty/step+1e-12)*step
    if min_qty is not None and qty<min_qty:qty=0
    notional=qty*entry;lev=max_notional/200;loss=notional*stop_pct/100;rr=abs(tp-entry)/abs(entry-stop)
    reason=None
    if qty<=0:reason="quantity_below_contract_minimum"
    elif not .5<=stop_pct<=3:reason="stop_distance_out_of_range"
    elif min_notional is not None and notional<min_notional:reason="below_contract_minimum_notional"
    elif lev>5:reason="required_leverage_exceeds_5x"
    elif loss>4+1e-9:reason="planned_loss_exceeds_4_usd"
    elif rr<2:reason="reward_to_risk_below_2"
    return {"entry":entry,"stop_loss":stop,"take_profit":tp,"stop_pct":stop_pct,"notional_usd":notional,
            "required_leverage":lev,"quantity_base":qty,"planned_loss_usd":loss,"reward_to_risk":rr,"valid":reason is None,"reason":reason}

class PublicMarketData:
    def __init__(self,client:httpx.Client|None=None):
        self.client=client or httpx.Client(timeout=12,follow_redirects=False);self.own=client is None
    def get(self,base,path,params=None):
        try:
            r=self.client.get(base+path,params=params,headers={"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            r.raise_for_status();return r.json()
        except (httpx.HTTPError,ValueError,TypeError) as e:raise DataError(f"provider_error:{path}:{type(e).__name__}") from e
    def discover(self):
        xs=self.get(CG,"/coins/markets",{"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"false"})
        if not isinstance(xs,list):raise DataError("invalid_coingecko_market_list")
        out=[]
        for x in xs:
            if isinstance(x,dict) and x.get("symbol") and isinstance(x.get("total_volume"),(int,float)):
                out.append({"id":str(x.get("id","")),"symbol":str(x["symbol"]).upper(),"volume":float(x["total_volume"])})
        return sorted(out,key=lambda x:x["volume"],reverse=True)
    def contracts(self):
        x=self.get(BN,"/fapi/v1/exchangeInfo");out={}
        for s in x.get("symbols",[]):
            if s.get("contractType")!="PERPETUAL" or s.get("status")!="TRADING" or s.get("quoteAsset")!="USDT":continue
            f={z.get("filterType"):z for z in s.get("filters",[])};lot=f.get("LOT_SIZE",{});pf=f.get("PRICE_FILTER",{})
            try:out[s["baseAsset"].upper()]={"symbol":s["symbol"],"base":s["baseAsset"],"quote":s["quoteAsset"],"tick":float(pf["tickSize"]),"step":float(lot["stepSize"]),"min_qty":float(lot["minQty"]),"min_notional":float((f.get("MIN_NOTIONAL") or f.get("NOTIONAL") or {}).get("notional",0) or 0)}
            except (KeyError,ValueError,TypeError):continue
        return out
    def tickers(self):return {x.get("symbol"):x for x in self.get(BN,"/fapi/v1/ticker/24hr") if isinstance(x,dict) and x.get("symbol")}
    def premium(self):
        xs=self.get(BN,"/fapi/v1/premiumIndex");xs=xs if isinstance(xs,list) else [xs];out={}
        for x in xs:
            try:out[x["symbol"]]={"price":float(x["markPrice"]),"funding":float(x["lastFundingRate"]),"time":int(x["time"]),"next":int(x["nextFundingTime"])}
            except (KeyError,ValueError,TypeError):continue
        return out
    def funding_intervals(self):
        try:return {x["symbol"]:int(x["fundingIntervalHours"]) for x in self.get(BN,"/fapi/v1/fundingInfo") if x.get("symbol") and x.get("fundingIntervalHours")}
        except DataError:return {}
    def candles(self,symbol,tf,limit=260,start=None):
        p={"symbol":symbol,"interval":tf,"limit":limit}
        if start is not None:p["startTime"]=start
        xs=self.get(BN,"/fapi/v1/klines",p)
        try:return [Candle(int(x[0]),float(x[1]),float(x[2]),float(x[3]),float(x[4]),float(x[5]),int(x[6])) for x in xs]
        except (ValueError,TypeError,IndexError) as e:raise DataError("invalid_kline_payload") from e
    def oi(self,symbol):
        try:x=self.get(BN,"/fapi/v1/openInterest",{"symbol":symbol})
        except DataError:return None
        change=None;change_ts=None
        try:
            hist=self.get(BN,"/futures/data/openInterestHist",{"symbol":symbol,"period":"1h","limit":3})
            if isinstance(hist,list) and len(hist)>=2:
                old,new=hist[-2],hist[-1];dt=int(new["timestamp"])-int(old["timestamp"]);a=float(old["sumOpenInterestValue"])
                if a and 2_700_000<=dt<=4_500_000:change=(float(new["sumOpenInterestValue"])/a-1)*100;change_ts=int(new["timestamp"])
        except (DataError,KeyError,ValueError,TypeError):pass
        try:return {"value":float(x["openInterest"]),"timestamp_ms":int(x["time"]),"change_pct_1h":change,"change_timestamp_ms":change_ts}
        except (KeyError,ValueError,TypeError):return None
    def long_short(self,symbol):
        try:
            xs=self.get(BN,"/futures/data/globalLongShortAccountRatio",{"symbol":symbol,"period":"1h","limit":2})
            if not xs:return None
            x=xs[-1];return {"ratio":float(x["longShortRatio"]),"long_pct":float(x["longAccount"]),"short_pct":float(x["shortAccount"]),"timestamp_ms":int(x["timestamp"])}
        except (DataError,KeyError,ValueError,TypeError):return None
    def close(self):
        if self.own:self.client.close()

def _trend(cs,daily=False):
    v=[x.close for x in cs];a=ema(v,20)[-1];b=ema(v,50)[-1]
    if a is None or b is None:return "UNKNOWN"
    if v[-1]>a>b:return "BULLISH" if daily else "UP"
    if v[-1]<a<b:return "BEARISH" if daily else "DOWN"
    return "NEUTRAL" if daily else "FLAT"

def _structure(cs,direction):
    hs=[];ls=[]
    for i in range(2,len(cs)-2):
        w=cs[i-2:i+3];c=cs[i]
        if c.high>max(x.high for j,x in enumerate(w) if j!=2):hs.append(c.high)
        if c.low<min(x.low for j,x in enumerate(w) if j!=2):ls.append(c.low)
    if len(hs)<2 or len(ls)<2:return {"classification":"UNKNOWN","bos":False}
    hh=hs[-1]>hs[-2];hl=ls[-1]>ls[-2];lh=hs[-1]<hs[-2];ll=ls[-1]<ls[-2]
    return {"classification":"BULLISH" if hh and hl else "BEARISH" if lh and ll else "MIXED",
            "bos":cs[-1].close>hs[-1] if direction=="LONG" else cs[-1].close<ls[-1]}

def _score(direction,tech,trends,structure,oi,ls,funding,entry_ok,risk_ok):
    p={"core_technical":25,"multi_timeframe":0,"market_structure":0,"volume_momentum":0,"derivatives":0,
       "smart_money_onchain":0,"entry_risk":0,"independent_confirmation":0}
    desired="UP" if direction=="LONG" else "DOWN";daily="BULLISH" if direction=="LONG" else "BEARISH"
    if trends["1d"]==daily:p["multi_timeframe"]+=7
    if trends["4h"]==desired:p["multi_timeframe"]+=5
    elif trends["4h"]=="FLAT":p["multi_timeframe"]+=2
    close=tech["close"];e20=tech["ema20"];e50=tech["ema50"]
    if (close>e20>e50) if direction=="LONG" else (close<e20<e50):p["multi_timeframe"]+=3
    wanted="BULLISH" if direction=="LONG" else "BEARISH"
    if structure["classification"]==wanted:p["market_structure"]+=10
    if structure["bos"]:p["market_structure"]+=5
    if tech["volume_ratio"]>1.5:p["volume_momentum"]+=4
    if tech["macd_aligned"]:p["volume_momentum"]+=3
    if (tech["rsi"]<30) if direction=="LONG" else (tech["rsi"]>70):p["volume_momentum"]+=3
    if (direction=="LONG" and funding<0) or (direction=="SHORT" and funding>0):p["derivatives"]+=3
    if oi and oi.get("change_pct_1h") is not None:
        if oi["change_pct_1h"]>0 and ((direction=="LONG" and tech["price_change"]>0) or (direction=="SHORT" and tech["price_change"]<0)):p["derivatives"]+=4
    if ls and ((direction=="LONG" and ls["ratio"]<1) or (direction=="SHORT" and ls["ratio"]>1)):p["derivatives"]+=3
    if risk_ok:p["entry_risk"]+=10
    if entry_ok:p["entry_risk"]+=5
    return sum(p.values()),p

def init_signal_db():
    with store.db_connection() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS signal_scans(scan_id TEXT PRIMARY KEY,scanned_at TEXT NOT NULL,result_json TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS signal_records(signal_id TEXT PRIMARY KEY,scan_id TEXT NOT NULL REFERENCES signal_scans(scan_id),
          symbol TEXT NOT NULL,direction TEXT NOT NULL,decision TEXT NOT NULL,entry REAL,stop_loss REAL,take_profit REAL,entry_ts_ms INTEGER,
          confidence INTEGER NOT NULL,data_grade TEXT NOT NULL,outcome TEXT NOT NULL DEFAULT 'OPEN',outcome_at TEXT,outcome_price REAL,realized_r REAL,data_json TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_signal_records_outcome ON signal_records(outcome,decision)")

def save_scan(result):
    init_signal_db();published=result.get("actionable",[])+result.get("conditional",[]);saved=0
    with store.db_connection() as c:
        c.execute("INSERT OR REPLACE INTO signal_scans VALUES(?,?,?)",(result["scan_id"],result["scanned_at"],json.dumps(result,ensure_ascii=False)))
        for x in published:
            c.execute("""INSERT INTO signal_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (str(uuid.uuid4()),result["scan_id"],x["symbol"],x.get("direction") or "UNKNOWN",x["decision"],x.get("entry"),x.get("stop_loss"),x.get("take_profit"),x.get("entry_observed_at_ms"),int(x.get("confidence_v5",0)),x.get("data_grade","FAIL"),"WATCH" if x["decision"].startswith("CONDITIONAL") else "OPEN",None,None,None,json.dumps(x,ensure_ascii=False)))
            saved+=1
    return {"published_records_saved":saved}

def latest_scan():
    init_signal_db()
    with store.db_connection() as c:r=c.execute("SELECT result_json FROM signal_scans ORDER BY scanned_at DESC LIMIT 1").fetchone()
    return json.loads(r[0]) if r else None

def performance():
    init_signal_db()
    with store.db_connection() as c:rows=c.execute("SELECT symbol,decision,data_grade,confidence,outcome,realized_r,data_json FROM signal_records WHERE decision IN ('BUY_NOW','SELL_NOW') ORDER BY rowid").fetchall()
    closed=[r for r in rows if r["outcome"] in {"TP1","STOP_LOSS"} and r["realized_r"] is not None]
    vals=[float(r["realized_r"]) for r in closed];wins=[x for x in vals if x>0];loss=[x for x in vals if x<0]
    eq=peak=dd=0
    for x in vals:eq+=x;peak=max(peak,eq);dd=max(dd,peak-eq)
    rr=[];returns=[]
    for r in closed:
        d=json.loads(r["data_json"]);risk=d.get("risk",{})
        if risk.get("reward_to_risk") is not None:rr.append(float(risk["reward_to_risk"]))
        if d.get("stop_pct") is not None:returns.append(float(r["realized_r"])*float(d["stop_pct"]))
    def segment(key_fn):
        groups={}
        for r in rows:
            key=key_fn(r)
            if key is None:continue
            groups.setdefault(key,[]).append(r)
        out={}
        for k,rs in groups.items():
            vs=[float(x["realized_r"]) for x in rs if x["outcome"] in {"TP1","STOP_LOSS"} and x["realized_r"] is not None]
            w=[x for x in vs if x>0];l=[x for x in vs if x<0]
            out[str(k)]={"published":len(rs),"closed":len(vs),"win_rate_pct":len(w)/len(vs)*100 if vs else None,
                         "expectancy_r":sum(vs)/len(vs) if vs else None,"profit_factor":sum(w)/abs(sum(l)) if l else ("undefined_no_losses" if w else None)}
        return out
    def conf(r):
        n=int(r["confidence"])
        return "<60" if n<60 else "60-69" if n<70 else "70-79" if n<80 else "80-89" if n<90 else "90-100"
    def timeframe(r):
        try:return json.loads(r["data_json"]).get("primary_timeframe","1h")
        except Exception:return "unknown"
    return {"mode":"paper_signal_tracking_not_executed_trades","published_actionable":len(rows),"closed_observations":len(closed),
      "tp1_count":sum(r["outcome"]=="TP1" for r in rows),"stop_loss_count":sum(r["outcome"]=="STOP_LOSS" for r in rows),
      "open_count":sum(r["outcome"]=="OPEN" for r in rows),"win_rate_pct":len(wins)/len(closed)*100 if closed else None,
      "loss_rate_pct":len(loss)/len(closed)*100 if closed else None,"average_reward_to_risk":sum(rr)/len(rr) if rr else None,
      "average_realized_return_pct_of_notional":sum(returns)/len(returns) if returns else None,"average_realized_r":sum(vals)/len(vals) if vals else None,
      "expectancy_r":sum(vals)/len(vals) if vals else None,"profit_factor":sum(wins)/abs(sum(loss)) if loss else ("undefined_no_losses" if wins else None),
      "max_drawdown_r":dd,"by_asset":segment(lambda r:r["symbol"]),"by_timeframe":segment(timeframe),
      "by_decision":segment(lambda r:r["decision"]),"by_data_grade":segment(lambda r:r["data_grade"]),"by_confidence_range":segment(conf)}

def render_output(r):
    if r.get("status")=="DATA_UNAVAILABLE":return "DATA UNAVAILABLE — do not trade today."
    fmt=lambda x:"—" if x is None else format(float(x),".10g")
    out=[];rows=r.get("actionable",[]);watch=r.get("conditional",[])
    if rows:
        out += ["| Symbol | Decision | Direction | Entry | Stop-Loss | Take-Profit | Stop % | Leverage | Risk $ | Data Grade | Confidence |","|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|"]
        for x in rows:
            z=x["risk"];out.append(f"| {x['symbol']} | {x['decision']} | {x['direction']} | {fmt(x['entry'])} | {fmt(x['stop_loss'])} | {fmt(x['take_profit'])} | {fmt(x['stop_pct'])}% | {fmt(z['required_leverage'])}x | USD {fmt(z['planned_loss_usd'])} | {x['data_grade']} | {x['confidence_v5']} |")
    elif not watch:out.append("No qualifying signals today.")
    if watch:
        if out:out.append("")
        out += ["Conditional watchlist","| Symbol | Decision | Direction | Confirmation Required | Trigger Level | Confidence | Data Grade |","|---|---|---|---|---:|---:|---|"]
        for x in watch:out.append(f"| {x['symbol']} | {x['decision']} | {x['direction']} | {x.get('confirmation_required') or '—'} | {fmt(x.get('trigger_level'))} | {x['confidence_v5']} | {x['data_grade']} |")
    if r.get("partial_scan"):out.append(f"Partial scan: {r.get('screened_assets',0)}/30.")
    return "\n".join(out)

class FuturesSignalEngine:
    def __init__(self,provider=None,clock=None):self.p=provider or PublicMarketData();self.own=provider is None;self.clock=clock or (lambda:int(time.time()*1000))
    def scan(self,extended=False,limit=30):
        now=self.clock();assets=self.p.discover();contracts=self.p.contracts();tickers=self.p.tickers();prem=self.p.premium();intervals=self.p.funding_intervals()
        counts={}
        for a in assets:counts[a["symbol"]]=counts.get(a["symbol"],0)+1
        eligible=[]
        for a in assets:
            s=a["symbol"]
            if s in STABLES or s in WRAPPED or counts[s]>1 or not a["id"]:continue
            c=contracts.get(s)
            if c and c["symbol"] in tickers and c["symbol"] in prem and float(tickers[c["symbol"]].get("quoteVolume",0) or 0)>0:eligible.append((a,c))
        cap=100 if extended else max(1,min(limit,100));selected=eligible[:cap];candidates=[]
        for a,c in selected:
            try:candidates.append(self.evaluate(a,c,prem[c["symbol"]],intervals.get(c["symbol"],8),now))
            except (DataError,CandleError,ValueError,TypeError,KeyError) as e:
                candidates.append({"symbol":c["symbol"],"asset":a["id"],"decision":"INSUFFICIENT_DATA","direction":None,"data_grade":"FAIL","confidence_v5":0,"v3_score":None,"reason":f"mandatory_data_error:{type(e).__name__}"})
        actionable=sorted([x for x in candidates if x["decision"] in {"BUY_NOW","SELL_NOW"}],key=lambda x:(-x["confidence_v5"],x.get("data_grade","Z"),-x.get("risk",{}).get("reward_to_risk",0)))[:10]
        conditional=sorted([x for x in candidates if x["decision"] in {"CONDITIONAL_BUY","CONDITIONAL_SELL"}],key=lambda x:-x["confidence_v5"])
        return {"scan_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),"scanned_at":datetime.now(timezone.utc).isoformat(),
          "universe_requested":cap,"eligible_assets":len(eligible),"screened_assets":len(selected),"partial_scan":cap>=30 and len(selected)<30,
          "source_status":{"discovery":"CoinGecko public API","futures":"Binance USD-M public market-data API","account_connection":False,"order_execution":False},
          "actionable":actionable,"conditional":conditional,"other_candidates":[x for x in candidates if x["decision"] not in {"BUY_NOW","SELL_NOW","CONDITIONAL_BUY","CONDITIONAL_SELL"}],
          "coverage":{"total_candidates":len(candidates),"insufficient_data":sum(x["decision"]=="INSUFFICIENT_DATA" for x in candidates),"rejected":sum(x["decision"]=="REJECT" for x in candidates),"wait":sum(x["decision"]=="WAIT" for x in candidates)}}
    def evaluate(self,a,c,p,fh,now):
        sym=c["symbol"];price=p["price"]
        if price<=0 or now-p["time"]>900_000 or p["time"]>now+60_000:raise DataError("stale_futures_mark_price")
        cs={tf:validate_candles(self.p.candles(sym,tf,260),iv,now) for tf,iv in INTERVALS.items()}
        one=cs["1h"];cl=[x.close for x in one];rv=rsi(cl)[-1];e20=ema(cl,20)[-1];e50=ema(cl,50)[-1];a14=atr(one)[-1];vr=volume_ratio(one)
        if None in (rv,e20,e50,a14,vr):raise DataError("mandatory_indicator_missing")
        trends={"1d":_trend(cs["1d"],True),"4h":_trend(cs["4h"]),"1h":_trend(one)}
        hours=int(fh or 8)
        if hours<=0:raise DataError("invalid_funding_interval")
        fund=p["funding"]*8/hours
        long=rv<35 and vr>1.2 and one[-1].close>e20 and trends["4h"] in {"UP","FLAT"} and abs(fund)<.0005
        short=rv>65 and vr>1.2 and one[-1].close<e20 and trends["4h"] in {"DOWN","FLAT"} and abs(fund)<.0005
        if not long and not short:return {"symbol":sym,"asset":a["id"],"decision":"REJECT","direction":None,"data_grade":"B","confidence_v5":0,"v3_score":None,"reason":"mandatory_v3_baseline_not_satisfied","technical":{"rsi14":rv,"volume_ratio":vr},"trends":trends}
        d="LONG" if long else "SHORT";oi=self.p.oi(sym);ls=self.p.long_short(sym)
        if oi and (now-oi["timestamp_ms"]>900_000 or oi["timestamp_ms"]>now+60_000):oi=None
        if oi and oi.get("change_timestamp_ms") and (now-oi["change_timestamp_ms"]>4_500_000 or oi["change_timestamp_ms"]>now+60_000):oi["change_pct_1h"]=None
        if ls and (now-ls["timestamp_ms"]>4_500_000 or ls["timestamp_ms"]>now+60_000):ls=None
        ml,ms,mh=macd_parts(cl);macd_ok=mh[-1] is not None and mh[-2] is not None and ((mh[-1]>0 and mh[-1]>=mh[-2]) if d=="LONG" else (mh[-1]<0 and mh[-1]<=mh[-2]))
        bl,bm,bu=bollinger(cl);sr=stoch_rsi(cl)
        tech={"rsi":rv,"ema20":e20,"ema50":e50,"ema200":ema(cl,200)[-1],"atr14":a14,"volume_ratio":vr,"close":one[-1].close,
          "macd":ml[-1],"macd_signal":ms[-1],"macd_histogram":mh[-1],"bollinger_lower":bl[-1],"bollinger_mid":bm[-1],
          "bollinger_upper":bu[-1],"stoch_rsi":sr[-1],"macd_aligned":macd_ok,"price_change":(cl[-1]/cl[-2]-1)*100}
        st=_structure(cs["4h"],d);risk=risk_calc(d,price,a14,c["step"],c["min_qty"],c.get("min_notional"))
        e15=ema([x.close for x in cs["15m"]],20)[-1];last=cs["15m"][-1];prev=cs["15m"][-2]
        entry_ok=e15 is not None and ((d=="LONG" and last.close>e15 and last.close>=prev.close) or (d=="SHORT" and last.close<e15 and last.close<=prev.close))
        score,parts=_score(d,tech,trends,st,oi,ls,fund,entry_ok,risk["valid"])
        v3=50+(10 if (rv<30 if d=="LONG" else rv>70) else 0)+(10 if vr>1.5 else 0)+(10 if trends["4h"]==("UP" if d=="LONG" else "DOWN") else 0)+(10 if ((one[-1].close>e20 and one[-1].close>e50) if d=="LONG" else (one[-1].close<e20 and one[-1].close<e50)) else 0)+(10 if ((d=="LONG" and fund<0) or (d=="SHORT" and fund>0)) else 0)
        grade="B"  # on-chain and independent-confirmation evidence are not connected yet
        conflict=trends["1d"] not in {"NEUTRAL","BULLISH" if d=="LONG" else "BEARISH"}
        if not risk["valid"]:decision="REJECT"
        elif score>=70 and entry_ok and not conflict:decision="BUY_NOW" if d=="LONG" else "SELL_NOW"
        elif score>=60 and (not entry_ok or conflict):decision="CONDITIONAL_BUY" if d=="LONG" else "CONDITIONAL_SELL"
        else:decision="WAIT"
        confirm=None;trigger_level=None
        if decision.startswith("CONDITIONAL"):
            if not entry_ok:
                confirm="15m completed close above EMA20 and not below prior close" if d=="LONG" else "15m completed close below EMA20 and not above prior close"
                trigger_level=max(e15,prev.close) if d=="LONG" else min(e15,prev.close)
            else:confirm="daily regime realigns with setup"
        return {"symbol":sym,"asset":a["id"],"primary_timeframe":"1h","decision":decision,"direction":d,"entry_type":"verified_futures_mark_price_reference",
          "entry":price,"entry_observed_at_ms":p["time"],"stop_loss":risk["stop_loss"],"take_profit":risk["take_profit"],"stop_pct":risk["stop_pct"],
          "risk":risk,"data_grade":grade,"confidence_v5":score,"v5_score_components":parts,"v3_score":v3,"technical":tech,"trends":trends,"structure":st,
          "derivatives":{"funding_rate_raw":p["funding"],"funding_interval_hours":hours,"funding_normalized_8h":fund,"open_interest":oi,"global_long_short_ratio":ls},
          "confirmation_required":confirm,"trigger_level":trigger_level,"sources":{"discovery":"CoinGecko","ohlcv":"Binance USD-M public API","futures":"Binance USD-M public API"},
          "limitations":["Smart-money/on-chain evidence unavailable; zero points.","Independent confirmation unavailable; zero points.","Fees, spread, slippage and liquidation mechanics excluded.","No exchange account connection or order execution."]}
    def close(self):
        if self.own:self.p.close()

router=APIRouter(tags=["futures-signals"])
@router.post("/signals/scan")
def run_scan(extended:bool=Query(False),universe_limit:int=Query(30,ge=1,le=100)):
    e=FuturesSignalEngine()
    try:
        r=e.scan(extended,universe_limit)
        r["status"]="DATA_UNAVAILABLE" if r["screened_assets"]==0 or r["coverage"]["insufficient_data"]==r["screened_assets"] else "SCAN_COMPLETED"
        r["formatted_output"]=render_output(r);r["persistence"]=save_scan(r)
        return r
    except DataError as ex:raise HTTPException(503,detail={"status":"INSUFFICIENT_DATA","reason":str(ex),"action":"DATA UNAVAILABLE — do not trade today."}) from ex
    finally:e.close()

@router.get("/signals/latest")
def get_latest():
    r=latest_scan()
    if r is None:raise HTTPException(404,detail="no_scan_recorded")
    return r

@router.get("/signals/performance")
def get_performance():return performance()

@router.post("/signals/evaluate")
def evaluate_outcomes():
    init_signal_db();checked=closed=ambiguous=0;p=PublicMarketData()
    try:
        with store.db_connection() as db:rows=db.execute("SELECT * FROM signal_records WHERE outcome='OPEN' AND decision IN ('BUY_NOW','SELL_NOW')").fetchall()
        for row in rows:
            checked+=1
            try:cs=validate_candles(p.candles(row["symbol"],"15m",1500,row["entry_ts_ms"]),900_000,int(time.time()*1000),1)
            except (DataError,CandleError):continue
            for c in cs:
                if c.open_time<int(row["entry_ts_ms"] or 0):continue
                if row["direction"]=="LONG":sl=c.low<=row["stop_loss"];tp=c.high>=row["take_profit"]
                else:sl=c.high>=row["stop_loss"];tp=c.low<=row["take_profit"]
                if sl and tp:outcome="UNKNOWN";rr=0;ambiguous+=1
                elif sl:outcome="STOP_LOSS";rr=-1
                elif tp:outcome="TP1";rr=abs(row["take_profit"]-row["entry"])/abs(row["entry"]-row["stop_loss"])
                else:continue
                with store.db_connection() as db:db.execute("UPDATE signal_records SET outcome=?,outcome_at=?,outcome_price=?,realized_r=? WHERE signal_id=? AND outcome='OPEN'",(outcome,datetime.fromtimestamp(c.close_time/1000,tz=timezone.utc).isoformat(),c.close,rr,row["signal_id"]))
                if outcome!="UNKNOWN":closed+=1
                break
        return {"checked":checked,"newly_closed":closed,"ambiguous_same_candle":ambiguous,"performance":performance(),"note":"Same-candle stop/target touches remain UNKNOWN; no intrabar sequence is assumed."}
    finally:p.close()
