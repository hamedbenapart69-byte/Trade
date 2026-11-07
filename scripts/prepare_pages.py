"""Build a minimal, validated public dashboard payload for GitHub Pages."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "v5_live_scan.json"
SITE = ROOT / "site"
ACTIONABLE = {"BUY_NOW", "SELL_NOW"}
CONDITIONAL = {"CONDITIONAL_BUY", "CONDITIONAL_SELL"}


def _safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def _num(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _valid_actionable(item: dict, source_ok: bool) -> bool:
    risk = item.get("risk") or {}
    entry = item.get("entry")
    stop = item.get("stop_loss")
    target = item.get("take_profit")
    stop_pct = _num(item.get("stop_pct"))
    confidence = _num(item.get("confidence_v5"))
    planned_loss = _num(risk.get("planned_loss_usd"))
    leverage = _num(risk.get("required_leverage"))
    rr = _num(risk.get("reward_to_risk"))
    return bool(
        source_ok
        and item.get("decision") in ACTIONABLE
        and item.get("direction") in {"LONG", "SHORT"}
        and item.get("data_grade") in {"A", "B"}
        and confidence is not None and confidence >= 70
        and all(_num(v) is not None and _num(v) > 0 for v in (entry, stop, target))
        and stop_pct is not None and 0.5 <= stop_pct <= 3.0
        and planned_loss is not None and 0 < planned_loss <= 4.0 + 1e-9
        and leverage is not None and 0 < leverage <= 5.0 + 1e-9
        and rr is not None and rr >= 2.0
        and risk.get("valid") is True
        and risk.get("contract_spec_verified") is True
        and item.get("self_audit_passed") is True
        and (item.get("entry_quality") or {}).get("entry_ok") is True
        and (item.get("entry_quality") or {}).get("chase") is False
    )


def _valid_conditional(item: dict, source_ok: bool) -> bool:
    entry = item.get("entry_quality") or {}
    score = _num(item.get("confidence_v5"))
    trigger = _num(entry.get("trigger_level"))
    return bool(
        source_ok
        and item.get("decision") in CONDITIONAL
        and item.get("direction") in {"LONG", "SHORT"}
        and item.get("data_grade") in {"A", "B"}
        and score is not None and score >= 60
        and item.get("self_audit_passed") is True
        and isinstance(entry.get("confirmation_required"), str)
        and entry.get("confirmation_required").strip()
        and trigger is not None and trigger > 0
        and (item.get("risk") or {}).get("valid") is True
        and (item.get("risk") or {}).get("contract_spec_verified") is True
    )


def build_payload(raw: dict) -> dict:
    raw = _safe(raw if isinstance(raw, dict) else {})
    generated = datetime.now(timezone.utc).isoformat()
    context = raw.get("validation_context") or {}
    sources = raw.get("source_status") or {}
    source_ok = bool(
        context.get("fixture_data") is False
        and context.get("account_connection") is False
        and context.get("order_execution") is False
        and sources.get("account_connection") is False
        and sources.get("exchange_api_credentials") is False
        and sources.get("order_execution") is False
        and sources.get("futures_ohlcv")
    )
    status = raw.get("status")
    if status not in {"SCAN_COMPLETED", "DATA_UNAVAILABLE", "INSUFFICIENT_DATA"}:
        status = "INSUFFICIENT_DATA"
    if status == "SCAN_COMPLETED" and not source_ok:
        status = "INSUFFICIENT_DATA"
    raw_actionable = raw.get("actionable") if isinstance(raw.get("actionable"), list) else []
    raw_conditional = raw.get("conditional") if isinstance(raw.get("conditional"), list) else []
    actionable = [x for x in raw_actionable if isinstance(x, dict) and _valid_actionable(x, source_ok)] if status == "SCAN_COMPLETED" else []
    conditional = [x for x in raw_conditional if isinstance(x, dict) and _valid_conditional(x, source_ok)] if status == "SCAN_COMPLETED" else []
    return {
        "schema_version": 1,
        "status": status,
        "scan_id": raw.get("scan_id"),
        "scanned_at": raw.get("scanned_at") or raw.get("generated_at") or generated,
        "published_at": generated,
        "universe_requested": raw.get("universe_requested"),
        "eligible_assets": raw.get("eligible_assets"),
        "selected_assets": raw.get("selected_assets"),
        "screened_assets": raw.get("screened_assets"),
        "partial_scan": raw.get("partial_scan"),
        "coverage": raw.get("coverage") if isinstance(raw.get("coverage"), dict) else {},
        "source_status": sources,
        "actionable": actionable,
        "conditional": conditional,
        "performance": raw.get("performance") if isinstance(raw.get("performance"), dict) else {},
        "validation_context": context,
        "limitations": raw.get("limitations") if isinstance(raw.get("limitations"), list) else [],
        "publication_gate": {
            "source_verified": source_ok,
            "actionable_candidates_received": len(raw_actionable),
            "actionable_candidates_published": len(actionable),
            "conditional_candidates_received": len(raw_conditional),
            "conditional_candidates_published": len(conditional),
        },
        "error": raw.get("reason") or raw.get("error"),
    }


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit("live_scan_output_missing")
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    payload = build_payload(raw)
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (SITE / "index.html").write_text(
        (ROOT / "web" / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "actionable": len(payload["actionable"]),
        "conditional": len(payload["conditional"]),
        "source_verified": payload["publication_gate"]["source_verified"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
