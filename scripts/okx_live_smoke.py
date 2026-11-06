from __future__ import annotations
import json,time
from app.signals import FuturesSignalEngine,create_provider,contract_sized_risk

p=create_provider()
try:
    coins=p.discover()
    coin=next(x for x in coins if x["symbol"]=="BTC")
    symbol="BTCUSDT"
    tracked=p.tracked_symbols()
    if symbol not in tracked: raise RuntimeError("BTCUSDT_missing_from_OKX_live_perpetual_universe")
    specs=p.contract_specs([symbol])
    if symbol not in specs: raise RuntimeError("BTCUSDT_contract_metadata_unavailable")
    prices=p.prices([symbol])
    derivatives=p.derivatives([symbol])
    candles={tf:p.candles(symbol,tf,220) for tf in ("15m","1h","4h","1d")}
    now=int(time.time()*1000)
    engine=FuturesSignalEngine(provider=p)
    result=engine.evaluate(coin,symbol,candles,derivatives[symbol],prices[symbol],p.smart_money(),now,None,specs[symbol])
    sizing=contract_sized_risk("LONG",float(derivatives[symbol]["markPrice"]),float(derivatives[symbol]["markPrice"])*0.99,specs[symbol])
    if not sizing.get("contract_spec_verified") or sizing.get("quantity_unit")!="contracts":
        raise RuntimeError("OKX_contract_multiplier_sizing_not_verified")
    print(json.dumps({"status":"SMOKE_TEST_PASSED","provider":p.provider_name,"symbol":symbol,
      "instrument":specs[symbol],"price":prices[symbol],"derivatives":derivatives[symbol],
      "candles":{k:{"count":len(v),"latest_open_ms":v[-1].open_time,"latest_final":v[-1].is_final} for k,v in candles.items()},
      "candidate":{"decision":result["decision"],"confidence_v5":result.get("confidence_v5"),"reason":result.get("reason")},
      "risk_sizing":{"valid":sizing["valid"],"reason":sizing["reason"],"quantity_contracts":sizing["quantity_contracts_reference"],
        "quantity_base":sizing["quantity_base"],"planned_loss_usd":sizing["planned_loss_usd"],"required_leverage":sizing["required_leverage"],
        "reward_to_risk":sizing["reward_to_risk"]},"api_calls":p.calls},indent=2))
finally:
    p.close()
