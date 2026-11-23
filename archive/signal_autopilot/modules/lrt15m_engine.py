"""موتور LRT-15m؛ خروجی تا کالیبراسیون فقط UNCALIBRATED است."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

# اجرای مستقیم این فایل از ریشهٔ مخزن نیز باید importهای محلی را پیدا کند.
_current_file = Path(__file__).resolve()
_package_root = _current_file.parent.parent  # signal_autopilot/
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy
from modules.lfs_v2 import calculate_lfs_v2


LFS_WEIGHTS = {
    "liquidity_sweep": 0.25,
    "order_block": 0.20,
    "fair_value_gap": 0.20,
    "ichimoku_bias": 0.20,
    "cvd": 0.15,
}
TIER_A_BRIER_MAX = 0.25
MIN_LFS_SCORE_REAL_CVD = 0.70
MIN_LFS_SCORE_PROXY_CVD = 0.30
CROSS_LOOKBACK = 10
MAX_ZONE_DISTANCE_PCT = 0.80
PRODUCTION_MODE_THRESHOLD = 80
RESEARCH_MODE_THRESHOLD = 60
# نام‌های سازگاری فقط به ثابت‌های اصلی ارجاع می‌دهند.
WATCHLIST_CONFLUENCE_THRESHOLD = RESEARCH_MODE_THRESHOLD
STAGE1_WATCHLIST_CONFLUENCE_THRESHOLD = PRODUCTION_MODE_THRESHOLD
MONITORING_CONFLUENCE_THRESHOLD = RESEARCH_MODE_THRESHOLD
ICHIMOKU_TENKAN = 9
ICHIMOKU_KIJUN = 26
ICHIMOKU_SENKOU_B = 52
ATR_PERIOD = 14


def midpoint(highs: list[float], lows: list[float], end: int, period: int) -> float | None:
    start = end - period + 1
    if start < 0:
        return None
    return (max(highs[start:end + 1]) + min(lows[start:end + 1])) / 2.0


def ichimoku(bars: list[dict[str, float]]) -> dict[str, float | None]:
    highs = [x["high"] for x in bars]
    lows = [x["low"] for x in bars]
    idx = len(bars) - 1
    tenkan = midpoint(highs, lows, idx, ICHIMOKU_TENKAN)
    kijun = midpoint(highs, lows, idx, ICHIMOKU_KIJUN)
    cloud_idx = idx - ICHIMOKU_KIJUN
    span_a = span_b = None
    if cloud_idx >= 0:
        t_old = midpoint(highs, lows, cloud_idx, ICHIMOKU_TENKAN)
        k_old = midpoint(highs, lows, cloud_idx, ICHIMOKU_KIJUN)
        b_old = midpoint(highs, lows, cloud_idx, ICHIMOKU_SENKOU_B)
        if t_old is not None and k_old is not None:
            span_a = (t_old + k_old) / 2.0
        span_b = b_old
    return {"tenkan": tenkan, "kijun": kijun, "span_a": span_a, "span_b": span_b}


def atr(bars: list[dict[str, float]], period: int = ATR_PERIOD) -> float | None:
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(len(bars) - period, len(bars)):
        current, previous = bars[i], bars[i - 1]
        trs.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    return sum(trs) / len(trs)


def aggregate_bars(rows: list[dict[str, Any]], bars_per_group: int) -> list[dict[str, float]]:
    output = []
    bucket: list[dict[str, Any]] = []
    current_key = None
    for row in rows:
        key = int(row["open_time"]) // (900_000 * bars_per_group)
        if current_key is not None and key != current_key:
            if len(bucket) == bars_per_group:
                output.append(_merge_bucket(bucket))
            bucket = []
        current_key = key
        bucket.append(row)
    if len(bucket) == bars_per_group:
        output.append(_merge_bucket(bucket))
    return output


def _merge_bucket(bucket: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "open": float(bucket[0]["open"]), "high": max(float(x["high"]) for x in bucket),
        "low": min(float(x["low"]) for x in bucket), "close": float(bucket[-1]["close"]),
        "volume": sum(float(x["volume"]) for x in bucket),
        "taker_buy_base": sum(float(x.get("taker_buy_base", 0)) for x in bucket),
        "open_time": int(bucket[0]["open_time"]),
    }


def detect_sweep(
    bars: list[dict[str, Any]], lookback: int = 20, max_candles_ago: int = 10
) -> dict[str, Any]:
    """Sweep را در کندل جاری تا ۱۰ کندل بسته‌شدهٔ قبلی جست‌وجو می‌کند."""
    empty = {
        "bullish": False, "bearish": False, "candles_ago": None,
        "swept_level": None, "sweep_type": None,
        "swept_low": None, "swept_high": None,
    }
    if lookback < 1 or max_candles_ago < 0 or len(bars) < lookback + 1:
        return empty

    for candles_ago in range(0, max_candles_ago + 1):
        idx = len(bars) - 1 - candles_ago
        if idx < lookback:
            continue
        previous = bars[idx - lookback:idx]
        current = bars[idx]
        prior_low = min(float(x["low"]) for x in previous)
        prior_high = max(float(x["high"]) for x in previous)

        if float(current["low"]) < prior_low and float(current["close"]) > prior_low:
            return {
                "bullish": True, "bearish": False, "candles_ago": candles_ago,
                "swept_level": prior_low, "sweep_type": "BULLISH",
                "swept_low": prior_low, "swept_high": None,
            }
        if float(current["high"]) > prior_high and float(current["close"]) < prior_high:
            return {
                "bullish": False, "bearish": True, "candles_ago": candles_ago,
                "swept_level": prior_high, "sweep_type": "BEARISH",
                "swept_low": None, "swept_high": prior_high,
            }
    return empty

def detect_order_block(bars: list[dict[str, Any]], direction: str, atr_value: float | None) -> bool:
    if atr_value is None or len(bars) < 8:
        return False
    current = bars[-1]
    lookback = bars[-8:-2]
    displacement = 1.2 * atr_value
    if direction == "BUY":
        for candle in reversed(lookback):
            if candle["close"] < candle["open"] and current["close"] > candle["high"] + displacement:
                return current["low"] <= candle["high"] and current["close"] >= candle["open"]
    else:
        for candle in reversed(lookback):
            if candle["close"] > candle["open"] and current["close"] < candle["low"] - displacement:
                return current["high"] >= candle["low"] and current["close"] <= current["open"]
    return False


def detect_fvg(bars: list[dict[str, Any]], direction: str) -> bool:
    if len(bars) < 3:
        return False
    current = bars[-1]
    left = bars[-3]
    if direction == "BUY":
        return current["low"] > left["high"] and current["close"] >= left["high"]
    return current["high"] < left["low"] and current["close"] <= left["low"]



def tenkan_kijun_cross(
    bars: list[dict[str, Any]], direction: str, lookback: int = CROSS_LOOKBACK
) -> bool:
    """تقاطع تأییدشدهٔ تنکان/کیجون در حداکثر ۱۰ کندل بسته‌شدهٔ ۱۵دقیقه‌ای."""
    if len(bars) < 30 or lookback < 1:
        return False

    def values(index: int) -> tuple[float, float]:
        tenkan_window = bars[index - 8:index + 1]
        kijun_window = bars[index - 25:index + 1]
        tenkan = (max(float(x["high"]) for x in tenkan_window)
                  + min(float(x["low"]) for x in tenkan_window)) / 2.0
        kijun = (max(float(x["high"]) for x in kijun_window)
                 + min(float(x["low"]) for x in kijun_window)) / 2.0
        return tenkan, kijun

    start = max(26, len(bars) - lookback)
    for index in range(start, len(bars)):
        previous_tenkan, previous_kijun = values(index - 1)
        current_tenkan, current_kijun = values(index)
        if direction == "BUY" and previous_tenkan <= previous_kijun and current_tenkan > current_kijun:
            return True
        if direction == "SELL" and previous_tenkan >= previous_kijun and current_tenkan < current_kijun:
            return True
    return False


def zone_distance(
    bars: list[dict[str, Any]], direction: str, atr_value: float | None
) -> dict[str, Any]:
    """نزدیک‌ترین فاصلهٔ قیمت بسته‌شده تا ناحیهٔ OB/FVG را به درصد برمی‌گرداند."""
    if len(bars) < 20:
        return {"zone_type": "NONE", "distance_pct": None, "within_limit": False}
    current = bars[-1]
    close = float(current["close"])
    if close <= 0:
        return {"zone_type": "NONE", "distance_pct": None, "within_limit": False}
    zones: list[tuple[str, float, float]] = []
    displacement = 1.2 * atr_value if atr_value is not None else 0.0
    atr_threshold = 0.3 * atr_value if atr_value is not None else 0.0

    # OB: بررسی ۱۸ کندل قبلی، با حفظ displacement برابر ۱.۲ ATR
    for candle in bars[-20:-2]:
        if direction == "BUY" and float(candle["close"]) < float(candle["open"]) and close > float(candle["high"]) + displacement:
            zones.append(("OB", float(candle["low"]), float(candle["high"])))
        elif direction == "SELL" and float(candle["close"]) > float(candle["open"]) and close < float(candle["low"]) - displacement:
            zones.append(("OB", float(candle["low"]), float(candle["high"])))

    # FVG فقط با اندازهٔ شکاف بیش از ۰.۳ ATR ثبت می‌شود.
    left = bars[-3]
    if direction == "BUY":
        gap = float(current["low"]) - float(left["high"])
        if gap > atr_threshold:
            zones.append(("FVG", float(left["high"]), float(current["low"])))
    elif direction == "SELL":
        gap = float(left["low"]) - float(current["high"])
        if gap > atr_threshold:
            zones.append(("FVG", float(current["high"]), float(left["low"])))

    if not zones:
        return {"zone_type": "NONE", "distance_pct": None, "within_limit": False}
    distances: list[tuple[float, str]] = []
    for zone_type, lower, upper in zones:
        if lower <= close <= upper:
            distance = 0.0
        elif close > upper:
            distance = (close - upper) / close * 100.0
        else:
            distance = (lower - close) / close * 100.0
        distances.append((distance, zone_type))
    distance, zone_type = min(distances, key=lambda item: item[0])
    return {
        "zone_type": zone_type,
        "distance_pct": round(distance, 6),
        "within_limit": distance <= MAX_ZONE_DISTANCE_PCT,
    }

def cvd_delta_from_aggtrades(trades: list[dict[str, Any]]) -> float:
    """aggTrade: m=True یعنی خریدار maker و فروشنده aggressor است."""
    delta = 0.0
    for trade in trades:
        qty = float(trade.get("qty", trade.get("quantity", 0)))
        buyer_is_maker = bool(trade.get("is_buyer_maker", trade.get("m", False)))
        delta += -qty if buyer_is_maker else qty
    return delta


def cvd_proxy_from_klines(bars: list[dict[str, Any]], lookback: int = 4) -> float:
    """Compatibility adapter: OHLCV close-location proxy, never real CVD."""
    return float(calculate_cvd_proxy(bars, lookback)["delta"])


def _bias_4h(bars_4h: list[dict[str, float]]) -> tuple[str, dict[str, float | None]]:
    values = ichimoku(bars_4h)
    a, b = values["span_a"], values["span_b"]
    close = bars_4h[-1]["close"] if bars_4h else 0.0
    if a is None or b is None:
        return "UNKNOWN", values
    top, bottom = max(a, b), min(a, b)
    if close > top:
        return "BULLISH", values
    if close < bottom:
        return "BEARISH", values
    return "RANGE", values


def _bias_1h(bars_1h: list[dict[str, float]]) -> tuple[str, dict[str, float | None]]:
    values = ichimoku(bars_1h)
    kijun = values["kijun"]
    if kijun is None or not bars_1h:
        return "UNKNOWN", values
    close = bars_1h[-1]["close"]
    return ("BULLISH" if close > kijun else "BEARISH"), values


def higher_timeframe_gate(direction: str, bias4: str, bias1: str) -> tuple[bool, str]:
    """Bias مخالف یا نامشخص فقط WATCHLIST می‌دهد، نه BUY_NOW/SELL_NOW."""
    expected = "BULLISH" if direction == "BUY" else "BEARISH"
    opposite = "BEARISH" if direction == "BUY" else "BULLISH"
    if bias4 == opposite:
        return False, "WATCHLIST_4H_KUMO_OPPOSITE"
    if bias1 == opposite:
        return False, "WATCHLIST_1H_KIJUN_OPPOSITE"
    if bias4 == expected and bias1 == expected:
        return True, "BIAS_CONFIRMED"
    return False, "WATCHLIST_HIGHER_TF_BIAS_INCOMPLETE"


def score_stage1_confluence(
    components: dict[str, bool],
    cvd_source: str,
    cvd_aligned: bool,
) -> dict[str, Any]:
    """امتیاز پنج‌جزئی Stage 1؛ CVD فقط کیفیت Zone Reaction را تعدیل می‌کند."""
    zone_points = 0
    if components.get("zone_reaction", False):
        if cvd_source == "AGGTRADES_REAL":
            zone_points = 20 if cvd_aligned else 0
        else:
            zone_points = 12
    points = {
        "bias_4h": 20 if components.get("bias_4h", False) else 0,
        "bias_1h": 20 if components.get("bias_1h", False) else 0,
        "sweep": 20 if components.get("sweep", False) else 0,
        "zone_reaction": zone_points,
        "tenkan_kijun_cross_10": 20 if components.get("cross", False) else 0,
    }
    raw_score = sum(points.values())
    # Tierها فقط روی مضرب‌های ۲۰ تصمیم می‌گیرند؛ امتیاز خام حفظ می‌شود.
    tier_score = (raw_score // 20) * 20
    if tier_score >= 100:
        decision, tier, mode, research_decision = "WATCHLIST", "A", "PRODUCTION", None
    elif tier_score >= PRODUCTION_MODE_THRESHOLD:
        decision, tier, mode, research_decision = "WATCHLIST", "B", "PRODUCTION", None
    elif tier_score >= RESEARCH_MODE_THRESHOLD:
        # امتیاز ۶۰ تا ۷۹ فقط برای پژوهش است؛ وارد مسیر تولیدی نمی‌شود.
        decision, tier, mode, research_decision = "RESEARCH_WATCHLIST", None, "RESEARCH", "RESEARCH_WATCHLIST"
    else:
        decision, tier, mode, research_decision = "NO_TRADE", None, "NONE", None
    return {
        "raw_score": raw_score,
        "tier_score": tier_score,
        "points": points,
        "decision": decision,
        "tier": tier,
        "mode": mode,
        "research_decision": research_decision,
    }


def evaluate_stage1_decision(
    data_valid: bool,
    inside_kumo: bool,
    lfs_score: float,
    cvd_source: str,
    components: dict[str, bool],
    cvd_aligned: bool = False,
) -> dict[str, Any]:
    """سه Veto قطعی و سپس امتیازدهی؛ هیچ مسیر BUY_NOW/SELL_NOW ندارد."""
    if not data_valid:
        return {"veto": "DATA_INSUFFICIENT", "decision": "NO_TRADE", "mode": "NONE", "research_decision": None, "score": None}
    if inside_kumo:
        return {"veto": "INSIDE_KUMO_4H", "decision": "NO_TRADE", "mode": "NONE", "research_decision": None, "score": None}
    threshold = 0.30  # LFS_v2: آستانه برای FULL و PARTIAL_PROXY یکسان است.
    if float(lfs_score) < threshold:
        return {
            "veto": "LFS_BELOW_THRESHOLD",
            "decision": "NO_TRADE",
            "mode": "NONE",
            "research_decision": None,
            "score": None,
            "lfs_threshold": threshold,
        }
    scored = score_stage1_confluence(components, cvd_source, cvd_aligned)
    return {"veto": "PASS", **scored, "lfs_threshold": threshold}


def _aggregate_hourly_to_4h(bars_1h: list[dict[str, Any]]) -> list[dict[str, float]]:
    """تجمیع 1H به 4H؛ منطق شاخص‌ها ثابت می‌ماند و فقط منبع تاریخچه عوض می‌شود."""
    buckets: dict[int, list[dict[str, Any]]] = {}
    for row in bars_1h:
        buckets.setdefault(int(row["open_time"]) // 14_400_000, []).append(row)
    output = []
    for key in sorted(buckets):
        bucket = sorted(buckets[key], key=lambda item: int(item["open_time"]))
        if len(bucket) != 4 or any(
            int(bucket[i]["open_time"]) - int(bucket[i - 1]["open_time"]) != 3_600_000
            for i in range(1, 4)
        ):
            continue
        output.append({
            "open_time": int(bucket[0]["open_time"]), "open": float(bucket[0]["open"]),
            "high": max(float(x["high"]) for x in bucket),
            "low": min(float(x["low"]) for x in bucket),
            "close": float(bucket[-1]["close"]),
            "volume": sum(float(x["volume"]) for x in bucket),
            "taker_buy_base": sum(float(x.get("taker_buy_base", 0.0)) for x in bucket),
        })
    return output


def _continuous_bars(bars: list[dict[str, Any]], interval_ms: int, required: int) -> bool:
    if len(bars) < required:
        return False
    tail = bars[-required:]
    return all(
        int(tail[i]["open_time"]) - int(tail[i - 1]["open_time"]) == interval_ms
        for i in range(1, len(tail))
    )


def evaluate_stage1_symbol(
    symbol: str,
    rows: list[dict[str, Any]],
    aggtrades: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """ارزیابی Stage 1؛ LFS_v2 به‌صورت قطعی در Python محاسبه می‌شود."""
    stats_rows = getattr(rows, "stats_1h", None) or []
    okx_metrics = getattr(rows, "okx_metrics", None) or {}
    base = {
        "symbol": symbol, "direction": None, "veto": "DATA_INSUFFICIENT",
        "decision": "NO_TRADE", "tier": None, "raw_score": None,
        "tier_score": None, "points": {}, "components": {},
        "lfs_score": None, "lfs_source": "LFS_V2",
        "lfs_coverage_pct": 0.0, "lfs_status": "INSUFFICIENT",
        "lfs_components": {}, "api_status": okx_metrics.get("api_status", {}),
        "rows_available": len(rows),
    }
    if len(rows) < 500:
        return {**base, "reason": f"INSUFFICIENT_CLOSED_15M_BARS:{len(rows)}"}
    try:
        bars = []
        for row in rows:
            bar = {}
            for key, value in row.items():
                bar[key] = int(value) if key == "open_time" else (
                    str(value) if key in {"data_source", "cvd_source"} else float(value)
                )
            if bar["high"] < bar["low"] or bar["close"] <= 0 or bar["open"] <= 0:
                return {**base, "reason": "INVALID_OHLC"}
            bars.append(bar)
        bars.sort(key=lambda item: item["open_time"])
        if not _continuous_bars(bars, 900_000, 500):
            return {**base, "reason": "15M_GAP_OR_DUPLICATE"}

        bars_1h = []
        for row in stats_rows:
            bar = {
                "open_time": int(row["open_time"]), "open": float(row["open"]),
                "high": float(row["high"]), "low": float(row["low"]),
                "close": float(row["close"]), "volume": float(row["volume"]),
            }
            if bar["high"] >= bar["low"] and bar["close"] > 0 and bar["open"] > 0:
                bars_1h.append(bar)
        bars_1h.sort(key=lambda item: item["open_time"])
        if not bars_1h:
            bars_1h = aggregate_bars(bars, 4)  # سازگاری قدیمی؛ برای LFS تاریخچه کافی نیست.

        lfs_data = calculate_lfs_v2(
            symbol, bars, bars_1h,
            funding_rate=okx_metrics.get("funding_rate"),
            oi_1h=okx_metrics.get("oi_1h"), oi_1d=okx_metrics.get("oi_1d"),
            long_short_ratio=okx_metrics.get("long_short_ratio"),
        )
        base.update(lfs_data)
        base["lfs_source"] = "LFS_V2"

        # پوشش ناکافی باید پیش از تبدیل امتیاز None و هر محاسبهٔ وابسته متوقف شود.
        if lfs_data["lfs_status"] == "INSUFFICIENT":
            return {
                **base,
                "veto": "LFS_INSUFFICIENT_COVERAGE",
                "decision": "NO_TRADE",
                "reason": "LFS_INSUFFICIENT_COVERAGE",
                "lfs_score": None,
            }

        if not _continuous_bars(bars_1h, 3_600_000, 80):
            return {**base, "reason": "DATA_INSUFFICIENT_1H"}
        bars_4h = _aggregate_hourly_to_4h(bars_1h)
        if not _continuous_bars(bars_4h, 14_400_000, 79):
            return {**base, "reason": "DATA_INSUFFICIENT_4H"}

        bias4, cloud = _bias_4h(bars_4h)
        bias1, _ = _bias_1h(bars_1h)
        span_a, span_b = cloud.get("span_a"), cloud.get("span_b")
        current = bars[-1]
        if span_a is None or span_b is None or bias1 == "UNKNOWN":
            return {**base, "reason": "HTF_INDICATOR_UNAVAILABLE"}
        cloud_low, cloud_high = min(span_a, span_b), max(span_a, span_b)
        if cloud_low <= float(current["close"]) <= cloud_high:
            return {
                **base, "veto": "INSIDE_KUMO_4H", "reason": "INSIDE_KUMO_4H",
                "higher_timeframe_bias": {"4h_kumo": bias4, "1h_kijun": bias1},
                "price_vs_kumo": "INSIDE_KUMO",
            }

        cvd_value = None
        cvd_source = CVD_SOURCE
        if aggtrades is not None:
            current_bucket = int(current["open_time"])
            bucket_rows = [x for x in aggtrades if int(x.get("bucket_open_time", -1)) == current_bucket]
            if bucket_rows:
                cvd_value = sum(float(x.get("delta", 0.0)) for x in bucket_rows)
                cvd_source = "AGGTRADES_REAL"
            else:
                raw_rows = [
                    x for x in aggtrades
                    if current_bucket <= int(x.get("timestamp", x.get("T", -1))) < current_bucket + 900_000
                ]
                if raw_rows:
                    cvd_value = cvd_delta_from_aggtrades(raw_rows)
                    cvd_source = "AGGTRADES_REAL"
        if cvd_value is None:
            cvd_value = cvd_proxy_from_klines(bars)
            cvd_source = CVD_SOURCE
        cvd_sign = "BUY" if cvd_value > 0 else "SELL" if cvd_value < 0 else "NEUTRAL"
        atr_value = atr(bars)
        sweep_data = detect_sweep(bars, lookback=20, max_candles_ago=10)
        candidates, rejected_lfs = [], []

        for direction in ("BUY", "SELL"):
            expected = "BULLISH" if direction == "BUY" else "BEARISH"
            bias4_ok, bias1_ok = bias4 == expected, bias1 == expected
            sweep_ok = bool(sweep_data["bullish"] if direction == "BUY" else sweep_data["bearish"])
            ob_ok = detect_order_block(bars, direction, atr_value)
            fvg_ok = detect_fvg(bars, direction)
            zone = zone_distance(bars, direction, atr_value)
            zone_ok = (ob_ok or fvg_ok) and bool(zone["within_limit"])
            cross_ok = tenkan_kijun_cross(bars, direction, CROSS_LOOKBACK)
            cvd_aligned = cvd_sign == direction
            components = {
                "bias_4h": bias4_ok, "bias_1h": bias1_ok, "sweep": sweep_ok,
                "sweep_candles_ago": sweep_data.get("candles_ago"),
                "zone_reaction": zone_ok, "cross": cross_ok,
            }
            decision = evaluate_stage1_decision(
                True, False, float(lfs_data["lfs_score"]), cvd_source, components, cvd_aligned
            )
            record = {
                **decision, "symbol": symbol, "direction": direction,
                "lfs_score": lfs_data["lfs_score"], "lfs_source": "LFS_V2",
                "lfs_coverage_pct": lfs_data["lfs_coverage_pct"],
                "lfs_status": lfs_data["lfs_status"],
                "lfs_components": lfs_data["lfs_components"],
                "api_status": lfs_data["api_status"], "components": components,
                "cvd": {"delta": round(cvd_value, 8), "source": cvd_source},
                "zone_type": zone["zone_type"], "zone_distance_pct": zone["distance_pct"],
                "higher_timeframe_bias": {"4h_kumo": bias4, "1h_kijun": bias1},
                "price_vs_kumo": "ABOVE_KUMO" if float(current["close"]) > cloud_high else "BELOW_KUMO",
                "data_sources": sorted(
                    {str(x.get("data_source", "UNAVAILABLE")) for x in bars}
                    | {str(x.get("data_source", "UNAVAILABLE")) for x in bars_1h}
                ),
                "rows_available": len(bars), "stats_1h_rows_available": len(bars_1h),
            }
            if decision["veto"] == "PASS":
                entry = float(current["close"])
                stop = float(current["low"]) if direction == "BUY" else float(current["high"])
                risk = abs(entry - stop)
                if risk <= 0:
                    record.update({"decision": "NO_TRADE", "reason": "INVALID_RISK_DISTANCE"})
                else:
                    sign = 1 if direction == "BUY" else -1
                    record.update({
                        "entry": entry, "stop_loss": stop, "take_profit": entry + sign * 2.0 * risk,
                        "rr": 2.0,
                        "hypothesis": f"{direction} setup: 4H/1H bias, liquidity sweep, OB/FVG zone reaction and 10-candle Tenkan/Kijun cross confluence",
                        "falsification": "15m close beyond the reference stop-loss or invalidation of the aligned HTF bias",
                    })
                candidates.append(record)
            else:
                rejected_lfs.append(record)

        if not candidates:
            direction_diagnostics = [
                {
                    key: item.get(key) for key in (
                        "direction", "veto", "decision", "reason", "components",
                        "points", "raw_score", "tier_score", "lfs_score",
                        "lfs_status", "higher_timeframe_bias", "zone_type",
                        "zone_distance_pct", "price_vs_kumo",
                    )
                }
                for item in rejected_lfs
            ]
            if rejected_lfs:
                best = max(rejected_lfs, key=lambda item: float(item["lfs_score"]))
                return {
                    **base, **best, "veto": best["veto"], "decision": "NO_TRADE",
                    "reason": best.get("veto", "LFS_BELOW_THRESHOLD"),
                    "direction_candidates": direction_diagnostics,
                }
            return {
                **base, "reason": "NO_DIRECTION_CANDIDATE",
                "direction_candidates": direction_diagnostics,
            }
        candidates.sort(key=lambda item: (
            int(item.get("tier_score") or 0), int(item.get("raw_score") or 0),
            float(item.get("lfs_score") or 0),
        ), reverse=True)
        if len(candidates) > 1 and (
            candidates[0].get("tier_score") == candidates[1].get("tier_score")
            and candidates[0].get("raw_score") == candidates[1].get("raw_score")
        ):
            return {
                **base, "veto": "PASS", "decision": "NO_TRADE", "reason": "DIRECTION_CONFLICT",
                "direction_candidates": [
                    {
                        k: item.get(k)
                        for k in (
                            "direction", "raw_score", "tier_score", "lfs_score",
                            "veto", "decision", "components", "points", "zone_type",
                            "zone_distance_pct", "higher_timeframe_bias", "cvd",
                        )
                    }
                    for item in candidates
                ],
            }
        return candidates[0]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        return {**base, "reason": f"DATA_VALIDATION_ERROR:{type(exc).__name__}:{str(exc)[:100]}"}


def _no_setup(symbol: str, reason: str, rows: int) -> dict[str, Any]:
    return {
        "symbol": symbol, "timeframe": "15m", "decision": "NO_QUALIFIED_SETUP",
        "tier": None, "reason": reason, "rows_available": rows,
        "confidence": "NOT_CALIBRATED", "brier_score": "NOT_CALIBRATED",
        "ev_net": None, "ev_status": "NOT_CALIBRATED",
        "ev_reason": "NO_CALIBRATED_WIN_PROBABILITY_OR_PAYOFF_DISTRIBUTION",
        "ev": "NOT_CALCULATED_CALIBRATION_AND_COST_INPUTS_UNAVAILABLE",
        "status": "UNCALIBRATED",
    }


def load_parquet(path: Path) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq
    return pq.read_table(path).to_pylist()


def run(data_dir: Path, output_path: Path, universe_path: Path,
        aggtrades_dir: Path | None = None) -> dict[str, Any]:
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = universe["symbols"]
    results = []
    for symbol in symbols:
        path = data_dir / f"{symbol}_15m_730d.parquet"
        if not path.exists():
            # downloader file naming is date-stamped; resolve exactly one matching file.
            matches = sorted(data_dir.glob(f"{symbol}_15m_*.parquet"))
            path = matches[-1] if matches else path
        if not path.exists():
            results.append(_no_setup(symbol, "MARKET_DATA_DEGRADED_15M_FILE_MISSING", 0))
            continue
        rows = load_parquet(path)
        trades = None
        if aggtrades_dir:
            trade_path = aggtrades_dir / f"{symbol}_aggtrades.parquet"
            if trade_path.exists():
                trades = load_parquet(trade_path)
        results.append(evaluate_stage1_symbol(symbol, rows, trades))
    candidates = [x for x in results if x.get("direction") in ("BUY", "SELL")]
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "1b-test", "engine": "LRT-15m",
        "universe_count": len(symbols), "symbols_analyzed": len(results),
        "candidate_setups": len(candidates),
        "target_signals_per_day": "2-4 (target only; not guaranteed)",
        "lfs_weights": LFS_WEIGHTS, "brier_tier_a_threshold": TIER_A_BRIER_MAX,
        "calibration_status": "UNCALIBRATED",
        "ev_status": "NOT_CALCULATED_UNTIL_CALIBRATED_PROBABILITY_AND_COSTS_EXIST",
        "cvd_sources": sorted({x.get("cvd", {}).get("source", x.get("cvd_source", "UNAVAILABLE")) for x in results}),
        "data_sources": sorted({source for x in results for source in x.get("data_sources", [])}),
        "signals": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STAGE1B_LRT15M " + json.dumps({
        "symbols": len(results), "candidate_setups": len(candidates),
        "calibration": report["calibration_status"], "status": "UNCALIBRATED",
    }), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--universe", default="signal_autopilot/data/stage1b_universe_27.json")
    parser.add_argument("--aggtrades-dir")
    args = parser.parse_args()
    run(Path(args.data_dir), Path(args.output), Path(args.universe),
        Path(args.aggtrades_dir) if args.aggtrades_dir else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
