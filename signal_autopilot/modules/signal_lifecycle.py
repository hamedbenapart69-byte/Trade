"""Deterministic, closed-candle lifecycle evaluation for paper-tracked signals.

This module never places orders. It only records entry activation, target milestones,
stop outcomes, and expiry from OHLCV candles. When stop and target are both touched
inside one candle, the stop is evaluated first (conservative, no invented intrabar path).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


FINAL_STATUSES = {
    "TARGET_REACHED",
    "STOPPED",
    "STOPPED_AFTER_PARTIAL",
    "EXPIRED",
    "INVALIDATED",
}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _candle_time_ms(candle: dict[str, Any]) -> int | None:
    for key in ("open_time", "timestamp"):
        value = candle.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    value = _parse_dt(candle.get("timestamp_utc") or candle.get("open_time_utc"))
    return int(value.timestamp() * 1000) if value else None


def _touched(direction: str, price: float, candle: dict[str, Any], kind: str) -> bool:
    high, low = float(candle["high"]), float(candle["low"])
    if kind == "entry":
        return low <= price <= high
    if kind == "stop":
        return low <= price if direction == "BUY" else high >= price
    return high >= price if direction == "BUY" else low <= price


def _event(signal: dict[str, Any], event_type: str, candle_ms: int, price: float | None = None) -> dict[str, Any]:
    return {
        "event_id": f"{signal.get('signal_id')}:{event_type}:{candle_ms}",
        "type": event_type,
        "at_utc": datetime.fromtimestamp(candle_ms / 1000, timezone.utc).isoformat(),
        "price": price,
    }


def evaluate_open_signal(
    signal: dict[str, Any],
    candles: list[dict[str, Any]],
    now: datetime | None = None,
    expiry_hours: int = 24,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate unseen closed candles and return (updated signal, newly emitted events)."""
    updated = dict(signal)
    direction = str(updated.get("direction") or updated.get("side") or "").upper()
    if direction not in {"BUY", "SELL"}:
        raise ValueError("signal_direction_must_be_BUY_or_SELL")

    levels = updated.get("levels") or {}
    entry = updated.get("entry", levels.get("entry"))
    stop = updated.get("stop_loss", levels.get("stop_loss"))
    targets = [
        levels.get("tp1", (updated.get("take_profit") or [None])[0]),
        levels.get("tp2", (updated.get("take_profit") or [None, None])[1] if len(updated.get("take_profit") or []) > 1 else None),
        levels.get("tp3"),
    ]
    if entry is None or stop is None or not any(x is not None for x in targets):
        raise ValueError("signal_requires_entry_stop_and_at_least_one_target")

    created = _parse_dt(updated.get("created_at_utc") or updated.get("issued_at_utc"))
    if created is None:
        raise ValueError("signal_created_at_utc_required")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)

    status = str(updated.get("lifecycle_status") or "PENDING_ENTRY")
    if status in FINAL_STATUSES:
        return updated, []

    last_ms = int(updated.get("last_evaluated_candle_open_time", 0) or 0)
    new_events: list[dict[str, Any]] = []
    event_history = list(updated.get("lifecycle_events") or [])
    ordered = sorted(
        (c for c in candles if _candle_time_ms(c) is not None),
        key=lambda c: _candle_time_ms(c) or 0,
    )

    for candle in ordered:
        candle_ms = _candle_time_ms(candle)
        assert candle_ms is not None
        candle_dt = datetime.fromtimestamp(candle_ms / 1000, timezone.utc)
        if candle_ms <= last_ms or candle_dt <= created:
            continue
        # Only closed candles are accepted. Caller must provide closed OHLCV bars.
        high, low = float(candle["high"]), float(candle["low"])
        if high < low:
            raise ValueError("invalid_candle_high_below_low")

        if status == "PENDING_ENTRY":
            if not _touched(direction, float(entry), candle, "entry"):
                last_ms = candle_ms
                continue
            status = "ACTIVE"
            updated["activated_at_utc"] = candle_dt.isoformat()
            new_events.append(_event(updated, "ENTRY_ACTIVATED", candle_ms, float(entry)))

        if status == "ACTIVE":
            # Stop first if stop and one or more targets share the same candle.
            if _touched(direction, float(stop), candle, "stop"):
                partial = int(updated.get("targets_hit", 0)) > 0
                status = "STOPPED_AFTER_PARTIAL" if partial else "STOPPED"
                new_events.append(_event(updated, "STOP_HIT", candle_ms, float(stop)))
                updated["closed_at_utc"] = candle_dt.isoformat()
                updated["exit_price"] = float(stop)
                updated["close_reason"] = status
            else:
                hit_count = int(updated.get("targets_hit", 0))
                for index, target in enumerate(targets, start=1):
                    if target is None or index <= hit_count:
                        continue
                    if _touched(direction, float(target), candle, "target"):
                        hit_count = index
                        updated["targets_hit"] = hit_count
                        updated[f"tp{index}_hit_at_utc"] = candle_dt.isoformat()
                        new_events.append(_event(updated, f"TP{index}_HIT", candle_ms, float(target)))
                        if index == 3 or (index == 2 and targets[2] is None):
                            status = "TARGET_REACHED"
                            updated["closed_at_utc"] = candle_dt.isoformat()
                            updated["exit_price"] = float(target)
                            updated["close_reason"] = status
                            break
                        # Continue checking subsequent targets only when the same candle spans them.
        last_ms = candle_ms
        if status in FINAL_STATUSES:
            break

    updated["lifecycle_status"] = status
    updated["last_evaluated_candle_open_time"] = last_ms
    if status not in FINAL_STATUSES:
        expiry = _parse_dt(updated.get("expires_at_utc")) or (created + timedelta(hours=expiry_hours))
        if current >= expiry:
            status = "EXPIRED"
            updated["lifecycle_status"] = status
            updated["closed_at_utc"] = current.isoformat()
            updated["close_reason"] = "ENTRY_NOT_ACTIVATED" if not updated.get("activated_at_utc") else "TIME_EXPIRY"
            new_events.append(_event(updated, "SIGNAL_EXPIRED", int(current.timestamp() * 1000), None))

    if new_events:
        known = {e.get("event_id") for e in event_history}
        additions = [e for e in new_events if e["event_id"] not in known]
        event_history.extend(additions)
        new_events = additions
    updated["lifecycle_events"] = event_history
    return updated, new_events


def summarize_signals(signals: list[dict[str, Any]], day: str) -> dict[str, int | str]:
    """Build a UTC-day report from issued and terminal outcomes."""
    issued = [s for s in signals if str(s.get("created_at_utc", ""))[:10] == day]
    closed_today = [
        s for s in signals
        if str(s.get("closed_at_utc", ""))[:10] == day
        and s.get("lifecycle_status") in FINAL_STATUSES
    ]
    return {
        "day_utc": day,
        "issued": len(issued),
        "target_reached": sum(s.get("lifecycle_status") == "TARGET_REACHED" for s in closed_today),
        "stopped": sum(s.get("lifecycle_status") in {"STOPPED", "STOPPED_AFTER_PARTIAL"} for s in closed_today),
        "expired": sum(s.get("lifecycle_status") == "EXPIRED" for s in closed_today),
        "active_or_pending": sum(s.get("lifecycle_status", "PENDING_ENTRY") not in FINAL_STATUSES for s in signals),
        "closed_today": len(closed_today),
    }
