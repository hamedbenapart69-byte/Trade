"""V5 read-only futures signal engine using CoinGecko discovery and a selected public futures provider."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from math import sqrt
import json, time, uuid, os
import httpx
from fastapi import APIRouter, HTTPException, Query
from app import store

CG="https://api.coingecko.com/api/v3"
STABLES={"USDT","USDC","DAI","BUSD","TUSD","FDUSD","USDE","USDS","USDD","FRAX","USDP","PYUSD","USTC","LUSD","GUSD","EURC","EURS","USD1","USDJ"}
WRAPPED={"WBTC","WETH","STETH","WSTETH","CBBTC","BTCB","WBETH","BETH","WBNB","RENBTC","TBTC"}
INTERVALS={"15m":900_000,"1h":3_600_000,"4h":14_400_000,"1d":86_400_000}

class DataError(RuntimeError):pass
class CandleError(ValueError):pass

@dataclass(frozen=True)
class Candle:
    open_time:int;open:float;high:float;low:float;close:float;volume:float;close_time:int;is_final:bool=True;taker_buy_quote_volume:float|None=None

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
        if c.close_time!=c.open_time+interval-1:raise CandleError("candle_close_time_mismatch")
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
      "capital_assumption_usd":capital,"risk_cap_usd":risk_usd,"contract_quantity_note":"Base-unit estimate only; apply verified venue contract rules before publication."}

class PublicMarketData:
    """TraderSpy read-only REST adapter. Requires a free data-provider key, never an exchange key."""
    BASE="https://api.traderspy.app/v1"
    MAX_RUN_CALLS=190
    DAILY_APP_BUDGET=240
    def __init__(self,client:httpx.Client|None=None,api_key:str|None=None):
        self.client=client or httpx.Client(timeout=25,follow_redirects=False);self.own=client is None
        self.api_key=api_key if api_key is not None else os.getenv("TRADERSPY_API_KEY")
        self.last_call=0.0;self.calls=0
    def _ts_get(self,path,params=None):
        if not self.api_key:raise DataError("TRADERSPY_API_KEY_NOT_CONFIGURED")
        if self.calls>=self.MAX_RUN_CALLS:raise DataError("traderspy_run_call_budget_reached")
        reserve_traderspy_api_call(self.DAILY_APP_BUDGET)
        self.calls+=1
        wait=6.1-(time.monotonic()-self.last_call)
        if wait>0:time.sleep(wait)
        self.last_call=time.monotonic()
        try:
            r=self.client.get(self.BASE+path,params=params,headers={"Authorization":"Bearer "+self.api_key,"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"})
            if r.status_code==401:raise DataError("traderspy_api_key_invalid_or_unauthorized")
            if r.status_code==403:raise DataError("traderspy_free_plan_or_ip_restriction")
            if r.status_code==429:raise DataError("traderspy_rate_or_daily_limit_reached")
            r.raise_for_status();return r.json()
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
    def contract_specs(self,symbols):
        """Read public USDⓈ-M exchange metadata; no account credentials or trading endpoints."""
        # Try the documented USDⓈ-M endpoint first, then Binance's numbered
        # futures hosts as a connectivity fallback. Every payload is schema-checked.
        hosts=("fapi.binance.com","fapi1.binance.com","fapi2.binance.com","fapi3.binance.com","fapi4.binance.com")
        failures=[]
        payload=None
        for host in hosts:
            try:
                r=self.client.get(f"https://{host}/fapi/v1/exchangeInfo",
                    headers={"Accept":"application/json","User-Agent":"FuturesSignalAutopilot/5.0"},
                    follow_redirects=True)
                r.raise_for_status()
                candidate=r.json()
                if not isinstance(candidate,dict) or not isinstance(candidate.get("symbols"),list):
                    raise ValueError("invalid_exchange_metadata_schema")
                payload=candidate
                break
            except (httpx.HTTPError,ValueError,TypeError) as e:
                status=getattr(getattr(e,"response",None),"status_code",None)
                failures.append(f"{host}:{'http_'+str(status) if status is not None else type(e).__name__}")
        if payload is None:
            # Safe diagnostic codes only; never include request headers or API keys.
            raise DataError("public_futures_contract_metadata_unavailable:"+";".join(failures))
        requested={str(x).upper() for x in symbols};out={}
        for item in payload.get("symbols",[]):
            sym=str(item.get("symbol","")).upper()
            if sym not in requested:continue
            if item.get("contractType")!="PERPETUAL" or item.get("status")!="TRADING":continue
            if item.get("quoteAsset")!="USDT" or item.get("marginAsset")!="USDT":continue
            if str(item.get("pair","")).upper()!=sym or (str(item.get("baseAsset","")).upper()+"USDT")!=sym:continue
            filters={x.get("filterType"):x for x in item.get("filters",[]) if isinstance(x,dict)}
            price_filter=filters.get("PRICE_FILTER",{});lot=filters.get("LOT_SIZE",{})
            notional=filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
            try:
                tick=float(price_filter.get("tickSize") or 0);step=float(lot.get("stepSize") or 0)
                min_qty=float(lot.get("minQty") or 0);min_notional=float(notional.get("minNotional") or notional.get("notional") or 0)
            except (TypeError,ValueError):continue
            if min(tick,step,min_qty,min_notional)<=0:continue
            out[sym]={"symbol":sym,"pair":item.get("pair"),"contract_type":item.get("contractType"),
              "status":item.get("status"),"base_asset":item.get("baseAsset"),"quote_asset":item.get("quoteAsset"),
              "margin_asset":item.get("marginAsset"),"quantity_unit":"base_asset","tick_size":tick,
              "step_size":step,"min_qty":min_qty,"min_notional":min_notional}
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
            return out
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
        return {"traders":traders.get("data",[]),"positions":positions.get("data",[]),"signals":signals.get("data",[]),
          "traders_observed_at_ms":_iso_ms(traders.get("updatedAt") or traders.get("timestamp")),
          "positions_observed_at_ms":_iso_ms(positions.get("updatedAt") or positions.get("timestamp")),
          "signals_observed_at_ms":_iso_ms(signals.get("updatedAt") or signals.get("timestamp"))}
    def close(self):
        if self.own:self.client.close()

def _iso_ms(s):
    if isinstance(s,(int,float)):
        return int(s if s>10_000_000_000 else s*1000)
    try:return int(datetime.fromisoformat(str(s).replace("Z","+00:00")).timestamp()*1000)
    except (ValueError,AttributeError,TypeError):return 0

def funding_rate_per_8h(rate:float,interval_hours:float)->float:
    """Normalize a funding rate to an 8-hour equivalent for comparable filtering."""
    if not isinstance(rate,(int,float)) or not isinstance(interval_hours,(int,float)):
        raise DataError("ambiguous_funding_rate_or_interval")
    if not (rate==rate and abs(rate)!=float("inf")) or not (interval_hours>0 and interval_hours==interval_hours and abs(interval_hours)!=float("inf")):
        raise DataError("ambiguous_funding_rate_or_interval")
    if rate<=-1:
        raise DataError("invalid_funding_rate")
    return (1.0+float(rate))**(8.0/float(interval_hours))-1.0

def contract_sized_risk(direction:str,entry:float,stop:float,contract:dict)->dict:
    """Round venue price/size rules and calculate risk using the verified contract multiplier."""
    from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING, ROUND_DOWN
    tick=Decimal(str(contract["tick_size"]));step=Decimal(str(contract["step_size"]))
    minimum=Decimal(str(contract["min_qty"]));multiplier=Decimal(str(contract.get("contract_multiplier") or 1))
    if min(tick,step,minimum,multiplier)<=0:raise DataError("invalid_contract_tick_step_minimum_or_multiplier")
    def snap(value,mode):
        v=Decimal(str(value));units=(v/tick).to_integral_value(rounding=mode);return float(units*tick)
    en=snap(entry,ROUND_HALF_UP)
    st=snap(stop,ROUND_FLOOR if direction=="LONG" else ROUND_CEILING)
    base=risk_calc(direction,en,st)
    def tp_snap(value):
        return snap(value,ROUND_CEILING if direction=="LONG" else ROUND_FLOOR)
    tp1=tp_snap(base["take_profit"]);tp2=tp_snap(base["take_profit_2"]);tp3=tp_snap(base["take_profit_3"])
    dist=abs(Decimal(str(en))-Decimal(str(st)))
    unit=str(contract.get("quantity_unit") or "base_asset")
    unit_notional=Decimal(str(en))*multiplier if unit=="contracts" else Decimal(str(en))
    qty_raw=Decimal(str(base["max_notional_usd"]))/unit_notional
    qty=(qty_raw/step).to_integral_value(rounding=ROUND_DOWN)*step
    base_qty=qty*multiplier if unit=="contracts" else qty
    notional=base_qty*Decimal(str(en));loss=base_qty*dist
    required=max(Decimal("1"),notional/Decimal("200"))
    rr=abs(Decimal(str(tp1))-Decimal(str(en)))/dist if dist else Decimal("0")
    reason=base.get("reason")
    if reason is None and qty<minimum:reason="minimum_contract_quantity_not_met"
    maximum=Decimal(str(contract.get("max_qty") or 0))
    if reason is None and maximum>0 and qty>maximum:reason="maximum_contract_quantity_exceeded"
    min_notional=Decimal(str(contract.get("min_notional") or 0))
    if reason is None and min_notional>0 and notional<min_notional:reason="minimum_contract_notional_not_met"
    venue_max=5.0
    tiers=contract.get("risk_limits") or []
    for tier in sorted(tiers,key=lambda x:float(x.get("value") or 0)):
        if float(tier.get("value") or 0)>=float(notional):
            venue_max=float(tier.get("max_leverage") or 0);break
    else:
        if tiers:venue_max=float(sorted(tiers,key=lambda x:float(x.get("value") or 0))[-1].get("max_leverage") or 0)
    if reason is None and venue_max<=0:reason="venue_leverage_limit_unverified"
    if reason is None and float(required)>min(5.0,venue_max)+1e-9:reason="rounded_quantity_exceeds_venue_or_user_leverage_cap"
    if reason is None and float(loss)>4.0+1e-9:reason="rounded_quantity_exceeds_risk_cap"
    if reason is None and float(rr)<2.0:reason="tick_rounded_reward_to_risk_below_2"
    spec={k:contract.get(k) for k in ("symbol","venue_symbol","contract_type","status","base_asset","quote_asset","margin_asset","quantity_unit","multiplier_currency","source","min_trade_precision","risk_limits")}
    spec.update({"tick_size":float(tick),"step_size":float(step),"min_qty":float(minimum),
        "max_qty":float(maximum),"min_notional":float(min_notional),"contract_multiplier":float(multiplier),
        "venue_max_leverage":venue_max})
    base.update({"entry":en,"stop_loss":st,"take_profit":tp1,"take_profit_2":tp2,"take_profit_3":tp3,
      "quantity_base":float(base_qty),"quantity_contracts_reference":float(qty) if unit=="contracts" else None,
      "contract_multiplier_reference":float(multiplier),"quantity_unit":unit,
      "notional_usd":float(notional),"planned_loss_usd":float(loss),"required_leverage":float(required),
      "reward_to_risk":float(rr),"valid":reason is None,"reason":reason,"contract_spec_verified":True,
      "margin_mode_assumption":"ISOLATED; select manually in Toobit; scanner does not change margin mode",
      "planned_loss_excludes_fees_slippage_funding_and_execution_gaps":True,
      "contract_spec":spec,"contract_quantity_note":"Quantity rounded using the venue's published lot step and contract multiplier."})
    return base

def adx(cs:list[Candle],n:int=14)->list[float|None]:
    out=[None]*len(cs)
    if len(cs)<2*n+1:return out
    tr=[0.0];plus=[0.0];minus=[0.0]
    for i in range(1,len(cs)):
        up=cs[i].high-cs[i-1].high;dn=cs[i-1].low-cs[i].low
        plus.append(up if up>dn and up>0 else 0.0);minus.append(dn if dn>up and dn>0 else 0.0)
        tr.append(max(cs[i].high-cs[i].low,abs(cs[i].high-cs[i-1].close),abs(cs[i].low-cs[i-1].close)))
    atr_s=sum(tr[1:n+1]);p_s=sum(plus[1:n+1]);m_s=sum(minus[1:n+1]);dx=[]
    for i in range(n,len(cs)):
        if i>n:atr_s=atr_s-atr_s/n+tr[i];p_s=p_s-p_s/n+plus[i];m_s=m_s-m_s/n+minus[i]
        pdi=100*p_s/atr_s if atr_s else 0;mdi=100*m_s/atr_s if atr_s else 0
        dx.append(100*abs(pdi-mdi)/(pdi+mdi) if pdi+mdi else 0)
    if len(dx)<n:return out
    x=sum(dx[:n])/n;out[2*n-1]=x
    for j in range(n,len(dx)):x=(x*(n-1)+dx[j])/n;out[n+j]=x
    return out

def obv(cs:list[Candle])->list[float]:
    out=[0.0]*len(cs)
    for i in range(1,len(cs)):
        out[i]=out[i-1]+(cs[i].volume if cs[i].close>cs[i-1].close else -cs[i].volume if cs[i].close<cs[i-1].close else 0)
    return out

def mfi(cs:list[Candle],n:int=14)->list[float|None]:
    out=[None]*len(cs)
    if len(cs)<=n:return out
    pos=[];neg=[]
    for i,c in enumerate(cs):
        tp=(c.high+c.low+c.close)/3
        if i==0:pos.append(0.0);neg.append(0.0);continue
        prev=(cs[i-1].high+cs[i-1].low+cs[i-1].close)/3;flow=tp*c.volume
        pos.append(flow if tp>prev else 0.0);neg.append(flow if tp<prev else 0.0)
    for i in range(n,len(cs)):
        p=sum(pos[i-n+1:i+1]);q=sum(neg[i-n+1:i+1])
        out[i]=100.0 if q==0 else 100-100/(1+p/q)
    return out

def volatility_regime(cs:list[Candle],n:int=14)->str:
    av=atr(cs,n);valid=[x/c.close*100 for x,c in zip(av,cs) if x is not None and c.close>0]
    if len(valid)<30:return "UNKNOWN"
    current=valid[-1];rank=sum(x<=current for x in valid[-100:])/len(valid[-100:])
    return "HIGH" if rank>=.8 else "LOW" if rank<=.2 else "NORMAL"

def _trend(cs,daily=False):
    v=[x.close for x in cs];a=ema(v,20)[-1];b=ema(v,50)[-1]
    if a is None or b is None:return "UNKNOWN"
    if v[-1]>a>b:return "BULLISH" if daily else "UP"
    if v[-1]<a<b:return "BEARISH" if daily else "DOWN"
    return "NEUTRAL" if daily else "FLAT"

def _structure(cs,direction,atr_value=None):
    hp=[];lp=[]
    for i in range(2,len(cs)-2):
        w=cs[i-2:i+3];c=cs[i]
        if c.high>max(x.high for j,x in enumerate(w) if j!=2):hp.append((i,c.high))
        if c.low<min(x.low for j,x in enumerate(w) if j!=2):lp.append((i,c.low))
    if len(hp)<2 or len(lp)<2:return {"classification":"UNKNOWN","bos":False,"choch":False,"last_swing_high":None,"last_swing_low":None,
      "fvg_aligned":False,"order_block_aligned":False,"liquidity_sweep_aligned":False,"liquidity_levels":[]}
    ph,lh=hp[-1][1],lp[-1][1];hh=ph>hp[-2][1];hl=lh>lp[-2][1];lhh=ph<hp[-2][1];ll=lh<lp[-2][1]
    cls="BULLISH" if hh and hl else "BEARISH" if lhh and ll else "MIXED"
    bos=cs[-1].close>ph if direction=="LONG" else cs[-1].close<lh
    choch=(cls=="BEARISH" and direction=="LONG" and bos) or (cls=="BULLISH" and direction=="SHORT" and bos)
    sweep_long=cs[-1].low<lh and cs[-1].close>lh
    sweep_short=cs[-1].high>ph and cs[-1].close<ph
    fvg_bull=cs[-1].low>cs[-3].high
    fvg_bear=cs[-1].high<cs[-3].low
    ob=None
    if bos:
        for x in reversed(cs[-12:-1]):
            if (direction=="LONG" and x.close<x.open) or (direction=="SHORT" and x.close>x.open):
                ob={"low":x.low,"high":x.high,"type":"BULLISH" if direction=="LONG" else "BEARISH"};break
    tol=(atr_value or (cs[-1].high-cs[-1].low))*.25
    levels=[]
    for idx,val in hp[-12:]:
        if sum(1 for _,v in hp[-12:] if abs(v-val)<=tol)>=2:levels.append({"type":"RESISTANCE","price":val})
    for idx,val in lp[-12:]:
        if sum(1 for _,v in lp[-12:] if abs(v-val)<=tol)>=2:levels.append({"type":"SUPPORT","price":val})
    return {"classification":cls,"bos":bos,"choch":choch,"last_swing_high":ph,"last_swing_low":lh,
      "fvg_aligned":fvg_bull if direction=="LONG" else fvg_bear,"fvg_bullish":fvg_bull,"fvg_bearish":fvg_bear,
      "order_block":ob,"order_block_aligned":bool(ob),"liquidity_sweep_aligned":sweep_long if direction=="LONG" else sweep_short,
      "liquidity_sweep_bullish":sweep_long,"liquidity_sweep_bearish":sweep_short,"liquidity_levels":levels}

def _score(direction,tech,trends,structure,oi1h,oi4h,oi24h,ls,taker,funding,entry_points,risk_ok,smart_points,independent_ok):
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
    oi_values=[x for x in (oi1h,oi4h,oi24h) if x is not None]
    if oi_values and any((x>0 and tech["price_change"]>0) if direction=="LONG" else (x>0 and tech["price_change"]<0) for x in oi_values):p["derivatives"]+=4
    if ls is not None and ((direction=="LONG" and ls<0.8) or (direction=="SHORT" and ls>1.2)):p["derivatives"]+=2
    if taker is not None and ((direction=="LONG" and taker>1.05) or (direction=="SHORT" and taker<0.95)):p["derivatives"]+=1
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
        c.execute("""CREATE TABLE IF NOT EXISTS traderspy_api_usage(day_utc TEXT PRIMARY KEY,calls INTEGER NOT NULL DEFAULT 0)""")

def traderspy_daily_usage():
    init_signal_db();day=datetime.now(timezone.utc).date().isoformat()
    with store.db_connection() as c:
        r=c.execute("SELECT calls FROM traderspy_api_usage WHERE day_utc=?",(day,)).fetchone()
    return int(r[0]) if r else 0

def reserve_traderspy_api_call(daily_budget=240):
    init_signal_db();day=datetime.now(timezone.utc).date().isoformat()
    with store.db_connection() as c:
        r=c.execute("SELECT calls FROM traderspy_api_usage WHERE day_utc=?",(day,)).fetchone()
        used=int(r[0]) if r else 0
        if used>=daily_budget:raise DataError("traderspy_local_daily_budget_guard_reached")
        c.execute("INSERT INTO traderspy_api_usage(day_utc,calls) VALUES(?,1) ON CONFLICT(day_utc) DO UPDATE SET calls=calls+1",(day,))
        return used+1

def oi_change_1h(base,now_ms):
    init_signal_db()
    with store.db_connection() as c:
        r=c.execute("SELECT open_interest_usd FROM signal_market_snapshots WHERE base=? AND observed_at_ms BETWEEN ? AND ? ORDER BY observed_at_ms DESC LIMIT 1",
          (base,now_ms-75*60_000,now_ms-45*60_000)).fetchone()
    return r[0] if r else None

def save_market_snapshot(base,asof_ms,oi):
    if oi is None or oi<=0 or not asof_ms:return
    with store.db_connection() as c:
        c.execute("INSERT OR IGNORE INTO signal_market_snapshots VALUES(?,?,?)",(base,asof_ms,oi))
        c.execute("DELETE FROM signal_market_snapshots WHERE observed_at_ms<?",(asof_ms-7*24*60*60_000,))

def save_scan(result):
    init_signal_db();published=result.get("actionable",[])+result.get("conditional",[]);saved=0
    with store.db_connection() as c:
        c.execute("INSERT OR REPLACE INTO signal_scans VALUES(?,?,?)",(result["scan_id"],result["scanned_at"],json.dumps(result,ensure_ascii=False)))
        for x in published:
            c.execute("""INSERT INTO signal_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (str(uuid.uuid4()),result["scan_id"],x["symbol"],x.get("direction") or "UNKNOWN",x["decision"],x.get("entry"),x.get("stop_loss"),x.get("take_profit"),x.get("entry_observed_at_ms"),int(x.get("confidence_v5",0)),x.get("data_grade","FAIL"),"WATCH" if x["decision"].startswith("CONDITIONAL") else "OPEN",None,None,None,json.dumps(x,ensure_ascii=False)))
            saved+=1
        # Keep the latest scan and every scan referenced by a published signal; discard empty scan history.
        c.execute("DELETE FROM signal_scans WHERE scan_id<>? AND scan_id NOT IN (SELECT DISTINCT scan_id FROM signal_records)",(result["scan_id"],))
    result["persistence"]={"published_records_saved":saved}
    result["performance"]=performance()
    with store.db_connection() as c:
        c.execute("UPDATE signal_scans SET result_json=? WHERE scan_id=?",(json.dumps(result,ensure_ascii=False),result["scan_id"]))
    return result["persistence"]

