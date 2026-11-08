"""Deterministic UTC, schema, duplicate and gap validation for Stage 1."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

OHLCV_FIELDS = ("timestamp", "open", "high", "low", "close", "volume")


def validate_ohlcv_rows(rows: Iterable[dict]) -> list[dict]:
    normalized: dict[int, dict] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("ohlcv_row_not_object")
        missing = [key for key in OHLCV_FIELDS if key not in raw]
        if missing:
            raise ValueError(f"ohlcv_missing_fields:{','.join(missing)}")
        ts = int(raw["timestamp"])
        if ts <= 0:
            raise ValueError("ohlcv_invalid_timestamp")
        vals = {key: float(raw[key]) for key in OHLCV_FIELDS[1:]}
        if any(v < 0 for v in vals.values()) or min(vals[k] for k in ("open","high","low","close")) <= 0:
            raise ValueError("ohlcv_invalid_numeric_value")
        if vals["high"] < max(vals["open"], vals["close"], vals["low"]):
            raise ValueError("ohlcv_high_below_price")
        if vals["low"] > min(vals["open"], vals["close"], vals["high"]):
            raise ValueError("ohlcv_low_above_price")
        normalized[ts] = {"timestamp": ts, **vals}
    return [normalized[k] for k in sorted(normalized)]


def gap_report(rows: list[dict], interval_ms: int = 3_600_000) -> dict:
    timestamps = [int(row["timestamp"]) for row in rows]
    deltas = [b-a for a,b in zip(timestamps, timestamps[1:])]
    gaps = [delta for delta in deltas if delta > interval_ms]
    expected = ((timestamps[-1]-timestamps[0]) // interval_ms + 1) if len(timestamps)>1 else len(timestamps)
    return {
        "rows": len(rows),
        "duplicates_removed": 0,
        "expected_rows_between_endpoints": expected,
        "missing_intervals": max(expected-len(rows), 0),
        "gap_count_over_interval": len(gaps),
        "max_gap_ms": max(deltas, default=0),
        "max_gap_hours": round(max(deltas, default=0)/3_600_000, 4),
        "first_utc": datetime.fromtimestamp(timestamps[0]/1000, timezone.utc).isoformat() if timestamps else None,
        "last_utc": datetime.fromtimestamp(timestamps[-1]/1000, timezone.utc).isoformat() if timestamps else None,
        "no_gap_over_1h": not gaps,
    }
