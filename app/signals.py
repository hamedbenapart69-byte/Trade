"""V5 read-only futures signal engine using aggregated perps data and independent DEX OHLCV."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor, sqrt
import json, time, uuid, os
import httpx
from fastapi import APIRouter, HTTPException, Query
from app import store

CG="https://api.coingecko.com/api/v3"
OPTI="https://optimistfi.com"
GECKO="https://api.geckoterminal.com/api/v2"
STABLES={"USDT","USDC","DAI","BUSD","TUSD","FDUSD","USDE","USDS","USDD","FRAX","USDP","PYUSD","USTC","LUSD","GUSD","EURC","EURS","USD1","USDJ"}
WRAPPED={"WBTC","WETH","STETH","WSTETH","CBBTC","BTCB","WBETH","BETH","WBNB","RENBTC","TBTC"}
INTERVALS={"15m":900_000,"1h":3_600_000,"4h":14_400_000,"1d":86_400_000}

class DataError(RuntimeError):pass
class CandleError(ValueError):pass

@dataclass(frozen=True)
class Candle:
    open_time:int;open:float;high:float;low:float;close:float;volume:float;close_time:int;is_final:bool=True

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
    for i,c in enumerate(cs):tr.append(c.high-c.low if i==0 else max(c.high-c.low,abs(c.high-cs[i-1].close),abs(c.low-cs[i-1].close)))
    o=[None]*len(cs)
    if len(tr)<n:return o
    x=sum(tr[:n])/n;o[n-1]=x
    for i in range(n,len(tr)):x=(x*(n-1)+tr[i])/n;o[i]=x
    return o

def macd_parts(v:list[float]):
    a,b=ema(v,12),ema(v,26);line=[x-y if x is not None and y is not None else None for x,y in zip(a,b)]
    valid=[x for x in line if x is not None];sv=ema(valid,9);sig=[None]*len(line);j=0
    for i,x in enumerate(line):
        if x is not None:sig[i]=sv[j];j+=1
    hist=[x-y if x is not None and y is not None else None for x,y in zip(line,sig)]
    return line,sig,hist

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
    cs=[c for c in cs if c.is_final]
    if len(cs)<min_count:raise CandleError("insufficient_completed_candles")
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

def risk_calc(direction:str,entry:float,stop:float,capital:float=200.0,risk_usd:float=4.0,max_leverage:float=5.0)->dict:
    if entry<=0 or stop<=0 or (direction=="LONG" and stop>=entry) or (direction=="SHORT" and stop<=entry):
        raise DataError("invalid_entry_or_stop")
    dist=abs(entry-stop);stop_pct=dist/entry*100;max_notional=risk_usd/(stop_pct/100);required=max_notional/capital
    qty_base=max_notional/entry;loss=max_notional*stop_pct/100
    tp1=entry+2*dist if direction=="LONG" else entry-2*dist
    tp2=entry+3*dist if direction=="LONG" else entry-3*dist
    tp3=entry+4*dist if direction=="LONG" else entry-4*dist
    reason=None
    if not .5<=stop_pct<=3:reason="stop_distance_out_of_range"
    elif required>max_leverage:reason="required_leverage_exceeds_5x"
    elif loss>risk_usd+1e-9:reason="planned_loss_exceeds_4_usd"
    return {"entry":entry,"stop_loss":stop,"take_profit":tp1,"take_profit_2":tp2,"take_profit_3":tp3,
      "stop_pct":stop_pct,"max_notional_usd":max_notional,"notional_usd":max_notional,"required_leverage":required,
      "quantity_base":qty_base,"quantity_contracts_reference":None,"contract_multiplier_reference":None,
      "planned_loss_usd":loss,"reward_to_risk":abs(tp1-entry)/dist,"valid":reason is None,"reason":reason,
      "capital_assumption_usd":capital,"risk_cap_usd":risk_usd,"contract_quantity_note":"Base-unit sizing only; TraderSpy does not expose venue lot step or multiplier."}

class PublicMarketData:
    """TraderSpy read-only REST adapter. Requires a free data-provider key, never an exchange key."""
    BASE="https://api.traderspy.app/v1"
    MAX_RUN_CALLS=190
    def __init__(self,client:httpx.Client|None=None,api_key:str|None=None):
        self.client=client or httpx.Client(timeout=25,follow_redirects=False);self.own=client is None
        self.api_key=api_key or os.getenv("TRADERSPY_API_KEY")
        self.last_call=0.0;self.calls=0
    def _ts_get(self,path,params=None):
        if not self.api_key:raise DataError("TRADERSPY_API_KEY_NOT_CONFIGURED")
        if self.calls>=self.MAX_RUN_CALLS:raise DataError("traderspy_run_call_budget_reached")
        wait=6.1-(time.monotonic()-self.last_call)
        if wait>0:time.sleep(wait)
        self.last_call=time.monotonic()
        try:
            r=self.client.get(self.BASE+path,params=params,headers={"Authorization":"Bearer "+self.api_key,"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            if r.status_code==401:raise DataError("traderspy_api_key_invalid_or_unauthorized")
            if r.status_code==403:raise DataError("traderspy_free_plan_or_ip_restriction")
            if r.status_code==429:raise DataError("traderspy_rate_or_daily_limit_reached")
            r.raise_for_status();self.calls+=1;return r.json()
        except DataError:raise
        except (httpx.HTTPError,ValueError,TypeError) as e:raise DataError(f"traderspy_provider_error:{path}:{type(e).__name__}") from e
    def discover(self):
        try:
            r=self.client.get(CG+"/coins/markets",params={"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"false"},
                headers={"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            r.raise_for_status();xs=r.json()
        except (httpx.HTTPError,ValueError,TypeError) as e:raise DataError("coingecko_discovery_unavailable") from e
        if not isinstance(xs,list):raise DataError("invalid_coingecko_market_list")
        out=[]
        for x in xs:
            if not isinstance(x,dict) or not x.get("symbol"):continue
            out.append({"id":str(x.get("id","")),"symbol":str(x.get("symbol","")).upper(),"name":x.get("name"),
              "volume":float(x.get("total_volume") or 0),"market_cap_rank":x.get("market_cap_rank"),
              "current_price":float(x.get("current_price") or 0),"market_cap":float(x.get("market_cap") or 0)})
        return sorted(out,key=lambda x:x["volume"],reverse=True)
    def tracked_symbols(self):
        r=self._ts_get("/market/symbols")
        raw=r.get("symbols",r.get("data",[]))
        out=set()
        for x in raw:
            s=x if isinstance(x,str) else x.get("symbol") if isinstance(x,dict) else None
            if s:out.add(str(s).upper())
        return out
    def candles(self,symbol,tf,limit=220):
        r=self._ts_get("/market/candles",{"symbol":symbol,"interval":tf,"limit":limit})
        raw=r.get("candles",[])
        try:
            out=[]
            for x in raw:
                ot=int(x.get("openTime") or x.get("open_time"))
                iv=INTERVALS[tf]
                ct=int(x.get("closeTime") or x.get("close_time") or (ot+iv-1))
                out.append(Candle(ot,float(x["open"]),float(x["high"]),float(x["low"]),float(x["close"]),
                    float(x["volume"]),ct,bool(x.get("isFinal",x.get("is_final",True)))))
            return sorted(out,key=lambda x:x.open_time)
        except (ValueError,TypeError,KeyError) as e:raise DataError("invalid_traderspy_ohlcv_payload") from e
    def prices(self,symbols):
        out={}
        for i in range(0,len(symbols),20):
            batch=symbols[i:i+20];r=self._ts_get("/market/prices",{"symbols":",".join(batch)})
            for x in r.get("data",[]):
                if x.get("symbol"):out[str(x["symbol"]).upper()]=x
        return out
    def derivatives(self,symbols):
        out={}
        for i in range(0,len(symbols),5):
            batch=symbols[i:i+5];r=self._ts_get("/market/derivatives",{"symbols":",".join(batch)})
            for x in r.get("data",[]):
                if x.get("symbol"):out[str(x["symbol"]).upper()]=x
        return out
    def smart_money(self):
        traders=self._ts_get("/smart-money/traders",{"source":"all","timeRange":"7D","rankingType":"PNL","sortBy":"SCORE","order":"DESC","limit":100})
        positions=self._ts_get("/smart-money/positions",{"status":"open","source":"all","limit":100,"offset":0})
        signals=self._ts_get("/signals",{"limit":100,"importance":"high"})
        return {"traders":traders.get("data",[]),"positions":positions.get("data",[]),"signals":signals.get("data",[])}
    def close(self):
        if self.own:self.client.close()

def _iso_ms(s):
    if isinstance(s,(int,float)):
        return int(s if s>10_000_000_000 else s*1000)
    try:return int(datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp()*1000)
    except (ValueError,AttributeError,TypeError):return 0

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

def _score(direction,tech,trends,structure,oi4h,oi24h,ls,funding,entry_points,risk_ok,smart_points,independent_ok):
    p={"core_technical":0,"multi_timeframe":0,"market_structure":0,"volume_momentum":0,"derivatives":0,
       "smart_money_onchain":0,"entry_risk":0,"independent_confirmation":0}
    aligned=(tech["close"]>tech["ema20"]>tech["ema50"]) if direction=="LONG" else (tech["close"]<tech["ema20"]<tech["ema50"])
    p["core_technical"]+=8 if aligned else 0
    if (tech["rsi"]<35 if direction=="LONG" else tech["rsi"]>65):p["core_technical"]+=5
    if tech["macd_aligned"]:p["core_technical"]+=5
    if tech.get("adx") is not None and tech["adx"]>=20:p["core_technical"]+=4
    if tech.get("bb_position") in ({"lower_half","lower_band"} if direction=="LONG" else {"upper_half","upper_band"}):p["core_technical"]+=3
    daily="BULLISH" if direction=="LONG" else "BEARISH";desired="UP" if direction=="LONG" else "DOWN"
    if trends["1d"]==daily:p["multi_timeframe"]+=7
    if trends["4h"]==desired:p["multi_timeframe"]+=5
    elif trends["4h"]=="FLAT":p["multi_timeframe"]+=2
    if trends["1h"]==desired:p["multi_timeframe"]+=3
    wanted="BULLISH" if direction=="LONG" else "BEARISH"
    if structure["classification"]==wanted:p["market_structure"]+=5
    if structure.get("bos") or structure.get("choch"):p["market_structure"]+=5
    if structure.get("fvg_aligned") or structure.get("order_block_aligned") or structure.get("liquidity_sweep_aligned"):p["market_structure"]+=5
    if tech["volume_ratio"]>1.5:p["volume_momentum"]+=4
    if tech.get("obv_aligned"):p["volume_momentum"]+=3
    if tech.get("mfi_aligned"):p["volume_momentum"]+=3
    if (direction=="LONG" and funding<0) or (direction=="SHORT" and funding>0):p["derivatives"]+=3
    oi_values=[x for x in (oi4h,oi24h) if x is not None]
    if oi_values and any((x>0 and tech["price_change"]>0) if direction=="LONG" else (x>0 and tech["price_change"]<0) for x in oi_values):p["derivatives"]+=4
    if ls is not None and ((direction=="LONG" and ls>1.2) or (direction=="SHORT" and ls<0.8)):p["derivatives"]+=3
    p["smart_money_onchain"]=max(0,min(5,int(smart_points)))
    p["entry_risk"]+=min(5,max(0,int(entry_points)))
    if risk_ok:p["entry_risk"]+=10
    if independent_ok:p["independent_confirmation"]+=5
    return sum(p.values()),p

def init_signal_db():
    with store.db_connection() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS signal_scans(scan_id TEXT PRIMARY KEY,scanned_at TEXT NOT NULL,result_json TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS signal_records(signal_id TEXT PRIMARY KEY,scan_id TEXT NOT NULL REFERENCES signal_scans(scan_id),
          symbol TEXT NOT NULL,direction TEXT NOT NULL,decision TEXT NOT NULL,entry REAL,stop_loss REAL,take_profit REAL,entry_ts_ms INTEGER,
          confidence INTEGER NOT NULL,data_grade TEXT NOT NULL,outcome TEXT NOT NULL DEFAULT 'OPEN',outcome_at TEXT,outcome_price REAL,realized_r REAL,data_json TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_signal_records_outcome ON signal_records(outcome,decision)")
        c.execute("""CREATE TABLE IF NOT EXISTS signal_market_snapshots(base TEXT NOT NULL,observed_at_ms INTEGER NOT NULL,open_interest_usd REAL NOT NULL,PRIMARY KEY(base,observed_at_ms))""")

def oi_change_1h(base,now_ms):
    init_signal_db()
    with store.db_connection() as c:
        r=c.execute("SELECT open_interest_usd FROM signal_market_snapshots WHERE base=? AND observed_at_ms BETWEEN ? AND ? ORDER BY observed_at_ms DESC LIMIT 1",
          (base,now_ms-75*60_000,now_ms-45*60_000)).fetchone()
    return r[0] if r else None

def save_market_snapshot(base,asof_ms,oi):
    if oi is None or oi<=0:return
    with store.db_connection() as c:c.execute("INSERT OR IGNORE INTO signal_market_snapshots VALUES(?,?,?)",(base,asof_ms,oi))

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
        d=json.loads(r["data_json"]);z=d.get("risk",{})
        if z.get("reward_to_risk") is not None:rr.append(float(z["reward_to_risk"]))
        if d.get("stop_pct") is not None:returns.append(float(r["realized_r"])*float(d["stop_pct"]))
    def segment(key_fn):
        groups={}
        for r in rows:groups.setdefault(key_fn(r),[]).append(r)
        out={}
        for k,rs in groups.items():
            vs=[float(x["realized_r"]) for x in rs if x["outcome"] in {"TP1","STOP_LOSS"} and x["realized_r"] is not None]
            w=[x for x in vs if x>0];l=[x for x in vs if x<0]
            out[str(k)]={"published":len(rs),"closed":len(vs),"win_rate_pct":len(w)/len(vs)*100 if vs else None,
              "expectancy_r":sum(vs)/len(vs) if vs else None,"profit_factor":sum(w)/abs(sum(l)) if l else ("undefined_no_losses" if w else None)}
        return out
    def conf(r):
        n=int(r["confidence"]);return "<60" if n<60 else "60-69" if n<70 else "70-79" if n<80 else "80-89" if n<90 else "90-100"
    def tf(r):
        try:return json.loads(r["data_json"]).get("primary_timeframe","1h")
        except Exception:return "unknown"
    return {"mode":"paper_signal_tracking_not_executed_trades","published_actionable":len(rows),"closed_observations":len(closed),
      "tp1_count":sum(r["outcome"]=="TP1" for r in rows),"stop_loss_count":sum(r["outcome"]=="STOP_LOSS" for r in rows),
      "open_count":sum(r["outcome"]=="OPEN" for r in rows),"win_rate_pct":len(wins)/len(closed)*100 if closed else None,
      "loss_rate_pct":len(loss)/len(closed)*100 if closed else None,"average_reward_to_risk":sum(rr)/len(rr) if rr else None,
      "average_realized_return_pct_of_notional":sum(returns)/len(returns) if returns else None,"average_realized_r":sum(vals)/len(vals) if vals else None,
      "expectancy_r":sum(vals)/len(vals) if vals else None,"profit_factor":sum(wins)/abs(sum(loss)) if loss else ("undefined_no_losses" if wins else None),
      "max_drawdown_r":dd,"by_asset":segment(lambda r:r["symbol"]),"by_timeframe":segment(tf),
      "by_decision":segment(lambda r:r["decision"]),"by_data_grade":segment(lambda r:r["data_grade"]),"by_confidence_range":segment(conf)}

def render_output(r):
    if r.get("status")=="DATA_UNAVAILABLE":return "DATA UNAVAILABLE — do not trade today."
    fmt=lambda x:"—" if x is None else format(float(x),".10g")
    out=[];rows=r.get("actionable",[]);watch=r.get("conditional",[])
    if rows:
        out += ["| Symbol | Decision | Direction | Entry | Stop-Loss | Take-Profit | Stop % | Qty (base) | Contracts ref. | Leverage | Risk USD | Data Grade | Confidence |","|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|"]
        for x in rows:
            z=x["risk"];out.append(f"| {x['symbol']} | {x['decision']} | {x['direction']} | {fmt(x['entry'])} | {fmt(x['stop_loss'])} | {fmt(x['take_profit'])} | {fmt(x['stop_pct'])}% | {fmt(z['quantity_base'])} | {fmt(z['quantity_contracts_reference'])} | {fmt(z['required_leverage'])}x | {fmt(z['planned_loss_usd'])} | {x['data_grade']} | {x['confidence_v5']} |")
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
        now=self.clock();coins=self.p.discover();perps=self.p.perps_assets();whales=self.p.whales()
        asof=_iso_ms(perps.get("asOf"))
        if not asof or now-asof>900_000 or asof>now+60_000:raise DataError("optimistfi_perps_snapshot_stale")
        pmap={x.get("base","").upper():x for x in perps["data"] if x.get("assetClass")=="crypto" and x.get("base")}
        counts={}
        for x in coins:counts[x["symbol"]]=counts.get(x["symbol"],0)+1
        eligible=[]
        for x in coins:
            s=x["symbol"];p=pmap.get(s)
            if s in STABLES or s in WRAPPED or counts[s]>1 or not x["id"] or not p:continue
            if not p.get("price") or not p.get("openInterestUsd") or not p.get("volume24hUsd"):continue
            eligible.append((x,p))
        cap=100 if extended else max(1,min(limit,100));selected=eligible[:cap];candidates=[]
        for coin,perp in selected:
            try:
                pool=self.p.pool_for(coin)
                oi_old=oi_change_1h(perp["base"],asof)
                candidates.append(self.evaluate(coin,perp,pool,whales,asof,now,oi_old))
            except (DataError,CandleError,ValueError,TypeError,KeyError) as e:
                candidates.append({"symbol":perp["base"]+"-PERP","asset":coin["id"],"decision":"INSUFFICIENT_DATA","direction":None,"data_grade":"FAIL","confidence_v5":0,"v3_score":None,"reason":f"mandatory_data_error:{type(e).__name__}"})
            save_market_snapshot(perp["base"],asof,perp.get("openInterestUsd"))
        actionable=sorted([x for x in candidates if x["decision"] in {"BUY_NOW","SELL_NOW"}],key=lambda x:(-x["confidence_v5"],-x.get("risk",{}).get("reward_to_risk",0)))[:10]
        conditional=sorted([x for x in candidates if x["decision"] in {"CONDITIONAL_BUY","CONDITIONAL_SELL"}],key=lambda x:-x["confidence_v5"])
        return {"scan_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),"scanned_at":datetime.now(timezone.utc).isoformat(),
          "universe_requested":cap,"eligible_assets":len(eligible),"screened_assets":len(selected),"partial_scan":cap>=30 and len(selected)<30,
          "source_status":{"discovery":"CoinGecko public API","perpetuals":"OptimistFi Perps Data API","ohlcv":"GeckoTerminal DEX spot OHLCV",
            "account_connection":False,"exchange_api_credentials":False,"order_execution":False},
          "actionable":actionable,"conditional":conditional,"other_candidates":[x for x in candidates if x["decision"] not in {"BUY_NOW","SELL_NOW","CONDITIONAL_BUY","CONDITIONAL_SELL"}],
          "coverage":{"total_candidates":len(candidates),"insufficient_data":sum(x["decision"]=="INSUFFICIENT_DATA" for x in candidates),"rejected":sum(x["decision"]=="REJECT" for x in candidates),"wait":sum(x["decision"]=="WAIT" for x in candidates)}}
    def evaluate(self,coin,perp,pool,whales,asof,now,oi_old):
        price=float(perp["price"])
        if perp.get("priceDispersionBps") is None:raise DataError("missing_cross_venue_price_dispersion")
        disp=float(perp["priceDispersionBps"])
        if price<=0 or disp>100:raise DataError("invalid_price_or_cross_venue_dispersion_over_100bps")
        mins={"15m":210,"1h":210,"4h":210,"1d":100}
        cs={tf:validate_candles(self.p.candles(pool,tf,260),iv,now,mins[tf]) for tf,iv in INTERVALS.items()}
        spot=cs["15m"][-1].close;basis=(price/spot-1)*10000
        if abs(basis)>100:raise DataError("spot_futures_basis_over_100bps")
        one=cs["1h"];cl=[x.close for x in one];rv=rsi(cl)[-1];e20=ema(cl,20)[-1];e50=ema(cl,50)[-1];a14=atr(one)[-1];vr=volume_ratio(one)
        if None in (rv,e20,e50,a14,vr):raise DataError("mandatory_indicator_missing")
        trends={"1d":_trend(cs["1d"],True),"4h":_trend(cs["4h"]),"1h":_trend(one)}
        hourly=float(perp["fundingRateHourly"]);fund=hourly*8
        long=rv<35 and vr>1.2 and one[-1].close>e20 and trends["4h"] in {"UP","FLAT"} and abs(fund)<.0005
        short=rv>65 and vr>1.2 and one[-1].close<e20 and trends["4h"] in {"DOWN","FLAT"} and abs(fund)<.0005
        if not long and not short:return {"symbol":perp["base"]+"-PERP","asset":coin["id"],"decision":"REJECT","direction":None,"data_grade":"B","confidence_v5":0,"v3_score":None,"reason":"mandatory_v3_baseline_not_satisfied","technical":{"rsi14":rv,"volume_ratio":vr},"trends":trends}
        d="LONG" if long else "SHORT"
        oi_change=((float(perp["openInterestUsd"])/oi_old)-1)*100 if oi_old and oi_old>0 else None
        venues=perp.get("venues",[])
        long_oi=sum(float(v.get("openInterestLongUsd") or 0) for v in venues)
        short_oi=sum(float(v.get("openInterestShortUsd") or 0) for v in venues)
        ls=long_oi/short_oi if long_oi>0 and short_oi>0 else None
        required=(4/(1.5*a14/price))/200
        contract_venues=[v for v in venues if float(v.get("maxLeverage") or 0)>0 and float(v.get("contractMultiplier") or 0)>0]
        if not contract_venues:raise DataError("missing_verified_venue_multiplier_or_leverage")
        eligible_venues=[v for v in contract_venues if float(v.get("maxLeverage") or 0)>=required]
        venue=max(eligible_venues or contract_venues,key=lambda v:float(v.get("openInterestUsd") or 0))
        mult=float(venue["contractMultiplier"]);venue_lev=float(venue["maxLeverage"])
        ml,ms,mh=macd_parts(cl);macd_ok=mh[-1] is not None and mh[-2] is not None and ((mh[-1]>0 and mh[-1]>=mh[-2]) if d=="LONG" else (mh[-1]<0 and mh[-1]<=mh[-2]))
        bl,bm,bu=bollinger(cl);sr=stoch_rsi(cl)
        tech={"rsi":rv,"ema20":e20,"ema50":e50,"ema200":ema(cl,200)[-1],"atr14":a14,"volume_ratio":vr,"close":one[-1].close,
          "macd":ml[-1],"macd_signal":ms[-1],"macd_histogram":mh[-1],"bollinger_lower":bl[-1],"bollinger_mid":bm[-1],
          "bollinger_upper":bu[-1],"stoch_rsi":sr[-1],"macd_aligned":macd_ok,"price_change":(cl[-1]/cl[-2]-1)*100}
        st=_structure(cs["4h"],d);risk=risk_calc(d,price,a14,mult,venue_lev)
        e15=ema([x.close for x in cs["15m"]],20)[-1];last=cs["15m"][-1];prev=cs["15m"][-2]
        entry_ok=e15 is not None and ((d=="LONG" and last.close>e15 and last.close>=prev.close) or (d=="SHORT" and last.close<e15 and last.close<=prev.close))
        independent=abs(basis)<=50
        score,parts=_score(d,tech,trends,st,oi_change,ls,fund,entry_ok,risk["valid"],independent)
        v3=50+(10 if (rv<30 if d=="LONG" else rv>70) else 0)+(10 if vr>1.5 else 0)+(10 if trends["4h"]==("UP" if d=="LONG" else "DOWN") else 0)+(10 if ((one[-1].close>e20 and one[-1].close>e50) if d=="LONG" else (one[-1].close<e20 and one[-1].close<e50)) else 0)+(10 if ((d=="LONG" and fund<0) or (d=="SHORT" and fund>0)) else 0)
        conflict=trends["1d"] not in {"NEUTRAL","BULLISH" if d=="LONG" else "BEARISH"}
        if not risk["valid"]:decision="REJECT"
        elif score>=70 and entry_ok and not conflict:decision="BUY_NOW" if d=="LONG" else "SELL_NOW"
        elif score>=60 and (not entry_ok or conflict):decision="CONDITIONAL_BUY" if d=="LONG" else "CONDITIONAL_SELL"
        else:decision="WAIT"
        confirm=None;trigger=None
        if decision.startswith("CONDITIONAL"):
            if not entry_ok:
                confirm="15m DEX close above EMA20 and not below prior close" if d=="LONG" else "15m DEX close below EMA20 and not above prior close"
                trigger=max(e15,prev.close) if d=="LONG" else min(e15,prev.close)
            else:confirm="daily regime realigns with setup"
        flow=self._whale_flow(whales,perp["base"],d)
        return {"symbol":perp["base"]+"-PERP","asset":coin["id"],"primary_timeframe":"1h","decision":decision,"direction":d,
          "entry_type":"OptimistFi_oi_weighted_perps_mark_price","entry":price,"entry_observed_at_ms":asof,
          "stop_loss":risk["stop_loss"],"take_profit":risk["take_profit"],"stop_pct":risk["stop_pct"],"risk":risk,
          "data_grade":"B","confidence_v5":score,"v5_score_components":parts,"v3_score":v3,"technical":tech,"trends":trends,"structure":st,
          "derivatives":{"funding_rate_hourly":hourly,"funding_rate_8h_equivalent":fund,"open_interest_usd":perp["openInterestUsd"],
            "open_interest_change_1h_pct":oi_change,"global_long_short_ratio_if_published":ls,"price_dispersion_bps":disp},
          "independent_confirmation":{"spot_price_usd":spot,"perps_mark_price_usd":price,"basis_bps":basis,"passed":independent},
          "large_taker_flow_last_hour":flow,"reference_venue":venue.get("venue"),"contract_multiplier":mult,
          "pool":{"network":pool["network"],"address":pool["address"],"token_side":pool["token_side"],"reserve_usd":pool["reserve_usd"],"name":pool["pool_name"]},
          "confirmation_required":confirm,"trigger_level":trigger,
          "limitations":["Technical OHLCV is DEX spot data, not futures-contract candles; the futures mark price is separately sourced from OptimistFi.","Smart-money wallet identity/on-chain holdings are unavailable; no Smart Money points awarded. Large taker trades are a separate unscored observation.","Contract lot step and minimum quantity are not published by the aggregator; contract quantity is a reference only.","Fees, spread, slippage and liquidation mechanics are excluded.","No account connection, credentials or order execution."]}
    @staticmethod
    def _whale_flow(whales,base,direction):
        trades=[t for t in whales.get("trades",[]) if t.get("base")==base and t.get("side") in {"buy","sell"} and isinstance(t.get("notionalUsd"),(int,float))]
        if not trades:return {"available":False,"buy_usd":None,"sell_usd":None,"net_buy_usd":None,"aligned":None,"wallet_identity_available":False}
        buy=sum(float(t["notionalUsd"]) for t in trades if t["side"]=="buy")
        sell=sum(float(t["notionalUsd"]) for t in trades if t["side"]=="sell")
        net=buy-sell
        return {"available":True,"buy_usd":buy,"sell_usd":sell,"net_buy_usd":net,"aligned":(net>0 if direction=="LONG" else net<0),"wallet_identity_available":False}
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
            try:
                d=json.loads(row["data_json"]);pool=d["pool"];cs=validate_candles(p.candles(pool,"15m",1000),900_000,int(time.time()*1000),1)
            except (DataError,CandleError,KeyError,ValueError):continue
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
        return {"checked":checked,"newly_closed":closed,"ambiguous_same_candle":ambiguous,"performance":performance(),"note":"Outcomes are spot-DEX proxy observations, not futures-contract fills. Same-candle stop/target touches remain UNKNOWN; no intrabar sequence is assumed."}
    finally:p.close()
