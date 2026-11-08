#!/usr/bin/env python3
"""Stage 1 CLI. Run --probe-only first from the target network."""
from __future__ import annotations
import argparse, json
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
            result={"binance":collector.probe_binance(),"bybit":collector.probe_bybit()}
        else:
            result=collector.run(target_count=args.symbols,years=args.years)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        if args.probe_only and not result["binance"]["passed"]:
            raise SystemExit(2)
        if not args.probe_only and (result["failed_symbols"] or result["fear_greed"]["error"]):
            raise SystemExit(3)
    finally:
        collector.close()


if __name__=="__main__":
    main()
