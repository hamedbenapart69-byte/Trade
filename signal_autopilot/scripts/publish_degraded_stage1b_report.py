"""Publish an explicit MARKET_DATA_DEGRADED snapshot after scanner failure."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_ROOT = str(Path(__file__).resolve().parent)
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from publish_stage1b_dashboard import _load_universe, publish_dashboard

DECISION_POLICY = "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW"
ALLOWED_FAILURES = {"failure", "timed_out", "startup_failure"}


def build_degraded_source(
    universe_path: Path,
    generated_at_utc: str,
    run_id: str,
    conclusion: str,
) -> dict[str, Any]:
    if conclusion not in ALLOWED_FAILURES:
        raise ValueError("SCANNER_FAILURE_CONCLUSION_INVALID")
    expected_symbols = _load_universe(universe_path)
    if not expected_symbols:
        raise ValueError("UNIVERSE_EMPTY")
    reason = f"SCANNER_WORKFLOW_FAILED:{conclusion}"
    rows = []
    for symbol in expected_symbols:
        rows.append({
            "symbol": symbol,
            "mode": "PRODUCTION",
            "decision": "NO_TRADE",
            "veto": "DATA_WORKFLOW_FAILED",
            "reason": reason,
            "direction": None,
            "tier": None,
            "entry": None,
            "stop_loss": None,
            "take_profit_1": None,
            "take_profit": None,
            "rr": None,
            "hypothesis": "UNAVAILABLE",
            "falsification": "UNAVAILABLE",
            "confidence": "NOT_CALIBRATED",
            "lfs_score": None,
            "lfs_status": "UNAVAILABLE",
            "lfs_coverage_pct": None,
            "cvd": {"source": "UNAVAILABLE"},
            "higher_timeframe_bias": {
                "4h_kumo": "UNAVAILABLE",
                "1h_kijun": "UNAVAILABLE",
            },
            "rows_available": 0,
            "stats_1h_rows_available": 0,
            "last_closed_candle_utc": None,
            "data_sources": ["UNAVAILABLE"],
        })
    return {
        "generated_at_utc": generated_at_utc,
        "stage": "STAGE_1_UNCALIBRATED",
        "engine": "LRT-15m",
        "production_watchlist_count": 0,
        "research_candidate_count": 0,
        "universe_count": len(expected_symbols),
        "symbols_reported": len(rows),
        "symbols": rows,
        "calibration": "UNCALIBRATED",
        "ev_status": "NOT_CALCULATED",
        "decision_policy": DECISION_POLICY,
        "data_gate_status": "NOT_REPORTED",
        "report_status": "MARKET_DATA_DEGRADED",
        "failure_reason": reason,
        "upstream_run_id": str(run_id),
        "upstream_conclusion": conclusion,
        "data_sources": ["UNAVAILABLE"],
        "cvd_sources": ["UNAVAILABLE"],
    }


def publish_degraded_report(
    universe_path: Path,
    output_dir: Path,
    generated_at_utc: str,
    run_id: str,
    conclusion: str,
) -> dict[str, Any]:
    source = build_degraded_source(universe_path, generated_at_utc, run_id, conclusion)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".degraded-stage1b-", dir=str(output_dir.parent)) as tmp:
        report_path = Path(tmp) / "stage1_lrt_report.json"
        report_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = publish_dashboard(report_path, universe_path, output_dir)
    result["report_status"] = "MARKET_DATA_DEGRADED"
    result["upstream_run_id"] = str(run_id)
    result["upstream_conclusion"] = conclusion
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--conclusion", required=True, choices=sorted(ALLOWED_FAILURES))
    args = parser.parse_args()
    result = publish_degraded_report(
        args.universe,
        args.output_dir,
        args.generated_at,
        args.run_id,
        args.conclusion,
    )
    print("STAGE1B_DEGRADED_PUBLICATION " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