def latest_scan():
    init_signal_db()
    with store.db_connection() as c:r=c.execute("SELECT result_json FROM signal_scans ORDER BY scanned_at DESC LIMIT 1").fetchone()
    return json.loads(r[0]) if r else None

def performance():
    init_signal_db()
    with store.db_connection() as c:
        rows=c.execute("SELECT symbol,decision,data_grade,confidence,outcome,realized_r,data_json FROM signal_records WHERE decision IN ('BUY_NOW','SELL_NOW','CONDITIONAL_BUY','CONDITIONAL_SELL') ORDER BY rowid").fetchall()
        latest=c.execute("SELECT result_json FROM signal_scans ORDER BY scanned_at DESC LIMIT 1").fetchone()
    provider_name="configured public futures provider"
    if latest:
        try:provider_name=(json.loads(latest[0]).get("source_status") or {}).get("futures_ohlcv") or provider_name
        except (ValueError,TypeError):pass
    closed=[r for r in rows if r["outcome"] in {"TP1","TP2","TP3","STOP_LOSS"} and r["realized_r"] is not None]
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
            vs=[float(x["realized_r"]) for x in rs if x["outcome"] in {"TP1","TP2","TP3","STOP_LOSS"} and x["realized_r"] is not None]
            w=[x for x in vs if x>0];l=[x for x in vs if x<0]
            out[str(k)]={"published":len(rs),"closed":len(vs),"win_rate_pct":len(w)/len(vs)*100 if vs else None,
              "expectancy_r":sum(vs)/len(vs) if vs else None,"profit_factor":sum(w)/abs(sum(l)) if l else ("undefined_no_losses" if w else None)}
        return out
    def conf(r):
        n=int(r["confidence"]);return "<60" if n<60 else "60-69" if n<70 else "70-79" if n<80 else "80-89" if n<90 else "90-100"
    def tf(r):
        try:return json.loads(r["data_json"]).get("primary_timeframe","1h")
        except Exception:return "unknown"
    return {"mode":"paper_signal_tracking_not_executed_trades","outcome_source":f"{provider_name} OHLCV; no exchange fills are observed",
      "published_signals":len(rows),"closed_observations":len(closed),"tp1_count":sum(r["outcome"]=="TP1" for r in rows),
      "tp2_count":sum(r["outcome"]=="TP2" for r in rows),"tp3_count":sum(r["outcome"]=="TP3" for r in rows),
      "stop_loss_count":sum(r["outcome"]=="STOP_LOSS" for r in rows),"expired_count":sum(r["outcome"]=="EXPIRED" for r in rows),
      "no_valid_entry_count":sum(r["outcome"]=="NO_VALID_ENTRY" for r in rows),"unknown_count":sum(r["outcome"]=="UNKNOWN" for r in rows),
      "watch_count":sum(r["outcome"]=="WATCH" for r in rows),"open_count":sum(r["outcome"]=="OPEN" for r in rows),
      "win_rate_pct":len(wins)/len(closed)*100 if closed else None,"loss_rate_pct":len(loss)/len(closed)*100 if closed else None,
      "average_reward_to_risk":sum(rr)/len(rr) if rr else None,"average_realized_return_pct_of_notional":sum(returns)/len(returns) if returns else None,
      "average_realized_r":sum(vals)/len(vals) if vals else None,"expectancy_r":sum(vals)/len(vals) if vals else None,
      "profit_factor":sum(wins)/abs(sum(loss)) if loss else ("undefined_no_losses" if wins else None),"max_drawdown_r":dd,
      "by_asset":segment(lambda r:r["symbol"]),"by_timeframe":segment(tf),"by_decision":segment(lambda r:r["decision"]),
      "by_data_grade":segment(lambda r:r["data_grade"]),"by_confidence_range":segment(conf)}

