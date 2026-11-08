#!/usr/bin/env python3
"""Stage 1 CLI. Run --probe-only first from the target network."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_layer.collector import Stage1Collector, MS_DAY


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--probe-only",action="store_true")
    parser.add_argument("--symbols",type=int,default=100)
    parser.add_argument("--years",type=int,default=2)
    parser.add_argument("--data-dir",default="data/stage1")
    parser.add_argument("--provider",choices=["binance","okx"],default="okx")
    args=parser.parse_args()
    collector=Stage1Collector(data_dir=args.data_dir,provider=args.provider)
    try:
        if args.probe_only:
            result={"binance":collector.probe_binance(),"bybit":collector.probe_bybit(),"okx":collector.probe_okx(),"fear_greed":collector.probe_fear_greed()}
            if args.provider == "okx":
                try:
                    cutoff = int(time.time()*1000) - int(args.years*365.25*MS_DAY)
                    universe = collector.discover_symbols(args.symbols, min_listing_ms=cutoff)
                    result["ccxt_universe"] = {"selected_count":len(universe),"requested_count":args.symbols,
                                               "sample_symbols":universe[:12],"passed":len(universe)>=args.symbols}
                except Exception as exc:
                    result["ccxt_universe"] = {"passed":False,"error":type(exc).__name__,
                                               "detail":str(exc)[:180]}
            out=Path(args.data_dir)
            out.mkdir(parents=True,exist_ok=True)
            (out/"endpoint_probe.json").write_text(
                json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
        else:
            result=collector.run(target_count=args.symbols,years=args.years)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if args.probe_only and ((not result["binance"]["passed"] and not result["okx"]["passed"]) or not result["fear_greed"]["passed"] or (args.provider == "okx" and not result.get("ccxt_universe",{}).get("passed",False))):
            raise SystemExit(2)
        if not args.probe_only and (result["failed_symbols"] or result["fear_greed"]["error"]):
            raise SystemExit(3)
    finally:
        collector.close()


if __name__=="__main__":
    main()
