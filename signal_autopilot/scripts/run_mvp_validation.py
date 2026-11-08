#!/usr/bin/env python3
"""اجرای گزارش Walk-Forward روی آرشیو Parquet شاخه market-data."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.mvp_validation import run_validation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", default="artifacts/mvp-validation.json")
    args = parser.parse_args()
    report = run_validation(Path(args.data_dir))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "symbols": report["coverage"]["symbols_with_data"],
        "trades": report["oos_metrics"]["trades"],
        "win_rate_pct": report["oos_metrics"]["win_rate_pct"],
        "profit_factor": report["oos_metrics"]["profit_factor"],
        "max_drawdown_pct": report["oos_metrics"]["max_drawdown_pct"],
        "gate_status": report["gate_status"],
        "report": str(output),
    }, ensure_ascii=False))
    return 0 if report["coverage"]["symbols_with_data"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
