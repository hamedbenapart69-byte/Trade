"""Pure-Python OHLCV validation and technical indicators.

All functions are deterministic and provider-agnostic. Inputs must be chronological
(oldest first). No network access, exchange account access, or trade execution occurs.
"""
from __future__ import annotations

from math import isfinite, sqrt
from statistics import mean, pstdev
from typing import Iterable, Sequence


class MarketDataValidationError(ValueError):
    """Raised when market data is malformed or insufficient for a calculation."""


def _series(values: Iterable[float], *, minimum: int = 1, name: str = "series") -> list[float]:
    out = [float(v) for v in values]
    if len(out) < minimum:
        raise MarketDataValidationError(f"{name}_requires_at_least_{minimum}_values")
    if any(not isfinite(v) for v in out):
        raise MarketDataValidationError(f"{name}_contains_non_finite_values")
    return out


def validate_ohlcv(candles: Sequence[dict], *, minimum: int = 2) -> list[dict[str, float]]:
    """Validate canonical candles with timestamp/open/high/low/close/volume keys."""
    if len(candles) < minimum:
        raise MarketDataValidationError(f"ohlcv_requires_at_least_{minimum}_candles")
    clean: list[dict[str, float]] = []
    last_ts = -float("inf")
    for i, candle in enumerate(candles):
        try:
            row = {k: float(candle[k]) for k in ("timestamp", "open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError) as exc:
            raise MarketDataValidationError(f"candle_{i}_missing_or_invalid_field") from exc
        if any(not isfinite(v) for v in row.values()):
            raise MarketDataValidationError(f"candle_{i}_contains_non_finite_values")
        if row["timestamp"] <= last_ts:
            raise MarketDataValidationError("timestamps_must_be_strictly_increasing")
        if min(row["open"], row["high"], row["low"], row["close"]) <= 0 or row["volume"] < 0:
            raise MarketDataValidationError(f"candle_{i}_has_invalid_price_or_volume")
        if row["high"] < max(row["open"], row["close"], row["low"]):
            raise MarketDataValidationError(f"candle_{i}_high_is_inconsistent")
        if row["low"] > min(row["open"], row["close"], row["high"]):
            raise MarketDataValidationError(f"candle_{i}_low_is_inconsistent")
        clean.append(row)
        last_ts = row["timestamp"]
    return clean


def ema(values: Iterable[float], period: int) -> float:
    data = _series(values, minimum=period, name="ema")
    if period < 1:
        raise MarketDataValidationError("ema_period_must_be_positive")
    alpha = 2.0 / (period + 1.0)
    value = mean(data[:period])
    for item in data[period:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def rsi(values: Iterable[float], period: int = 14) -> float:
    data = _series(values, minimum=period + 1, name="rsi")
    if period < 1:
        raise MarketDataValidationError("rsi_period_must_be_positive")
    gains = [max(data[i] - data[i - 1], 0.0) for i in range(1, len(data))]
    losses = [max(data[i - 1] - data[i], 0.0) for i in range(1, len(data))]
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_ranges(candles: Sequence[dict]) -> list[float]:
    rows = validate_ohlcv(candles, minimum=2)
    out = []
    for i in range(1, len(rows)):
        current, previous = rows[i], rows[i - 1]
        out.append(max(current["high"] - current["low"], abs(current["high"] - previous["close"]), abs(current["low"] - previous["close"])))
    return out


def atr(candles: Sequence[dict], period: int = 14) -> float:
    if period < 1:
        raise MarketDataValidationError("atr_period_must_be_positive")
    ranges = _series(true_ranges(candles), minimum=period, name="atr")
    value = mean(ranges[:period])
    for item in ranges[period:]:
        value = ((period - 1) * value + item) / period
    return value


def bollinger(values: Iterable[float], period: int = 20, deviations: float = 2.0) -> dict[str, float]:
    data = _series(values, minimum=period, name="bollinger")
    if period < 2 or deviations <= 0:
        raise MarketDataValidationError("invalid_bollinger_parameters")
    window = data[-period:]
    middle = mean(window)
    sigma = pstdev(window)
    return {"lower": middle - deviations * sigma, "middle": middle, "upper": middle + deviations * sigma, "bandwidth": (2 * deviations * sigma / middle) if middle else 0.0}


def volume_ratio(volumes: Iterable[float], period: int = 20) -> float:
    data = _series(volumes, minimum=period + 1, name="volume")
    baseline = mean(data[-period-1:-1])
    if baseline == 0:
        raise MarketDataValidationError("volume_baseline_is_zero")
    return data[-1] / baseline


def pct_return(values: Iterable[float], periods: int = 1) -> float:
    data = _series(values, minimum=periods + 1, name="returns")
    if periods < 1 or data[-periods - 1] == 0:
        raise MarketDataValidationError("invalid_return_period_or_base")
    return (data[-1] / data[-periods - 1] - 1.0) * 100.0


def correlation(left: Iterable[float], right: Iterable[float]) -> float:
    x, y = _series(left, minimum=2, name="left_returns"), _series(right, minimum=2, name="right_returns")
    if len(x) != len(y):
        raise MarketDataValidationError("correlation_series_must_be_aligned")
    mx, my = mean(x), mean(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    denom = sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    if denom == 0:
        raise MarketDataValidationError("correlation_undefined_for_constant_series")
    return sum(a*b for a, b in zip(dx, dy)) / denom
