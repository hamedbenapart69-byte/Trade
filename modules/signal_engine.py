"""Conservative EMA/funding placeholder. This is not the V8 engine."""
from datetime import datetime, timezone
C10={"BUY_NOW","SELL_NOW","CONDITIONAL_BUY","CONDITIONAL_SELL","WATCHLIST","NO_QUALIFIED_SETUP","MARKET_DATA_DEGRADED"}
FUNDING_EXTREME=0.0005

def ema(values,period):
    if len(values)<period: return []
    alpha=2.0/(period+1.0); out=[sum(values[:period])/period]
    for value in values[period:]: out.append(value*alpha+out[-1]*(1.0-alpha))
    return out

def build_signal(row,generated_at_utc):
    availability=row.get("availability") or {}; candles=row.get("ohlcv") or []
    base={"symbol":row.get("symbol"),"status":"MARKET_DATA_DEGRADED","side":None,"tier":"NONE",
      "entry":None,"stop_loss":None,"take_profit":[],"reason":"Required futures data is missing or insufficient",
      "lfs":"NOT_CALCULABLE (missing order book)","nss":"NOT_CALCULATED",
      "hypothesis":"EMA20/EMA50 + funding placeholder only",
      "falsification":"A completed 1h candle invalidates the EMA cross or funding condition",
      "confidence":"NOT_CALIBRATED","ev_net":"NOT_CALIBRATED","data_availability":availability,
      "order_book":"UNAVAILABLE","liquidation":"UNAVAILABLE","basis":"UNAVAILABLE","generated_at_utc":generated_at_utc}
    if availability.get("ohlcv")!="OK" or availability.get("funding")!="OK" or len(candles)<52:
        base["reason"]="MARKET_DATA_DEGRADED: OHLCV or funding unavailable/insufficient"; return base
    try:
        now=datetime.fromisoformat(generated_at_utc.replace("Z","+00:00")).timestamp()*1000
        candle_age_hours=(now-int(candles[-1]["timestamp"]))/3_600_000
        if candle_age_hours>2:
            base["reason"]="MARKET_DATA_DEGRADED: latest completed 1h candle is "+str(round(candle_age_hours,2))+"h old"; return base
    except (TypeError,ValueError,KeyError):
        base["reason"]="MARKET_DATA_DEGRADED: invalid candle timestamp"; return base
    closes=[float(c["close"]) for c in candles]; fast=ema(closes,20); slow=ema(closes,50)
    if len(fast)<2 or len(slow)<2: return base
    fp,fn,sp,sn=fast[-2],fast[-1],slow[-2],slow[-1]
    funding=float(row["funding_rate"]); bull=fp<=sp and fn>sn; bear=fp>=sp and fn<sn
    if bull and funding<=-FUNDING_EXTREME:
        base.update(status="CONDITIONAL_BUY",side="LONG",tier="PLACEHOLDER",reason="EMA20 crossed above EMA50 with strongly negative funding; manual confirmation required")
    elif bear and funding>=FUNDING_EXTREME:
        base.update(status="CONDITIONAL_SELL",side="SHORT",tier="PLACEHOLDER",reason="EMA20 crossed below EMA50 with strongly positive funding; manual confirmation required")
    elif abs(fn-sn)/max(abs(sn),1e-12)<0.0015:
        base.update(status="WATCHLIST",reason="EMA20 is close to EMA50; no qualified trigger")
    else: base.update(status="NO_QUALIFIED_SETUP",reason="No qualified EMA/funding placeholder setup")
    base.update(ema20=round(fn,10),ema50=round(sn,10),funding_rate=funding)
    return base

def generate_signals(data):
    generated=data.get("generated_at_utc"); rows=data.get("symbols") or []
    signals=[build_signal(row,generated) for row in rows]
    if not signals:
        signals=[{"symbol":"MARKET","status":"MARKET_DATA_DEGRADED","side":None,"tier":"NONE","entry":None,
          "stop_loss":None,"take_profit":[],"reason":"No market data returned",
          "lfs":"NOT_CALCULABLE (missing order book)","nss":"NOT_CALCULATED",
          "confidence":"NOT_CALIBRATED","ev_net":"NOT_CALIBRATED","order_book":"UNAVAILABLE",
          "liquidation":"UNAVAILABLE","basis":"UNAVAILABLE","generated_at_utc":generated}]
    for s in signals:
        if s.get("status") not in C10: raise ValueError("invalid_C10_status:"+str(s.get("status")))
    degraded=any(s["status"]=="MARKET_DATA_DEGRADED" for s in signals)
    return {"schema_version":"1.0","generated_at_utc":generated,"provider":data.get("provider","unknown"),
      "pipeline_status":"DEGRADED" if degraded or data.get("fallback_used") else "OK",
      "engine":"EMA20_EMA50_FUNDING_PLACEHOLDER","is_v8":False,"manual_trade_only":True,
      "fallback_used":bool(data.get("fallback_used")),"primary_error":data.get("primary_error"),
      "data_availability":{"ohlcv":"OK" if signals and all((s.get("data_availability") or {}).get("ohlcv")=="OK" for s in signals) else "DEGRADED",
        "funding":"OK" if signals and all((s.get("data_availability") or {}).get("funding")=="OK" for s in signals) else "DEGRADED",
        "open_interest":"PARTIAL_OR_UNAVAILABLE","open_interest_history_days":30,
        "order_book":"UNAVAILABLE","liquidation":"UNAVAILABLE","basis":"UNAVAILABLE",
        "fear_greed":"OK" if data.get("fear_greed") else "UNAVAILABLE"},
      "fear_greed":data.get("fear_greed"),
      "quality":{"symbols_requested":data.get("symbols_requested",0),"symbols_processed":data.get("symbols_processed",0),
        "symbols_degraded":sum(1 for s in signals if s["status"]=="MARKET_DATA_DEGRADED")},
      "signals":signals}
