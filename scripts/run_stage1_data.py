#!/usr/bin/env python3
"""Stage 1 CLI. Run --probe-only first from the target network."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.data_layer.collector import Stage1Collector


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--probe-only",action="store_true")
    parser.add_argument("--symbols",type=int,default=100)
    parser.add_argument("--years",type=int,default=2)
    parser.add_argument("--data-dir",default="data/stage1")
    args=parser.parse_args()
    collector=Stage1Collector(data_dir=args.data_dir)
    try:
        if args.probe_only:
            result={"binance":collector.probe_binance(),"bybit":collector.probe_bybit(),"fear_greed":collector.probe_fear_greed(),"data_vision":collector.probe_data_vision()}
            out=Path(args.data_dir)
            out.mkdir(parents=True,exist_ok=True)
            (out/"endpoint_probe.json").write_text(
                json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
        else:
            result=collector.run(target_count=args.symbols,years=args.years)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if args.probe_only and (not result["binance"]["passed"] or not result["fear_greed"]["passed"]):
            raise SystemExit(2)
        if not args.probe_only and (result["failed_symbols"] or result["fear_greed"]["error"]):
            raise SystemExit(3)
    finally:
        collector.close()


if __name__=="__main__":
    main()
