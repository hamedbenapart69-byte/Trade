"""Cost-coverage annotations for Stage 1 research outcomes.

All rates in this module are percentage points of notional return, not leveraged ROI.
The project specifies a 0.04% reference fee but does not unambiguously state whether
it is per fill or round trip. Both interpretations are exposed as PROXY scenarios.
Unknown execution costs remain UNAVAILABLE; no scenario is labeled fully net performance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

FEE_REFERENCE_RATE_PCT = 0.04
FEE_MODEL = "PROXY_FEE_BASIS_SENSITIVITY"
CLOSED_FILLED_STATUSES = {"TP_HIT", "SL_HIT", "EXPIRED"}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def annotate_outcome_costs(outcome: dict[str, Any]) -> dict[str, Any]:
    """Return a copied outcome with explicit cost coverage and no fabricated net PnL."""
    result = dict(outcome)
    status = result.get("status")
    filled = result.get("entry_fill_status") == "SIMULATED_FILLED"

    if status == "ENTRY_INVALIDATED_GAP" or result.get("entry_fill_status") == "NOT_FILLED":
        result["cost_accounting"] = {
            "status": "NOT_TRADED",
            "gross_return_pct": None,
            "fee": {"status": "NOT_APPLICABLE", "reason": "NO_SIMULATED_FILL"},
            "spread": {"status": "UNAVAILABLE"},
            "slippage": {"status": "UNAVAILABLE"},
            "funding": {"status": "UNAVAILABLE"},
            "market_impact": {"status": "UNAVAILABLE"},
            "net_return_pct": "UNAVAILABLE",
            "net_ev": "NOT_CALCULATED",
        }
        return result

    if status not in CLOSED_FILLED_STATUSES or not filled:
        result["cost_accounting"] = {
            "status": "PENDING",
            "gross_return_pct": _finite_number(result.get("pnl_pct_raw")),
            "fee": {"status": "PENDING"},
            "spread": {"status": "UNAVAILABLE"},
            "slippage": {"status": "UNAVAILABLE"},
            "funding": {"status": "UNAVAILABLE"},
            "market_impact": {"status": "UNAVAILABLE"},
            "net_return_pct": "UNAVAILABLE",
            "net_ev": "NOT_CALCULATED",
        }
        return result

    gross = _finite_number(result.get("pnl_pct_raw"))
    entry = _finite_number(result.get("entry_actual"))
    exit_price = _finite_number(result.get("exit_price"))
    if gross is None or entry is None or exit_price is None or entry <= 0 or exit_price <= 0:
        result["cost_accounting"] = {
            "status": "INVALID_INPUT",
            "gross_return_pct": gross,
            "fee": {"status": "UNAVAILABLE"},
            "spread": {"status": "UNAVAILABLE"},
            "slippage": {"status": "UNAVAILABLE"},
            "funding": {"status": "UNAVAILABLE"},
            "market_impact": {"status": "UNAVAILABLE"},
            "net_return_pct": "UNAVAILABLE",
            "net_ev": "NOT_CALCULATED",
            "reason": "CLOSED_TRADE_REQUIRES_FINITE_GROSS_RETURN_AND_POSITIVE_FILL_PRICES",
        }
        return result

    # منبع فقط نرخ مرجع ۰٫۰۴٪ را تعیین کرده؛ مبنای هر Fill یا Round-trip مشخص نیست.
    # بنابراین دو سناریو را نشان می‌دهیم و هیچ‌کدام را هزینهٔ واقعی فرض نمی‌کنیم.
    one_way_reference = FEE_REFERENCE_RATE_PCT
    two_fill_reference = round(FEE_REFERENCE_RATE_PCT * 2, 8)
    result["cost_accounting"] = {
        "status": "PROXY_BASIS_UNRESOLVED",
        "gross_return_pct": round(gross, 8),
        "fee": {
            "status": "PROXY_SCENARIOS_ONLY",
            "model": FEE_MODEL,
            "reference_rate_pct": FEE_REFERENCE_RATE_PCT,
            "basis": "UNRESOLVED_PER_FILL_VS_ROUND_TRIP",
            "round_trip_total_interpretation": {
                "fee_pct": one_way_reference,
                "after_fee_only_pct": round(gross - one_way_reference, 8),
            },
            "per_fill_interpretation": {
                "fill_count": 2,
                "fee_pct": two_fill_reference,
                "after_fee_only_pct": round(gross - two_fill_reference, 8),
            },
        },
        "spread": {"status": "UNAVAILABLE"},
        "slippage": {"status": "UNAVAILABLE"},
        "funding": {"status": "UNAVAILABLE"},
        "market_impact": {"status": "UNAVAILABLE"},
        "net_return_pct": "UNAVAILABLE",
        "net_ev": "NOT_CALCULATED",
        "unavailable_components": ["fee_basis", "spread", "slippage", "funding", "market_impact"],
        "warning": "FEE_SCENARIOS_ARE_NOT_OBSERVED_COSTS_OR_FULLY_NET_PERFORMANCE",
    }
    # Preserve legacy fields as UNAVAILABLE until every required cost is observed.
    result["fee_pct"] = "UNAVAILABLE"
    result["slippage_pct"] = "UNAVAILABLE"
    result["net_pnl_pct"] = "UNAVAILABLE"
    return result


def annotate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("outcomes"), list):
        raise ValueError("INVALID_OUTCOME_PAYLOAD_SCHEMA")
    updated = dict(payload)
    rows = []
    for row in payload["outcomes"]:
        if not isinstance(row, dict):
            raise ValueError("INVALID_OUTCOME_ROW")
        rows.append(annotate_outcome_costs(row))
    updated["outcomes"] = rows
    updated["cost_accounting_schema_version"] = 1
    updated["cost_accounting_model"] = FEE_MODEL
    return updated


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcomes", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.outcomes.read_text(encoding="utf-8"))
    updated = annotate_payload(payload)
    write_payload(args.outcomes, updated)
    summary = {}
    for row in updated["outcomes"]:
        state = row.get("cost_accounting", {}).get("status", "UNKNOWN")
        summary[state] = summary.get(state, 0) + 1
    print("OUTCOME_COST_ACCOUNTING " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
