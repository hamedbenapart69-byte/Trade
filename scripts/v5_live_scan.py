"""Expanded live V5 scan using verified public market-data endpoints."""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
from app.signals import FuturesSignalEngine, create_provider, render_output, save_scan, evaluate_outcomes_with_provider


def classify_scan(result: dict) -> str:
    coverage = result.get("coverage") or {}
    total = int(coverage.get("total_candidates") or 0)
    insufficient = int(coverage.get("insufficient_data") or 0)
    screened = int(result.get("screened_assets") or 0)
    if screened <= 0 or (total > 0 and insufficient >= total):
        return "DATA_UNAVAILABLE"
    return "SCAN_COMPLETED"


def main() -> int:
    out = Path("artifacts/v5_live_scan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    provider = None
    engine = None
    try:
        provider = create_provider()
        engine = FuturesSignalEngine(provider=provider)
        prior = evaluate_outcomes_with_provider(provider)
        result = engine.scan(extended=True, limit=100)
        eligible = int(result.get("eligible_assets") or 0)
        selected = int(result.get("selected_assets") or 0)
        result["scan_mode"] = "EXPANDED_TOP_100"
        result["primary_shortlist_target"] = 30
        result["primary_shortlist_selected"] = min(30, selected)
        result["expanded_discovery_target"] = max(0, min(70, eligible - 30))
        result["expanded_discovery_selected"] = max(0, selected - 30)
        result["status"] = classify_scan(result)
        result["prior_outcome_evaluation"] = prior
        result["formatted_output"] = render_output(result)
        result["validation_context"] = {
            "execution": "GitHub-hosted runner",
            "market_data": "live public HTTP endpoints",
            "fixture_data": False,
            "account_connection": False,
            "order_execution": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        save_scan(result)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(result["formatted_output"])
        print(json.dumps({
            "status": result["status"],
            "scan_mode": result["scan_mode"],
            "eligible_assets": eligible,
            "selected_assets": selected,
            "screened_assets": result.get("screened_assets"),
            "coverage": result.get("coverage"),
            "source_status": result.get("source_status"),
        }, ensure_ascii=False))
        return 2 if result["status"] == "DATA_UNAVAILABLE" else 0
    except Exception as exc:
        failure = {
            "status": "INSUFFICIENT_DATA",
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "fixture_data": False,
            "account_connection": False,
            "order_execution": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        out.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print("DATA UNAVAILABLE — do not trade today.")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.close()
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    sys.exit(main())