def render_output(r):
    if r.get("status")=="DATA_UNAVAILABLE":return "No qualifying signals today."
    fmt=lambda x:"—" if x is None else format(float(x),".10g")
    rows=r.get("actionable",[])[:10]
    if not rows:return "No qualifying signals today."
    out=["| Rank | Symbol | Side | Entry | Stop Loss | TP1 | TP2 | TP3 | Leverage (≤5x) | Position Notional (USD) | Planned Risk (USD) | Timeframe | Confidence/Source |",
      "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for rank,x in enumerate(rows,1):
        z=x["risk"];spec=z.get("contract_spec") or {}
        symbol=spec.get("venue_symbol") or x["symbol"]
        source_name=str(spec.get("source") or "public futures data")
        source_link="[Toobit API](https://api-docs.toobit.com/api/usdt-m-market-data)" if source_name.startswith("Toobit") else source_name
        source=" / ".join([str(x.get("data_grade") or "—"),source_link,"isolated sizing assumption","targets calculated"])
        out.append(f"| {rank} | {symbol} | {x['direction']} | {fmt(x['entry'])} | {fmt(x['stop_loss'])} | {fmt(x['take_profit'])} | {fmt(x.get('take_profit_2'))} | {fmt(x.get('take_profit_3'))} | {fmt(z['required_leverage'])}x | {fmt(z['notional_usd'])} | {fmt(z['planned_loss_usd'])} | {x.get('primary_timeframe') or '1h'} | {source} |")
    return "\n".join(out)

class FuturesSignalEngine:
    def __init__(self,provider=None,clock=None):
        self.p=provider or PublicMarketData();self.own=provider is None;self.clock=clock or (lambda:int(time.time()*1000))
    def scan(self,extended=False,limit=30):
        now=self.clock()
        coins=self.p.discover()
        tracked=self.p.tracked_symbols()
        symbols_for_specs=[str(x["symbol"]).upper()+"USDT" for x in coins if str(x.get("symbol","")).upper()+"USDT" in tracked]
        contracts=self.p.contract_specs(symbols_for_specs)
        counts={}
        for x in coins:counts[x["symbol"]]=counts.get(x["symbol"],0)+1
        eligible=[]
        for x in coins:
            s=x["symbol"]
            name=str(x.get("name") or "").lower()
            if not s or not x["id"] or counts[s]>1 or s in STABLES or s in WRAPPED:continue
            if "wrapped" in name or any(k in name for k in ("leveraged","3x long","3x short","5x long","5x short")):continue
            if any(s.endswith(z) for z in ("UP","DOWN","BULL","BEAR","3L","3S","5L","5S")):continue
            sym=s+"USDT"
            if sym not in tracked:continue
            eligible.append((x,sym))
        requested=100 if extended else max(1,min(limit,30))
        cap=requested
        ranker=getattr(self.p,"rank_symbols_by_volume",None)
        if callable(ranker):eligible=ranker(eligible)
        selected=eligible[:cap]
        if not selected:raise DataError("no_coin_gecko_assets_match_public_usdt_perpetual_universe")
        symbols=[s for _,s in selected]
        prices=self.p.prices(symbols)
        derivatives=self.p.derivatives(symbols)
        try:smart=self.p.smart_money()
        except DataError:smart={"traders":[],"positions":[],"signals":[],"traders_observed_at_ms":0,"positions_observed_at_ms":0,"signals_observed_at_ms":0}
        candidates=[]
        for coin,symbol in selected:
            try:
                d=derivatives.get(symbol);p=prices.get(symbol);contract=contracts.get(symbol)
                if not d or not p:raise DataError("missing_live_price_or_derivatives")
                if not contract:raise DataError("missing_verified_perpetual_contract_specs")
                if contract.get("base_asset")!=str(coin.get("symbol","")).upper() or contract.get("quote_asset")!="USDT" or contract.get("margin_asset")!="USDT":
                    raise DataError("underlying_quote_or_margin_asset_mismatch")
                candles={tf:self.p.candles(symbol,tf,220) for tf in INTERVALS}
                if candles.get("1h") and candles["1h"][-1].taker_buy_quote_volume is not None:
                    total=float(candles["1h"][-1].volume);buy=float(candles["1h"][-1].taker_buy_quote_volume)
                    if 0<buy<total:d.setdefault("positioning",{})["takerBuySellRatio"]=buy/(total-buy)
                oi_old=oi_change_1h(symbol, _iso_ms(d.get("updatedAt")))
                result=self.evaluate(coin,symbol,candles,d,p,smart,now,oi_old,contract)
                candidates.append(result)
                save_market_snapshot(symbol,_iso_ms(d.get("updatedAt")),float((d.get("openInterest") or {}).get("valueUsd") or 0))
            except (DataError,CandleError,ValueError,TypeError,KeyError) as e:
                candidates.append({"symbol":symbol,"asset":coin["id"],"decision":"INSUFFICIENT_DATA","direction":None,
                  "data_grade":"FAIL","confidence_v5":0,"v3_score":None,"reason":f"mandatory_data_error:{type(e).__name__}:{str(e)[:120]}"})
        screened=sum(x["decision"]!="INSUFFICIENT_DATA" for x in candidates)
        actionable=sorted([x for x in candidates if x["decision"] in {"BUY_NOW","SELL_NOW"}],
          key=lambda x:(-x["confidence_v5"],0 if x["data_grade"]=="A" else 1,not x.get("entry_quality",{}).get("entry_ok",False),
            -x.get("risk",{}).get("reward_to_risk",0),-x.get("v5_score_components",{}).get("multi_timeframe",0),
            not x.get("independent_confirmation",{}).get("passed",False)))[:10]
        conditional=sorted([x for x in candidates if x["decision"] in {"CONDITIONAL_BUY","CONDITIONAL_SELL"}],key=lambda x:-x["confidence_v5"])
        return {"scan_id":datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),"scanned_at":datetime.now(timezone.utc).isoformat(),
          "universe_requested":requested,"eligible_assets":len(eligible),"selected_assets":len(selected),"screened_assets":screened,
          "partial_scan":screened<30,"extended_partial":bool(extended and len(selected)<min(100,len(eligible))),
          "api_calls_used":self.p.calls,"api_calls_used_today":traderspy_daily_usage() if getattr(self.p,"provider_name","")=="TraderSpy read-only market-data API" else None,
          "api_app_daily_budget":240 if getattr(self.p,"provider_name","")=="TraderSpy read-only market-data API" else None,
          "api_plan_limit_daily":300 if getattr(self.p,"provider_name","")=="TraderSpy read-only market-data API" else None,
          "api_plan_rate_limit_per_minute":10 if getattr(self.p,"provider_name","")=="TraderSpy read-only market-data API" else None,
          "source_status":{"discovery":"CoinGecko public API","futures_ohlcv":getattr(self.p,"provider_name","unknown"),
            "derivatives":getattr(self.p,"provider_name","unknown"),"smart_money":"not supplied by selected market-data adapter",
            "underlying_market_data":"CoinGecko public spot price cross-checked against selected futures index price",
            "account_connection":False,"exchange_api_credentials":False,"order_execution":False},
          "actionable":actionable,"conditional":conditional,
          "other_candidates":[x for x in candidates if x["decision"] not in {"BUY_NOW","SELL_NOW","CONDITIONAL_BUY","CONDITIONAL_SELL"}],
          "coverage":{"total_candidates":len(candidates),"screened":screened,"insufficient_data":sum(x["decision"]=="INSUFFICIENT_DATA" for x in candidates),
            "rejected":sum(x["decision"]=="REJECT" for x in candidates),"wait":sum(x["decision"]=="WAIT" for x in candidates)}}
    def evaluate(self,coin,symbol,candles,deriv,price,smart,now,oi_old,contract):
        du=_iso_ms(deriv.get("updatedAt"));pu=_iso_ms(price.get("updatedAt"))
        if not du or not pu or now-du>900_000 or now-pu>900_000 or du>now+60_000 or pu>now+60_000:
            raise DataError("stale_or_future_dated_live_futures_snapshot")
        mark=float(deriv.get("markPrice") or 0);index=float(deriv.get("indexPrice") or 0);last_price=float(price.get("price") or 0)
        if min(mark,index,last_price)<=0:raise DataError("missing_verified_futures_mark_index_or_last_price")
        if abs(mark/last_price-1)*10000>100:raise DataError("futures_mark_last_trade_basis_over_100bps")
        cg_price=float(coin.get("current_price") or 0)
        if cg_price<=0:raise DataError("missing_independent_coingecko_spot_reference")
        basis=(index/cg_price-1)*10000
        if abs(basis)>100:raise DataError("futures_index_vs_independent_spot_conflict_over_100bps")
        independent=abs(basis)<=50
        mins={"15m":210,"1h":210,"4h":210,"1d":200}
        cs={tf:validate_candles(candles[tf],iv,now,mins[tf]) for tf,iv in INTERVALS.items()}
        one=cs["1h"];cl=[x.close for x in one];rv=rsi(cl)[-1];e20=ema(cl,20)[-1];e50=ema(cl,50)[-1];e200=ema(cl,200)[-1]
        a14=atr(one)[-1];vr=volume_ratio(one)
        if None in (rv,e20,e50,a14,vr):raise DataError("mandatory_1h_indicator_missing")
        trends={"1d":_trend(cs["1d"],True),"4h":_trend(cs["4h"]),"1h":_trend(one)}
        funding_obj=deriv.get("funding") or {};funding=float(funding_obj.get("rate")) if funding_obj.get("rate") is not None else None
        interval_hours=float(funding_obj.get("intervalHours") or 0)
        oi_obj=deriv.get("openInterest") or {};oi=float(oi_obj.get("valueUsd") or 0)
        if funding is None or interval_hours<=0 or oi<=0:raise DataError("missing_funding_interval_or_open_interest")
        if oi_old and oi_old>0:oi1h=(oi/oi_old-1)*100
        else:oi1h=None
        oi4h=float(oi_obj["change4hPct"]) if oi_obj.get("change4hPct") is not None else None
        oi24h=float(oi_obj["change24hPct"]) if oi_obj.get("change24hPct") is not None else None
        positioning=deriv.get("positioning") or {}
        ls=float(positioning["globalLongShortRatio"]) if positioning.get("globalLongShortRatio") is not None else None
        top_ls=float(positioning["topTraderLongShortRatio"]) if positioning.get("topTraderLongShortRatio") is not None else None
        taker=float(positioning["takerBuySellRatio"]) if positioning.get("takerBuySellRatio") is not None else None
        funding_8h=funding_rate_per_8h(funding,interval_hours)
        if abs(funding_8h)>=.0005:
            return {"symbol":symbol,"asset":coin["id"],"decision":"REJECT","direction":None,"data_grade":"B","confidence_v5":0,"v3_score":None,
              "reason":"V3_funding_threshold_failed","derivatives":{"funding_rate":funding,"funding_interval_hours":interval_hours,"funding_rate_8h_equivalent":funding_8h}}
        ml,ms,mh=macd_parts(cl);macd_ok=mh[-1] is not None and mh[-2] is not None and ((mh[-1]>0 and mh[-1]>=mh[-2]) or (mh[-1]<0 and mh[-1]<=mh[-2]))
        bl,bm,bu=bollinger(cl);sr=stoch_rsi(cl);ad=adx(one)[-1];ov=obv(one);mf=mfi(one)[-1]
        bbpos="lower_band" if cl[-1]<=bl[-1] else "lower_half" if cl[-1]<bm[-1] else "upper_band" if cl[-1]>=bu[-1] else "upper_half"
        long=rv<35 and vr>1.2 and cl[-1]>e20 and trends["4h"] in {"UP","FLAT"}
        short=rv>65 and vr>1.2 and cl[-1]<e20 and trends["4h"] in {"DOWN","FLAT"}
        if not long and not short:
            return {"symbol":symbol,"asset":coin["id"],"decision":"REJECT","direction":None,"data_grade":"B","confidence_v5":0,"v3_score":None,
              "reason":"mandatory_V3_baseline_not_satisfied","technical":{"rsi14":rv,"volume_ratio":vr,"ema20":e20,"ema50":e50},"trends":trends}
        direction="LONG" if long else "SHORT"
        price_change=float(oi_obj.get("priceChange24hPct") or 0)
        tech={"rsi":rv,"ema20":e20,"ema50":e50,"ema200":e200,"atr14":a14,"volume_ratio":vr,"close":cl[-1],
          "macd":ml[-1],"macd_signal":ms[-1],"macd_histogram":mh[-1],"bollinger_lower":bl[-1],"bollinger_mid":bm[-1],
          "bollinger_upper":bu[-1],"bb_position":bbpos,"stoch_rsi":sr[-1],"adx":ad,"obv":ov[-1],
          "obv_aligned":(ov[-1]>ov[-10] if direction=="LONG" else ov[-1]<ov[-10]),
          "mfi":mf,"mfi_aligned":(mf>=50 if direction=="LONG" else mf<=50),
          "macd_aligned":((mh[-1]>0 and mh[-1]>=mh[-2]) if direction=="LONG" else (mh[-1]<0 and mh[-1]<=mh[-2])),
          "price_change":price_change}
        st=_structure(cs["4h"],direction,a14)
        atr_stop=last_price-1.5*a14 if direction=="LONG" else last_price+1.5*a14
        structural=None
        if direction=="LONG" and st.get("last_swing_low"):structural=st["last_swing_low"]-.2*a14
        if direction=="SHORT" and st.get("last_swing_high"):structural=st["last_swing_high"]+.2*a14
        stop=atr_stop
        if structural and ((direction=="LONG" and structural<last_price) or (direction=="SHORT" and structural>last_price)):
            sp=abs(last_price-structural)/last_price*100
            if .5<=sp<=3 and abs(last_price-structural)>=1.0*a14:stop=structural
        risk=contract_sized_risk(direction,last_price,stop,contract)
        if getattr(self.p,"provider_name","").startswith("Toobit"):
            if float(price.get("quoteVolume24h") or 0)<100000:raise DataError("toobit_24h_quote_volume_below_100000_usd")
            if float(price.get("spreadBps") or 99999)>30:raise DataError("toobit_orderbook_spread_above_30_bps")
            required_depth=max(500.0,2.0*float(risk.get("notional_usd") or 0))
            if float(price.get("bidDepthUsd") or 0)<required_depth or float(price.get("askDepthUsd") or 0)<required_depth:
                raise DataError("toobit_orderbook_depth_below_two_times_position_notional_or_500_usd")
        # Add higher targets only when a verified swing/liquidity level leaves room beyond TP1.
        levels=st.get("liquidity_levels",[])
        if direction=="LONG":
            resist=sorted([x["price"] for x in levels if x["type"]=="RESISTANCE" and x["price"]>risk["take_profit"]])
            risk["take_profit_2"]=min(risk["take_profit_2"],resist[0]) if resist and resist[0]>risk["take_profit"] else None
            risk["take_profit_3"]=min(risk["take_profit_3"],resist[1]) if len(resist)>1 and resist[1]>(risk["take_profit_2"] or risk["take_profit"]) else None
        else:
            supports=sorted([x["price"] for x in levels if x["type"]=="SUPPORT" and x["price"]<risk["take_profit"]],reverse=True)
            risk["take_profit_2"]=max(risk["take_profit_2"],supports[0]) if supports and supports[0]<risk["take_profit"] else None
            risk["take_profit_3"]=max(risk["take_profit_3"],supports[1]) if len(supports)>1 and supports[1]<(risk["take_profit_2"] or risk["take_profit"]) else None
        cs15=cs["15m"];v15=[x.close for x in cs15];e15=ema(v15,20)[-1];atr15=atr(cs15)[-1];last=cs15[-1];prev=cs15[-2]
        if e15 is None or atr15 is None:raise DataError("missing_15m_entry_indicators")
        distance_atr=abs(last_price-e15)/atr15 if atr15>0 else 999
        chase=distance_atr>2.0
        entry_ok=(last_price>e15 and last.close>=prev.close) if direction=="LONG" else (last_price<e15 and last.close<=prev.close)
        entry_ok=entry_ok and not chase
        sweep=st.get("liquidity_sweep_aligned",False)
        if sweep:entry_type="LIQUIDITY_SWEEP"
        elif st.get("bos") and abs(last_price-e15)<=.75*atr15:entry_type="BREAKOUT_RETEST"
        elif abs(last_price-e15)<=.5*atr15:entry_type="PULLBACK"
        else:entry_type="MARKET"
        entry_points=(2 if entry_type in {"LIQUIDITY_SWEEP","BREAKOUT_RETEST"} else 1 if entry_type=="PULLBACK" else 0)+(2 if not chase else 0)+(1 if entry_ok else 0)
        smart_points=self._smart_score(symbol,direction,top_ls,smart,now)
        score,parts=_score(direction,tech,trends,st,oi1h,oi4h,oi24h,ls,taker,funding,entry_points,risk["valid"],smart_points,independent)
        v3=50+(10 if (rv<30 if direction=="LONG" else rv>70) else 0)+(10 if vr>1.5 else 0)+(10 if trends["4h"]==("UP" if direction=="LONG" else "DOWN") else 0)+(10 if ((cl[-1]>e20 and cl[-1]>e50) if direction=="LONG" else (cl[-1]<e20 and cl[-1]<e50)) else 0)+(10 if ((direction=="LONG" and funding<0) or (direction=="SHORT" and funding>0)) else 0)
        conflict=trends["1d"] not in {"NEUTRAL","BULLISH" if direction=="LONG" else "BEARISH"}
        grade="B" if independent else "C"
        ai=self._ai_support(symbol,direction,smart.get("signals",[]),now)
        ai["provider_observed_at_ms"]=smart.get("signals_observed_at_ms")
        is_toobit=getattr(self.p,"provider_name","").startswith("Toobit")
        depth_required=max(500.0,2.0*float(risk.get("notional_usd") or 0))
        audit={"contract_identity_type_status_and_specifications_verified":bool(contract and contract.get("contract_type")=="PERPETUAL" and contract.get("status")=="TRADING"),
          "venue_quantity_precision_and_minimum_verified":bool(contract and contract.get("tick_size") and contract.get("step_size") and contract.get("min_qty")),
          "venue_risk_limit_tier_verified":bool(not is_toobit or contract.get("risk_limits") and risk.get("contract_spec",{}).get("venue_max_leverage")),
          "toobit_quote_volume_gate_passed":bool(not is_toobit or float(price.get("quoteVolume24h") or 0)>=100000),
          "toobit_spread_gate_passed":bool(not is_toobit or float(price.get("spreadBps") or 99999)<=30),
          "toobit_bid_ask_depth_gate_passed":bool(not is_toobit or float(price.get("bidDepthUsd") or 0)>=depth_required and float(price.get("askDepthUsd") or 0)>=depth_required),
          "mark_price_valid":True,"index_price_valid":True,"last_trade_price_valid":True,
          "live_price_and_derivatives_timestamps_fresh":True,"ohlcv_15m_validated":True,"ohlcv_1h_validated":True,
          "ohlcv_4h_validated":True,"ohlcv_1d_validated":True,"completed_candles_only":True,"v3_baseline_passed":True,
          "funding_rate_verified":True,"funding_interval_verified":True,"funding_threshold_passed":abs(funding_8h)<.0005,"funding_rate_8h_equivalent":funding_8h,
          "current_open_interest_verified":oi>0,"oi_changes_recorded_where_available":True,"multi_timeframe_checked":True,
          "market_structure_checked":True,"volume_and_momentum_checked":True,"anti_chase_checked":True,
          "stop_distance_0_5_to_3_pct":.5<=risk["stop_pct"]<=3,"planned_loss_at_most_4_usd":risk["planned_loss_usd"]<=4+1e-9,
          "planned_loss_excludes_fees_slippage_funding_and_execution_gaps":True,
          "isolated_margin_is_manual_assumption_only":True,
          "leverage_at_most_5x":risk["required_leverage"]<=5,"reward_to_risk_at_least_2":risk["reward_to_risk"]>=2,
          "independent_confirmation_and_grade_verified":independent and grade in {"A","B"}}
        audit_passed=all(audit.values())
        if not risk["valid"]:decision="REJECT"
        elif not audit_passed:decision="WAIT"
        elif score>=70 and entry_ok and not conflict:decision="BUY_NOW" if direction=="LONG" else "SELL_NOW"
        elif score>=60 and (not entry_ok or conflict or chase):decision="CONDITIONAL_BUY" if direction=="LONG" else "CONDITIONAL_SELL"
        else:decision="WAIT"
        confirm=None;trigger=None
        if decision.startswith("CONDITIONAL"):
            if chase:confirm="15m pullback toward EMA20; do not chase beyond 2 ATR";trigger=e15
            elif not entry_ok:
                confirm="15m close confirms direction relative to EMA20 and prior candle"
                trigger=max(e15,prev.close) if direction=="LONG" else min(e15,prev.close)
            else:confirm="daily regime realigns with setup"
        return {"symbol":symbol,"asset":coin["id"],"primary_timeframe":"1h","decision":decision,"direction":direction,
          "entry_type":entry_type,"entry":risk["entry"],"entry_observed_at_ms":pu,"stop_loss":risk["stop_loss"],"take_profit":risk["take_profit"],
          "take_profit_2":risk["take_profit_2"],"take_profit_3":risk["take_profit_3"],"stop_pct":risk["stop_pct"],"risk":risk,
          "data_grade":grade,"confidence_v5":score,"v5_score_components":parts,"v3_score":v3,"technical":tech,"trends":trends,
          "structure":st,"volatility_regime":volatility_regime(one),"derivatives":{"funding_rate":funding,"funding_interval_hours":interval_hours,
            "open_interest_usd":oi,"open_interest_change_1h_pct":oi1h,"open_interest_change_4h_pct":oi4h,"open_interest_change_24h_pct":oi24h,
            "price_change_24h_pct":price_change,"global_long_short_ratio":ls,"top_trader_long_short_ratio":top_ls,
            "taker_buy_sell_ratio":taker,"liquidation_regime":oi_obj.get("regime"),"source":deriv.get("source")},
          "independent_confirmation":{"coingecko_spot_price_usd":cg_price,"futures_index_price_usd":index,"basis_bps":basis,"passed":independent},
          "smart_money":{"score_points":smart_points,"top_trader_ratio":top_ls,"top_traders_observed_at_ms":smart.get("traders_observed_at_ms"),
            "positions_observed_at_ms":smart.get("positions_observed_at_ms"),"open_positions":self._position_evidence(symbol,direction,smart),
            "ai_signal_support":ai},"entry_quality":{"entry_ok":entry_ok,"chase":chase,"distance_from_15m_ema20_atr":distance_atr,
            "entry_points":entry_points,"confirmation_required":confirm,"trigger_level":trigger},
          "expires_at_ms":pu+24*60*60_000,"self_audit":audit,"self_audit_count":len(audit),"self_audit_passed":audit_passed,
          "limitations":["Selected public futures provider is used read-only; no exchange account or trading credentials are used.",
            "The selected provider does not currently supply verified orderbook spread, exact fees, slippage, venue liquidation price, or on-chain wallet identity.",
            "Optional smart-money and top-trader evidence is absent unless the selected provider explicitly returns it.",
            "Paper outcomes use public OHLCV candles, not exchange fills; simulated observations are not executed-trade performance."]}
    @staticmethod
    def _position_evidence(symbol,direction,smart):
        out=[]
        for p in smart.get("positions",[]):
            if str(p.get("symbol","")).upper()!=symbol:continue
            side=str(p.get("side","")).upper()
            if side in {"LONG","SHORT"}:out.append({"side":side,"trader_id":p.get("traderId") or p.get("trader_id"),"size_usd":p.get("sizeUsd") or p.get("notionalUsd")})
        return out
    @classmethod
    def _smart_score(cls,symbol,direction,top_ratio,smart,now):
        points=3 if top_ratio is not None and ((direction=="LONG" and top_ratio>1.2) or (direction=="SHORT" and top_ratio<.8)) else 0
        observed=smart.get("positions_observed_at_ms")
        aligned=cls._position_evidence(symbol,direction,smart) if observed and 0<=now-observed<=900_000 else []
        traders={str(t.get("traderId") or t.get("trader_id")):float(t.get("smartScore") or t.get("score") or 0) for t in smart.get("traders",[]) if t.get("traderId") or t.get("trader_id")}
        qualified={x["trader_id"] for x in aligned if x["trader_id"] and traders.get(str(x["trader_id"]),0)>=70 and x["side"]==direction}
        if len(qualified)>=2:points+=2
        elif len(qualified)==1:points+=1
        return min(points,5)
    @staticmethod
    def _ai_support(symbol,direction,signals,now):
        for s in signals:
            if str(s.get("symbol","")).upper()!=symbol:continue
            d=str(s.get("direction") or s.get("signal") or "").upper()
            conf=s.get("confidence")
            ts=_iso_ms(s.get("createdAt") or s.get("timestamp") or s.get("created_at"))
            if d in {direction,"BUY" if direction=="LONG" else "SELL"} and isinstance(conf,(int,float)) and conf>60 and ts and 0<=now-ts<=900_000:
                return {"available":True,"confidence":conf,"direction":direction,"created_at_ms":ts,"supporting_only":True}
        return {"available":False,"supporting_only":True}
    def close(self):
        if self.own:self.p.close()

