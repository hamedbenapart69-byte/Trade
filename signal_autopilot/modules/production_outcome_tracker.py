"""Track simulated price-path outcomes for production WATCHLIST signals.

This module never represents an executed trade. It reuses the public OHLCV
outcome evaluator while keeping production state and output separate from the
research-signal tracker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PACKAGE_ROOT = str(Path(__file__).resolve().parents[1])
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from modules.research_tracker import fetch_public_ohlcv, update_outcomes

INTERVAL_MS = 15 * 60 * 1000
EVALUATION_KIND = "PRODUCTION_WATCHLIST_SHADOW"
MAX_STATE_AGE = timedelta(hours=4)
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)


def _validate_state_freshness(state: dict[str, Any], now: datetime) -> None:
    if now.tzinfo is None:
        raise ValueError("TRACKER_NOW_TIMEZONE_REQUIRED")
    updated = _parse_utc(state.get("updated_at_utc"), "STATE_UPDATED_AT")
    age = now.astimezone(timezone.utc) - updated
    if age < -MAX_FUTURE_CLOCK_SKEW:
        raise ValueError("PRODUCTION_SIGNAL_STATE_FUTURE_DATED")
    if age > MAX_STATE_AGE:
        raise ValueError(f"PRODUCTION_SIGNAL_STATE_STALE:age_seconds={int(age.total_seconds())}")


def _snapshot_fingerprint(signal: dict[str, Any]) -> str:
    # وضعیت OPEN/CLOSED قابل تغییر است؛ تمام شواهد و سطوح خود سیگنال ثابت می‌مانند.
    snapshot = {key: value for key, value in signal.items() if key != "source_tracker_status"}
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_MISSING")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}_INVALID")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field}_INVALID")
    return number


def _adapt_record(
    signal_id: str,
    record: dict[str, Any],
    tracker_status: str,
) -> dict[str, Any] | None:
    decision = record.get("decision") or record.get("status")
    if record.get("mode") != "PRODUCTION" or decision != "WATCHLIST":
        return None
    if str(record.get("signal_id") or signal_id) != signal_id:
        raise ValueError("PRODUCTION_SIGNAL_ID_MISMATCH")
    direction = record.get("direction")
    if direction not in {"BUY", "SELL"}:
        raise ValueError("PRODUCTION_SIGNAL_DIRECTION_INVALID")

    levels = record.get("levels")
    levels = levels if isinstance(levels, dict) else {}
    entry_raw = record.get("entry")
    stop_raw = record.get("stop_loss")
    target_raw = record.get("take_profit")
    if entry_raw is None:
        entry_raw = levels.get("entry")
    if stop_raw is None:
        stop_raw = levels.get("stop_loss")
    if target_raw is None:
        target_raw = levels.get("tp2")
    entry = _finite_number(entry_raw, "ENTRY_REFERENCE")
    stop = _finite_number(stop_raw, "STOP_REFERENCE")
    target = _finite_number(target_raw, "TP2_REFERENCE")
    if direction == "BUY" and not stop < entry < target:
        raise ValueError("PRODUCTION_SIGNAL_LEVEL_ORDER_INVALID")
    if direction == "SELL" and not target < entry < stop:
        raise ValueError("PRODUCTION_SIGNAL_LEVEL_ORDER_INVALID")
    rr_raw = levels.get("rr", record.get("rr"))
    if rr_raw is not None:
        rr = _finite_number(rr_raw, "RR_REFERENCE")
        risk, reward = (
            (entry - stop, target - entry)
            if direction == "BUY"
            else (stop - entry, entry - target)
        )
        if not math.isclose(rr, reward / risk, rel_tol=0.10, abs_tol=0.05):
            raise ValueError("PRODUCTION_SIGNAL_RR_MISMATCH")

    created = _parse_utc(record.get("created_at_utc"), "CREATED_AT")
    candle_time = _parse_utc(record.get("last_closed_candle_utc"), "LAST_CLOSED_CANDLE")
    candle_open_ms = int(candle_time.timestamp() * 1000)
    if candle_open_ms % INTERVAL_MS:
        raise ValueError("LAST_CLOSED_CANDLE_NOT_15M_ALIGNED")
    if candle_time > created:
        raise ValueError("LAST_CLOSED_CANDLE_AFTER_SIGNAL_TIME")

    tp1_raw = record.get("take_profit_1")
    if tp1_raw is None:
        tp1_raw = levels.get("tp1")
    tp1 = None
    if tp1_raw is not None:
        tp1 = _finite_number(tp1_raw, "TP1_REFERENCE")
        if direction == "BUY" and not entry < tp1 < target:
            raise ValueError("PRODUCTION_TP1_ORDER_INVALID")
        if direction == "SELL" and not target < tp1 < entry:
            raise ValueError("PRODUCTION_TP1_ORDER_INVALID")

    symbol = str(record.get("symbol") or "").strip().upper()
    if not symbol.endswith("USDT") or "/" in symbol or ":" in symbol:
        raise ValueError("PRODUCTION_SIGNAL_SYMBOL_INVALID")

    lfs_score = record.get("lfs_score")
    if lfs_score is not None:
        if isinstance(lfs_score, bool) or not isinstance(lfs_score, (int, float)) or not math.isfinite(float(lfs_score)) or not 0 <= float(lfs_score) <= 1:
            raise ValueError("PRODUCTION_LFS_SCORE_INVALID")
        lfs_score = float(lfs_score)
    lfs_coverage = record.get("lfs_coverage_pct")
    if lfs_coverage is not None:
        if isinstance(lfs_coverage, bool) or not isinstance(lfs_coverage, (int, float)) or not math.isfinite(float(lfs_coverage)) or not 0 <= float(lfs_coverage) <= 100:
            raise ValueError("PRODUCTION_LFS_COVERAGE_INVALID")
        lfs_coverage = float(lfs_coverage)

    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "direction": direction,
        "created_at_utc": created.isoformat(),
        "candle_open_time": candle_open_ms,
        "entry_reference": entry,
        "stop_reference": stop,
        "target_reference": target,
        "collection_status": "PENDING_OUTCOME_LABEL",
        "evaluation_kind": EVALUATION_KIND,
        "execution_status": "NOT_EXECUTED",
        "source_mode": "PRODUCTION",
        "source_decision": "WATCHLIST",
        "source_tracker_status": tracker_status,
        "tp1_reference": tp1,
        "rr_reference": float(rr_raw) if rr_raw is not None else None,
        "hypothesis": str(record.get("hypothesis") or "UNAVAILABLE"),
        "falsification": str(record.get("falsification") or "UNAVAILABLE"),
        "lfs_score": lfs_score,
        "lfs_status": record.get("lfs_status") or "UNAVAILABLE",
        "lfs_coverage_pct": lfs_coverage,
        "cvd_source": (record.get("cvd") or {}).get("source", "UNAVAILABLE")
        if isinstance(record.get("cvd"), dict) else "UNAVAILABLE",
    }


def _collect_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(state, dict) or not isinstance(state.get("open_signals"), dict):
        raise ValueError("PRODUCTION_SIGNAL_STATE_SCHEMA_INVALID")
    open_rows = state["open_signals"]
    closed_rows = state.get("closed_signals", {})
    if not isinstance(closed_rows, dict):
        raise ValueError("PRODUCTION_CLOSED_STATE_SCHEMA_INVALID")

    adapted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tracker_status, rows in (("OPEN", open_rows), ("CLOSED", closed_rows)):
        for raw_id, record in rows.items():
            signal_id = str(raw_id).strip()
            if not signal_id or not isinstance(record, dict):
                raise ValueError("PRODUCTION_SIGNAL_RECORD_INVALID")
            item = _adapt_record(signal_id, record, tracker_status)
            if item is None:
                continue
            if signal_id in seen:
                raise ValueError("PRODUCTION_SIGNAL_ID_DUPLICATE")
            if not item["symbol"]:
                raise ValueError("PRODUCTION_SIGNAL_SYMBOL_MISSING")
            seen.add(signal_id)
            adapted.append(item)
    return sorted(adapted, key=lambda row: (row["created_at_utc"], row["signal_id"]))


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".production_outcomes.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def update_production_outcomes(
    state_path: Path,
    outcomes_path: Path,
    now: datetime | None = None,
    fetcher: Callable = fetch_public_ohlcv,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("TRACKER_NOW_TIMEZONE_REQUIRED")
    now = now.astimezone(timezone.utc)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("PRODUCTION_SIGNAL_STATE_SCHEMA_INVALID")
    _validate_state_freshness(state, now)
    signals = _collect_signals(state)
    signal_ids = {row["signal_id"] for row in signals}

    previous_payload: dict[str, Any] = {"outcomes": []}
    if outcomes_path.exists():
        previous_payload = json.loads(outcomes_path.read_text(encoding="utf-8"))
        if not isinstance(previous_payload, dict) or not isinstance(previous_payload.get("outcomes"), list):
            raise ValueError("PRODUCTION_OUTCOME_STATE_SCHEMA_INVALID")
        if any(not isinstance(row, dict) or not row.get("signal_id") for row in previous_payload["outcomes"]):
            raise ValueError("PRODUCTION_OUTCOME_STATE_RECORD_INVALID")
        previous_ids = [str(row["signal_id"]) for row in previous_payload["outcomes"]]
        if len(previous_ids) != len(set(previous_ids)):
            raise ValueError("PRODUCTION_OUTCOME_STATE_DUPLICATE_ID")
        previous_ids = set(previous_ids)
        if previous_ids - signal_ids:
            raise ValueError("PRODUCTION_SIGNAL_HISTORY_REGRESSION")

    outcomes_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".production-outcome-work-", dir=str(outcomes_path.parent)) as temp_dir:
        temp_root = Path(temp_dir)
        signals_temp = temp_root / "signals.json"
        outcomes_temp = temp_root / "outcomes.json"
        signals_temp.write_text(
            json.dumps({"signals": signals}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if outcomes_path.exists():
            outcomes_temp.write_text(outcomes_path.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            outcomes_temp.write_text('{"outcomes": []}\n', encoding="utf-8")

        result = update_outcomes(signals_temp, outcomes_temp, now=now, fetcher=fetcher)
        payload = json.loads(outcomes_temp.read_text(encoding="utf-8"))

    rows = payload.get("outcomes")
    if not isinstance(rows, list):
        raise ValueError("PRODUCTION_OUTCOME_RESULT_SCHEMA_INVALID")
    by_id = {row["signal_id"]: row for row in signals}
    outcome_ids = [str(row.get("signal_id") or "") for row in rows if isinstance(row, dict)]
    if len(outcome_ids) != len(rows) or set(outcome_ids) != signal_ids or len(set(outcome_ids)) != len(outcome_ids):
        raise ValueError("PRODUCTION_OUTCOME_COVERAGE_MISMATCH")

    for outcome in rows:
        source = by_id[outcome["signal_id"]]
        fingerprint = _snapshot_fingerprint(source)
        previous_fingerprint = outcome.get("source_snapshot_fingerprint")
        if previous_fingerprint and previous_fingerprint != fingerprint:
            raise ValueError(f"PRODUCTION_SIGNAL_SNAPSHOT_MUTATED:{outcome['signal_id']}")
        # فایل‌های قدیمی فاقد fingerprint هستند؛ حداقل سطوح مرجع ثبت‌شده را
        # با منبع فعلی تطبیق می‌دهیم تا migration بی‌صدا دادهٔ تاریخی را عوض نکند.
        for field in ("symbol", "direction", "entry_reference", "stop_reference", "target_reference"):
            previous_value = outcome.get(field)
            current_value = source.get(field)
            if previous_value is not None and previous_value != current_value:
                raise ValueError(f"PRODUCTION_SIGNAL_REFERENCE_MUTATED:{outcome['signal_id']}:{field}")
        outcome["source_snapshot_fingerprint"] = fingerprint
        for key in (
            "evaluation_kind", "execution_status", "source_mode", "source_decision",
            "source_tracker_status", "tp1_reference", "hypothesis", "falsification",
            "lfs_score", "lfs_status", "lfs_coverage_pct", "cvd_source",
        ):
            outcome[key] = source[key]
        outcome["statistics_status"] = "NOT_CALCULATED"
        outcome["cost_status"] = "UNAVAILABLE"

    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1

    payload.update({
        "schema_version": 1,
        "updated_at_utc": now.isoformat(),
        "evaluation_kind": EVALUATION_KIND,
        "evaluation_contract": "FIRST_15M_OPEN_STRICTLY_AFTER_SIGNAL_TIMESTAMP",
        "execution_status": "NOT_EXECUTED",
        "statistics_status": "NOT_CALCULATED",
        "cost_status": "UNAVAILABLE",
        "source_state": "signal-state/signal_autopilot/state/open_signals.json",
        "source_signals_count": len(signals),
        "outcomes_count": len(rows),
        "counts": counts,
        "outcomes": rows,
    })
    _atomic_write(outcomes_path, payload)
    return {
        "source_signals_count": len(signals),
        "outcomes_count": len(rows),
        "counts": counts,
        "path": str(outcomes_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = update_production_outcomes(args.state, args.outcomes)
    print("PRODUCTION_SHADOW_OUTCOME_SUMMARY " + json.dumps(result["counts"], sort_keys=True))
    print(f"PRODUCTION_SHADOW_COVERAGE={result['outcomes_count']}/{result['source_signals_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
