"""Conservative LFS1 proxy from OHLCV ATR and volume ratio; never REAL."""
from __future__ import annotations

from statistics import median
from typing import Any


def _percentile_rank(value: float, history: list[float]) -> float:
    if not history:
        raise ValueError("percentile_history_missing")
    return sum(1 for item in history if item <= value) / len(history)


def calculate_lfs1_proxy(candles: list[dict[str, Any]] | None,
                         threshold: float = 0.90) -> dict[str, Any]:
    """امتیاز نازکی نقدینگی را فقط به‌صورت PROXY از ATR و نسبت حجم برآورد می‌کند."""
    if not candles or len(candles) < 52:
        return {"status": "UNAVAILABLE", "data_class": "PROXY",
                "reason": "insufficient_ohlcv_bars", "required_bars": 52,
                "observed_bars": len(candles or [])}
    ordered = sorted(candles, key=lambda row: int(row.get("timestamp") or 0))
    try:
        highs = [float(row["high"]) for row in ordered]
        lows = [float(row["low"]) for row in ordered]
        closes = [float(row["close"]) for row in ordered]
        volumes = [float(row["volume"]) for row in ordered]
        if any(value <= 0 for value in closes) or any(value < 0 for value in volumes):
            raise ValueError("invalid_price_or_volume")
        true_ranges = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]))
            for i in range(1, len(ordered))
        ]
        atr_pct = [
            (sum(true_ranges[end - 14:end]) / 14) / closes[end]
            for end in range(14, len(closes))
        ]
        volume_24h = [sum(volumes[end - 23:end + 1]) for end in range(23, len(volumes))]
        if len(atr_pct) < 2 or len(volume_24h) < 25:
            raise ValueError("insufficient_feature_history")
        current_atr = atr_pct[-1]
        current_volume = volume_24h[-1]
        baseline_volume = median(volume_24h[:-1])
        if baseline_volume <= 0:
            raise ValueError("invalid_volume_baseline")
        volume_ratio = current_volume / baseline_volume
        atr_rank = _percentile_rank(current_atr, atr_pct[:-1])
        low_volume_rank = 1.0 - _percentile_rank(current_volume, volume_24h[:-1])
        score = (atr_rank + low_volume_rank) / 2.0
        is_thin = score >= threshold and atr_rank >= 0.85 and low_volume_rank >= 0.85
        return {
            "status": "HIGH_THINNESS_PROXY" if is_thin else "NORMAL_PROXY",
            "data_class": "PROXY",
            "method": "ATR14_PERCENTILE_AND_INVERSE_24H_VOLUME_PERCENTILE",
            "score": round(score, 6), "threshold": threshold,
            "atr_percentile": round(atr_rank, 6),
            "low_volume_percentile": round(low_volume_rank, 6),
            "volume_ratio_vs_rolling_median": round(volume_ratio, 6),
            "lookback_bars": len(ordered), "lookback_hours": len(ordered),
            "calibration": "NOT_CALIBRATED", "real_orderbook_used": False,
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return {"status": "UNAVAILABLE", "data_class": "PROXY",
                "reason": type(exc).__name__ + ":" + str(exc)[:160],
                "real_orderbook_used": False}


def aggregate_lfs_v2(components: dict[str, float | None]) -> dict[str, Any]:
    """LFS وزنی را فقط وقتی هر پنج جزء حاضر و معتبر باشند محاسبه می‌کند."""
    weights = {"LFS1": 0.25, "LFS2": 0.20, "LFS3": 0.20, "LFS4": 0.20, "LFS5": 0.15}
    missing = [name for name in weights if components.get(name) is None]
    invalid = [name for name, value in components.items()
               if name in weights and value is not None and not 0.0 <= float(value) <= 1.0]
    if missing or invalid:
        return {"status": "UNAVAILABLE", "data_class": "PARTIAL",
                "missing_components": missing, "invalid_components": invalid,
                "reason": "all_five_components_required_no_missing_to_zero"}
    score = sum(weights[name] * float(components[name]) for name in weights)
    return {"status": "AVAILABLE_PROXY", "score": round(score, 6),
            "data_class": "PROXY", "weights": weights, "calibration": "NOT_CALIBRATED"}