def create_provider():
    """Select a read-only public market-data provider; Toobit is the free default."""
    selected=os.getenv("V5_DATA_PROVIDER","toobit").strip().lower()
    if selected=="toobit":
        from app.integrations.toobit_market import ToobitPublicMarketData
        return ToobitPublicMarketData()
    if selected=="okx":
        from app.integrations.okx_market import OkxPublicMarketData
        return OkxPublicMarketData()
    if selected=="traderspy":
        return PublicMarketData()
    raise DataError("unsupported_v5_data_provider")

router=APIRouter(tags=["futures-signals"])
@router.get("/signals/status")
def get_signal_status():
    selected=os.getenv("V5_DATA_PROVIDER","toobit").strip().lower()
    scan=latest_scan()
    if selected in {"okx","toobit"}:
        context=(scan or {}).get("validation_context") or {}
        source=(scan or {}).get("source_status") or {}
        scanned_ms=_iso_ms((scan or {}).get("scanned_at"))
        age_ms=int(time.time()*1000)-scanned_ms if scanned_ms else None
        screened=int((scan or {}).get("screened_assets") or 0)
        selected_assets=int((scan or {}).get("selected_assets") or 0)
        completed=bool(scan and scan.get("status")=="SCAN_COMPLETED" and context.get("fixture_data") is False
          and source.get("futures_ohlcv") and selected_assets>=30 and screened>=30)
        live_verified=bool(completed and age_ms is not None and 0<=age_ms<=900_000)
        return {"status":"NO_SCAN_YET" if scan is None else scan.get("status","UNKNOWN"),
          "data_provider":source.get("futures_ohlcv","Toobit public read-only linear USDT perpetual API" if selected=="toobit" else "OKX public read-only linear USDT perpetual API"),
          "api_key_required":False,"exchange_account_connection":False,
          "exchange_api_key_required":False,"order_execution_enabled":False,
          "live_rest_access_verified":live_verified,"endpoint_probe_verified":bool(completed),
          "full_live_scan_verified":completed,
          "last_scan_utc":(scan or {}).get("scanned_at"),
          "last_full_live_scan_utc":(scan or {}).get("scanned_at") if completed else None,
          "last_scan_age_minutes":round(age_ms/60000,1) if age_ms is not None and age_ms>=0 else None,
          "last_full_live_scan_age_minutes":round(age_ms/60000,1) if completed and age_ms is not None and age_ms>=0 else None,
          "last_scan_coverage":f"{screened}/{selected_assets}" if scan else None,
          "last_full_live_scan_coverage":f"{screened}/{selected_assets}" if completed else None,
          "last_full_live_scan_actionable_signals":len((scan or {}).get("actionable") or []) if completed else 0,
          "note":"A full live scan requires at least 30 successfully screened assets and verified non-fixture data. Live REST freshness is true only while that scan is no older than 15 minutes."}
    configured=bool(os.getenv("TRADERSPY_API_KEY"))
    return {"status":"KEY_CONFIGURED_UNVERIFIED" if configured else "DATA_UNAVAILABLE",
      "data_provider":"TraderSpy read-only futures market-data API","api_key_configured":configured,
      "api_key_type":"read-only data-provider credential; not an exchange key",
      "free_plan_daily_calls":300,"free_plan_calls_per_minute":10,"app_daily_budget":240,
      "api_calls_used_today":traderspy_daily_usage(),"api_calls_remaining_app_budget":max(0,240-traderspy_daily_usage()),
      "exchange_account_connection":False,"exchange_api_key_required":False,"order_execution_enabled":False,
      "live_rest_access_verified":False,"last_live_verification":None,
      "note":"A configured key is not proof of live reachability; run the manual V5 Live Validation workflow to verify."}
