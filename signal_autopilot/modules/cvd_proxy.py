"""OHLCV-only CVD proxy. This is an estimate, not aggressor-side trade data."""
from __future__ import annotations

from typing import Any

CVD_SOURCE = "PROXY_OHLCV"


def candle_delta(bar: dict[str, Any]) -> float:
    """Estimate buy/sell volume from close location within the candle range.

    buy_volume = volume * (close-low)/(high-low)
    sell_volume = volume - buy_volume
    delta = buy_volume - sell_volume

    A zero-range candle has no directional information and contributes zero.
    """
    high = float(bar["high"])
    low = float(bar["low"])
    close = float(bar["close"])
    volume = float(bar["volume"])
    if volume < 0 or high < low or not all(map(_finite, (high, low, close, volume))):
        raise ValueError("invalid_ohlcv_for_cvd_proxy")
    span = high - low
    if span == 0:
        return 0.0
    close_location = min(1.0, max(0.0, (close - low) / span))
    buy_volume = volume * close_location
    sell_volume = volume - buy_volume
    return buy_volume - sell_volume


def _finite(value: float) -> bool:
    import math
    return math.isfinite(value)


def calculate_cvd_proxy(
    bars: list[dict[str, Any]], lookback: int = 4
) -> dict[str, Any]:
    if lookback < 1:
        raise ValueError("lookback_must_be_positive")
    selected = bars[-lookback:]
    deltas = [candle_delta(bar) for bar in selected]
    buy_volume = sum(
        float(bar["volume"]) * (
            0.5 if float(bar["high"]) == float(bar["low"])
            else min(1.0, max(0.0, (float(bar["close"])-float(bar["low"])) /
                                  (float(bar["high"])-float(bar["low"]))))
        )
        for bar in selected
    )
    total_volume = sum(float(bar["volume"]) for bar in selected)
    sell_volume = total_volume - buy_volume
    return {
        "delta": sum(deltas),
        "buy_volume": buy_volume,
        "sell_volume": sell_volume,
        "source": CVD_SOURCE,
        "CVD_SOURCE": CVD_SOURCE,
        "lookback_bars": len(selected),
        "method": "OHLCV_CLOSE_LOCATION_ESTIMATE",
        "is_real_aggressor_flow": False,
    }

# Delivery contract marker: CVD_SOURCE is always explicit and PROXY_OHLCV is never represented as real aggressor flow.
