"""Cost-coverage annotations for Stage 1 research outcomes.

All rates in this module are percentage points of notional return, not leveraged ROI.
The configured 0.04% per-fill fee is a PROXY assumption from the project cost guard.
Unknown execution costs remain UNAVAILABLE; this module never labels fee-only return
as fully net performance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

FEE_RATE_PER_FILL_PCT = 0.04
FEE_MODEL = "PROXY_FIXED_0.04_PERCENT_PER_FILL"
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

    fills = 2
    fee_proxy = round(FEE_RATE_PER_FILL_PCT * fills, 8)
    result["cost_accounting"] = {
        "status": "PARTIAL_PROXY",
        "gross_return_pct": round(gross, 8),
        "fee": {
            "status": "PROXY",
            "model": FEE_MODEL,
            "rate_pct_per_fill": FEE_RATE_PER_FILL_PCT,
            "fill_count": fills,
            "total_pct": fee_proxy,
        },
        "spread": {"status": "UNAVAILABLE"},
        "slippage": {"status": "UNAVAILABLE"},
        "funding": {"status": "UNAVAILABLE"},
        "market_impact": {"status": "UNAVAILABLE"},
        "net_after_fee_only_pct": round(gross - fee_proxy, 8),
        "net_return_pct": "UNAVAILABLE",
        "net_ev": "NOT_CALCULATED",
        "unavailable_components": ["spread", "slippage", "funding", "market_impact"],
        "warning": "FEE_ONLY_PROXY_IS_NOT_FULLY_NET_PERFORMANCE",
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
    updated["outcomes"] = [
        annotate_outcome_costs(row) if isinstance(row, dict) else
        (_ for _ in ()).throw(ValueError("INVALID_OUTCOME_ROW"))
        for row in payload["outcomes"]
    ]
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
    write_payload(args.outcomes, annotate_payload(payload))
    summary = {}
    for row in payload["outcomes"]:
        state = row.get("cost_accounting", {}).get("status", "UNKNOWN")
        summary[state] = summary.get(state, 0) + 1
    print("OUTCOME_COST_ACCOUNTING " + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