@router.post("/signals/scan")
def run_scan(extended:bool=Query(False),universe_limit:int=Query(30,ge=1,le=100)):
    p=create_provider();e=FuturesSignalEngine(provider=p)
    try:
        prior=evaluate_outcomes_with_provider(p)
        r=e.scan(extended,universe_limit)
        r["status"]="DATA_UNAVAILABLE" if r["screened_assets"]==0 or r["coverage"]["insufficient_data"]==r["screened_assets"] else "SCAN_COMPLETED"
        r["prior_outcome_evaluation"]=prior;r["formatted_output"]=render_output(r);save_scan(r)
        return r
    except DataError as ex:raise HTTPException(503,detail={"status":"INSUFFICIENT_DATA","reason":str(ex),"action":"DATA UNAVAILABLE — do not trade today."}) from ex
    finally:
        e.close();p.close()

@router.get("/signals/latest")
def get_latest():
    r=latest_scan()
    if r is None:raise HTTPException(404,detail="no_scan_recorded")
    return r

@router.get("/signals/performance")
def get_performance():return performance()

def evaluate_outcomes_with_provider(provider=None):
    init_signal_db();checked=closed=ambiguous=expired=no_entry=triggered=0;own=provider is None;p=provider or create_provider()
    try:
        with store.db_connection() as db:
            rows=db.execute("SELECT * FROM signal_records WHERE outcome IN ('OPEN','WATCH') AND decision IN ('BUY_NOW','SELL_NOW','CONDITIONAL_BUY','CONDITIONAL_SELL')").fetchall()
        candles_cache={};now=int(time.time()*1000)
        for row in rows:
            checked+=1
            try:d=json.loads(row["data_json"]);symbol=d["symbol"];expiry=int(d.get("expires_at_ms") or int(row["entry_ts_ms"] or now)+24*60*60_000)
            except (ValueError,TypeError,KeyError):continue
            if row["outcome"]=="WATCH":
                try:
                    key=(symbol,"15m")
                    if key not in candles_cache:candles_cache[key]=validate_candles(p.candles(symbol,"15m",500),INTERVALS["15m"],now,1)
                    cs15=candles_cache[key]
                except (DataError,CandleError,KeyError,ValueError):continue
                trigger=(d.get("entry_quality") or {}).get("trigger_level")
                if trigger is None:
                    if now>expiry:
                        at=datetime.fromtimestamp(expiry/1000,tz=timezone.utc).isoformat()
                        with store.db_connection() as db:db.execute("UPDATE signal_records SET outcome='NO_VALID_ENTRY',outcome_at=? WHERE signal_id=? AND outcome='WATCH'",(at,row["signal_id"]))
                        no_entry+=1
                    continue
                trigger_candle=None
                for candle in cs15:
                    if candle.open_time<int(row["entry_ts_ms"] or 0):continue
                    if candle.open_time>expiry:break
                    if (row["direction"]=="LONG" and candle.close>=float(trigger)) or (row["direction"]=="SHORT" and candle.close<=float(trigger)):
                        trigger_candle=candle;break
                if trigger_candle is None:
                    if now>expiry:
                        at=datetime.fromtimestamp(expiry/1000,tz=timezone.utc).isoformat()
                        with store.db_connection() as db:db.execute("UPDATE signal_records SET outcome='NO_VALID_ENTRY',outcome_at=? WHERE signal_id=? AND outcome='WATCH'",(at,row["signal_id"]))
                        no_entry+=1
                    continue
                try:
                    entry=float(trigger_candle.close);risk=risk_calc(row["direction"],entry,float(row["stop_loss"]))
                except (DataError,ValueError,TypeError):
                    risk={"valid":False,"reason":"conditional_entry_invalidates_original_stop_or_risk"}
                if not risk.get("valid"):
                    d["conditional_entry_rejected"]=risk.get("reason") or "risk_gate_failed"
                    at=datetime.fromtimestamp(trigger_candle.close_time/1000,tz=timezone.utc).isoformat()
                    with store.db_connection() as db:db.execute("UPDATE signal_records SET outcome='NO_VALID_ENTRY',outcome_at=?,data_json=? WHERE signal_id=? AND outcome='WATCH'",(at,json.dumps(d,ensure_ascii=False),row["signal_id"]))
                    no_entry+=1;continue
                d["entry"]=entry;d["entry_observed_at_ms"]=trigger_candle.close_time;d["risk"]=risk
                d["stop_loss"]=risk["stop_loss"];d["take_profit"]=risk["take_profit"];d["take_profit_2"]=risk["take_profit_2"];d["take_profit_3"]=risk["take_profit_3"]
                d.setdefault("entry_quality",{})["triggered"]=True;d["entry_quality"]["triggered_at_ms"]=trigger_candle.close_time
                at=datetime.fromtimestamp(trigger_candle.close_time/1000,tz=timezone.utc).isoformat()
                with store.db_connection() as db:
                    db.execute("UPDATE signal_records SET outcome='OPEN',entry=?,stop_loss=?,take_profit=?,entry_ts_ms=?,data_json=? WHERE signal_id=? AND outcome='WATCH'",
                      (entry,risk["stop_loss"],risk["take_profit"],trigger_candle.close_time,json.dumps(d,ensure_ascii=False),row["signal_id"]))
                triggered+=1
                continue
            try:
                tf=d.get("primary_timeframe","1h");iv=INTERVALS[tf];key=(symbol,tf)
                if key not in candles_cache:candles_cache[key]=validate_candles(p.candles(symbol,tf,500),iv,now,1)
                cs=candles_cache[key]
            except (DataError,CandleError,KeyError,ValueError):continue
            entry_ts=int(row["entry_ts_ms"] or 0);best=None;best_rr=None;best_price=None;best_at=None;outcome=None;rr=None;price=None;at=None
            for candle in cs:
                if candle.open_time<entry_ts:continue
                if candle.open_time>expiry:break
                if row["direction"]=="LONG":
                    sl=candle.low<=row["stop_loss"];t1=candle.high>=row["take_profit"]
                    t2=candle.high>=float(d.get("take_profit_2") or 1e100);t3=candle.high>=float(d.get("take_profit_3") or 1e100)
                else:
                    sl=candle.high>=row["stop_loss"];t1=candle.low<=row["take_profit"]
                    t2=candle.low<=float(d.get("take_profit_2") or -1e100);t3=candle.low<=float(d.get("take_profit_3") or -1e100)
                anytp=t1 or t2 or t3
                if sl and anytp:
                    if best is None:outcome="UNKNOWN";rr=None;price=candle.close;at=datetime.fromtimestamp(candle.close_time/1000,tz=timezone.utc).isoformat();ambiguous+=1
                    else:outcome=best;rr=best_rr;price=best_price;at=best_at
                    break
                if sl:
                    if best is None:outcome="STOP_LOSS";rr=-1.0;price=candle.close;at=datetime.fromtimestamp(candle.close_time/1000,tz=timezone.utc).isoformat()
                    else:outcome=best;rr=best_rr;price=best_price;at=best_at
                    break
                if t3:best="TP3";best_rr=4.0;best_price=candle.close;best_at=datetime.fromtimestamp(candle.close_time/1000,tz=timezone.utc).isoformat();outcome=best;rr=best_rr;price=best_price;at=best_at;break
                if t2:best="TP2";best_rr=3.0;best_price=candle.close;best_at=datetime.fromtimestamp(candle.close_time/1000,tz=timezone.utc).isoformat()
                elif t1 and best is None:best="TP1";best_rr=2.0;best_price=candle.close;best_at=datetime.fromtimestamp(candle.close_time/1000,tz=timezone.utc).isoformat()
            if outcome is None and now>expiry:
                if best is not None:outcome=best;rr=best_rr;price=best_price;at=best_at
                else:outcome="EXPIRED";rr=0.0;price=None;at=datetime.fromtimestamp(expiry/1000,tz=timezone.utc).isoformat();expired+=1
            if outcome:
                with store.db_connection() as db:db.execute("UPDATE signal_records SET outcome=?,outcome_at=?,outcome_price=?,realized_r=? WHERE signal_id=? AND outcome='OPEN'",(outcome,at,price,rr,row["signal_id"]))
                if outcome not in {"UNKNOWN","EXPIRED"}:closed+=1
        return {"checked":checked,"newly_closed":closed,"newly_triggered":triggered,"no_valid_entry":no_entry,"expired":expired,
          "ambiguous_same_candle":ambiguous,"performance":performance(),
          "note":f"Paper observations use {getattr(p, 'provider_name', 'the selected public futures provider')} OHLCV, not exchange fills. TP milestones are tracked in order; if stop and first target occur in the same candle, outcome is UNKNOWN."}
    finally:
        if own:p.close()

@router.post("/signals/evaluate")
def evaluate_outcomes():
    return evaluate_outcomes_with_provider()
