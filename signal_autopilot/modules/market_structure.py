"""Causal market-structure primitives inspired by public SMC research.

این ماژول فقط از کندل‌های بسته‌شده استفاده می‌کند.
نقاط Swing با تأخیر تأیید می‌شوند تا اطلاعات آینده به گذشته نشت نکند.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TypedDict


class FairValueGap(TypedDict):
    direction: str
    bottom: float
    top: float
    pattern_start_index: int
    confirmed_at_index: int


class SwingPoint(TypedDict):
    kind: str
    price: float
    pivot_index: int
    confirmed_at_index: int


def _validated(candles: Sequence[Mapping[str, float]]) -> list[dict[str, float]]:
    """Validate OHLC rows and normalize numeric values."""
    rows: list[dict[str, float]] = []
    for index, candle in enumerate(candles):
        try:
            row = {key: float(candle[key]) for key in ("open", "high", "low", "close")}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid OHLC candle at index {index}") from exc
        if not all(math.isfinite(value) for value in row.values()):
            raise ValueError(f"non-finite OHLC value at index {index}")
        if row["high"] < max(row["open"], row["close"], row["low"]):
            raise ValueError(f"invalid high at index {index}")
        if row["low"] > min(row["open"], row["close"], row["high"]):
            raise ValueError(f"invalid low at index {index}")
        rows.append(row)
    return rows


def detect_fair_value_gaps(
    candles: Sequence[Mapping[str, float]],
) -> list[FairValueGap]:
    """Return 3-candle FVGs only when the third candle has closed.

    A bullish gap exists when candle[i].low > candle[i-2].high and the
    middle candle is bullish. A bearish gap is the inverse. The event is
    timestamped at i (the confirmation candle), never retroactively at i-1.
    A backtest must not fill at the confirmation close; earliest execution
    is the next tradable bar unless a stricter execution model is used.
    """
    rows = _validated(candles)
    gaps: list[FairValueGap] = []
    for index in range(2, len(rows)):
        first, middle, third = rows[index - 2], rows[index - 1], rows[index]
        if middle["close"] > middle["open"] and third["low"] > first["high"]:
            gaps.append({
                "direction": "BULLISH",
                "bottom": first["high"],
                "top": third["low"],
                "pattern_start_index": index - 2,
                "confirmed_at_index": index,
            })
        elif middle["close"] < middle["open"] and third["high"] < first["low"]:
            gaps.append({
                "direction": "BEARISH",
                "bottom": third["high"],
                "top": first["low"],
                "pattern_start_index": index - 2,
                "confirmed_at_index": index,
            })
    return gaps


def detect_confirmed_swings(
    candles: Sequence[Mapping[str, float]],
    span: int = 2,
) -> list[SwingPoint]:
    """Find local highs/lows, reporting them only after span right bars close.

    Ties are resolved toward the earliest equal extreme in the window.
    If one candle qualifies as both a swing high and swing low, it is omitted
    as ambiguous. confirmed_at_index is the first index at which the pivot
    could have been known without future leakage.
    """
    if not isinstance(span, int) or span < 1:
        raise ValueError("span must be a positive integer")
    rows = _validated(candles)
    points: list[SwingPoint] = []
    for pivot in range(span, len(rows) - span):
        window = rows[pivot - span : pivot + span + 1]
        high = rows[pivot]["high"]
        low = rows[pivot]["low"]
        is_high = high == max(item["high"] for item in window)
        is_low = low == min(item["low"] for item in window)
        if is_high:
            is_high = high > max(item["high"] for item in window[:span])
            is_high = is_high and high >= max(item["high"] for item in window[span + 1 :])
        if is_low:
            is_low = low < min(item["low"] for item in window[:span])
            is_low = is_low and low <= min(item["low"] for item in window[span + 1 :])
        if is_high == is_low:
            continue
        points.append({
            "kind": "HIGH" if is_high else "LOW",
            "price": high if is_high else low,
            "pivot_index": pivot,
            "confirmed_at_index": pivot + span,
        })
    return points
