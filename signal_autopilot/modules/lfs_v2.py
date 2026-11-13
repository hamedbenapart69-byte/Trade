"""محاسبهٔ LFS_v2؛ مستقل از موتور AI و با برچسب‌گذاری صریح دادهٔ واقعی/پروکسی."""
from __future__ import annotations

import math
from typing import Any, Iterable

WEIGHTS = {"LFS1": 0.25, "LFS2": 0.20, "LFS3": 0.20, "LFS4": 0.20, "LFS5": 0.15}
FUNDING_EXTREME_RATE = 0.0003  # 0.03%
HOURS_90D = 90 * 24
HOURS_30D = 30 * 24


def _clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def percentile(values: Iterable[float], q: float) -> float | None:
    """صدک خطی با درون‌یابی؛ q در بازهٔ 0 تا 100."""
    clean = sorted(float(x) for x in values if _finite(x) is not None)
    if not clean:
        return None
    q = _clip(q, 0.0, 100.0) / 100.0
    position = (len(clean) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return clean[low]
    fraction = position - low
    return clean[low] + (clean[high] - clean[low]) * fraction


def normalize_lfs1(current: float, p10: float, p90: float) -> float:
    """نرمال‌سازی مقاوم LFS1 بین صدک‌های ۱۰ و ۹۰."""
    if not all(math.isfinite(float(x)) for x in (current, p10, p90)) or p90 <= p10:
        return 0.0
    return _clip((float(current) - float(p10)) / (float(p90) - float(p10)))


def funding_extreme_score(funding_rate: float) -> float:
    return _clip(abs(float(funding_rate)) / FUNDING_EXTREME_RATE)


def empirical_percentile(current: float, history: Iterable[float]) -> float | None:
    """ECDF: نسبت مشاهدات تاریخی کوچک‌تر یا مساوی مقدار جاری."""
    values = [float(x) for x in history if _finite(x) is not None]
    if not values:
        return None
    return sum(1 for value in values if value <= float(current)) / len(values)


def rank_time_series(current: float, history: Iterable[float]) -> float | None:
    """نام صریح رتبهٔ زمانی برای استفادهٔ LFS3."""
    return empirical_percentile(current, history)


def bb_squeeze_score(current_width: float, p20: float, p50: float) -> float:
    """۱ تا p20؛ افت خطی تا صفر در p50؛ بالاتر از p50 صفر."""
    current_width, p20, p50 = float(current_width), float(p20), float(p50)
    if current_width <= p20:
        return 1.0
    if p50 <= p20 or current_width >= p50:
        return 0.0
    return _clip((p50 - current_width) / (p50 - p20))


def oi_drop_score(change: float) -> float:
    return _clip(abs(float(change)) / 0.10)


def _atr_last(bars: list[dict[str, Any]], period: int = 14) -> float | None:
    if len(bars) < period + 1:
        return None
    trs: list[float] = []
    for index in range(len(bars) - period, len(bars)):
        current, previous = bars[index], bars[index - 1]
        try:
            high, low, previous_close = float(current["high"]), float(current["low"]), float(previous["close"])
        except (KeyError, TypeError, ValueError):
            return None
        trs.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    return sum(trs) / len(trs)


def _bb_width_last(bars: list[dict[str, Any]], period: int = 20, deviations: float = 2.0) -> float | None:
    if len(bars) < period:
        return None
    try:
        closes = [float(row["close"]) for row in bars[-period:]]
    except (KeyError, TypeError, ValueError):
        return None
    middle = sum(closes) / period
    if middle <= 0:
        return None
    variance = sum((value - middle) ** 2 for value in closes) / period
    standard_deviation = math.sqrt(variance)
    upper = middle + deviations * standard_deviation
    lower = middle - deviations * standard_deviation
    return (upper - lower) / middle


def _rolling_sums(values: list[float], window: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        if index >= window - 1:
            output[index] = running
    return output


def _hourly_lfs1_distribution(bars_1h: list[dict[str, Any]]) -> tuple[list[float], float | None]:
    """توزیع ۹۰روزه؛ مخرج، میانگین حجم ۲۴ساعتهٔ روزانه در ۳۰ روز اخیر است."""
    if len(bars_1h) < HOURS_90D + 24:
        return [], None
    try:
        volumes = [float(row["volume"]) for row in bars_1h]
        closes = [float(row["close"]) for row in bars_1h]
    except (KeyError, TypeError, ValueError):
        return [], None
    if any(not math.isfinite(x) or x < 0 for x in volumes) or any(x <= 0 for x in closes):
        return [], None
    volume_24h = _rolling_sums(volumes, 24)
    recent_30d = [value for value in volume_24h[-HOURS_30D:] if value is not None]
    if len(recent_30d) < HOURS_30D:
        return [], None
    average_30d_24h_volume = sum(recent_30d) / len(recent_30d)
    if average_30d_24h_volume <= 0:
        return [], None

    values: list[float] = []
    start = max(len(bars_1h) - HOURS_90D, 14)
    for index in range(start, len(bars_1h)):
        if volume_24h[index] is None or closes[index] <= 0:
            continue
        atr_value = _atr_last(bars_1h[:index + 1], 14)
        if atr_value is None:
            continue
        values.append((atr_value / closes[index]) * (float(volume_24h[index]) / average_30d_24h_volume))
    return values, average_30d_24h_volume


def _hourly_bb_distribution(bars_1h: list[dict[str, Any]]) -> list[float]:
    if len(bars_1h) < HOURS_90D:
        return []
    start = max(19, len(bars_1h) - HOURS_90D)
    values: list[float] = []
    for index in range(start, len(bars_1h)):
        width = _bb_width_last(bars_1h[:index + 1])
        if width is not None and math.isfinite(width):
            values.append(width)
    return values


def _parse_oi_point(row: Any) -> tuple[int, float] | None:
    """پاسخ Rubik معمولاً آرایهٔ [ts, oi, vol] است؛ شیء را نیز می‌پذیریم."""
    try:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            timestamp, value = int(row[0]), float(row[1])
        elif isinstance(row, dict):
            timestamp = int(row.get("ts", row.get("timestamp")))
            value = float(row.get("oi", row.get("openInterest", row.get("open_interest"))))
        else:
            return None
    except (TypeError, ValueError):
        return None
    if timestamp <= 0 or not math.isfinite(value) or value <= 0:
        return None
    return timestamp, value


def _oi_points(rows: Any) -> list[tuple[int, float]]:
    if not isinstance(rows, (list, tuple)):
        return []
    points = [point for row in rows if (point := _parse_oi_point(row)) is not None]
    return sorted({timestamp: value for timestamp, value in points}.items())


def _oi_change_24h(rows: Any) -> float | None:
    points = _oi_points(rows)
    if len(points) < 2:
        return None
    latest_ts, latest_oi = points[-1]
    target = latest_ts - 24 * 60 * 60 * 1000
    candidates = [(abs(ts - target), oi) for ts, oi in points[:-1] if abs(ts - target) <= 2 * 60 * 60 * 1000]
    if not candidates:
        return None
    _, old_oi = min(candidates, key=lambda item: item[0])
    return (latest_oi - old_oi) / old_oi if old_oi > 0 else None


def _daily_oi_changes(rows: Any) -> list[float]:
    points = _oi_points(rows)
    output: list[float] = []
    for previous, current in zip(points, points[1:]):
        old_ts, old_oi = previous
        new_ts, new_oi = current
        if 20 * 60 * 60 * 1000 <= new_ts - old_ts <= 28 * 60 * 60 * 1000 and old_oi > 0:
            output.append((new_oi - old_oi) / old_oi)
    return output[-90:]


def _component(score: float | None, weight: float, status: str, value: Any = None, **extra: Any) -> dict[str, Any]:
    return {"score": score, "weight": weight, "status": status, "value": value, **extra}


def calculate_lfs_v2(
    symbol: str,
    bars_15m: list[dict[str, Any]],
    bars_1h: list[dict[str, Any]],
    *,
    funding_rate: float | None = None,
    oi_1h: Any = None,
    oi_1d: Any = None,
    long_short_ratio: float | None = None,
) -> dict[str, Any]:
    """محاسبهٔ پنج مؤلفه با وزن ثابت؛ وزن دادهٔ UNAVAILABLE حذف یا بازتوزیع نمی‌شود."""
    components: dict[str, dict[str, Any]] = {}
    api_status = {
        "funding": funding_rate is not None,
        "oi_1h": bool(_oi_points(oi_1h)),
        "oi_1d": bool(_oi_points(oi_1d)),
        "long_short_ratio": long_short_ratio is not None,
    }

    # LFS1: حجم ۲۴ساعتهٔ ۱۵m در برابر میانگین حجم ۲۴ساعتهٔ ۳۰ روز از 1H.
    lfs1_history, avg_30d_volume = _hourly_lfs1_distribution(bars_1h)
    p10, p90 = percentile(lfs1_history, 10), percentile(lfs1_history, 90)
    atr15 = _atr_last(bars_15m)
    try:
        close15 = float(bars_15m[-1]["close"])
        volume24_15 = sum(float(row["volume"]) for row in bars_15m[-96:])
    except (IndexError, KeyError, TypeError, ValueError):
        close15, volume24_15 = 0.0, 0.0
    lfs1_current = (
        (atr15 / close15) * (volume24_15 / avg_30d_volume)
        if atr15 is not None and close15 > 0 and avg_30d_volume and avg_30d_volume > 0
        and len(bars_15m) >= 96 else None
    )
    if lfs1_current is not None and p10 is not None and p90 is not None and p90 > p10:
        components["LFS1"] = _component(
            normalize_lfs1(lfs1_current, p10, p90), WEIGHTS["LFS1"], "PROXY",
            lfs1_current, p10=p10, p90=p90, average_30d_24h_volume=avg_30d_volume,
        )
    else:
        components["LFS1"] = _component(None, WEIGHTS["LFS1"], "UNAVAILABLE", lfs1_current)

    # LFS2: Funding جاری OKX؛ نرخ ۰.۰۳٪ امتیاز کامل می‌گیرد.
    if funding_rate is not None and _finite(funding_rate) is not None:
        funding = float(funding_rate)
        components["LFS2"] = _component(
            funding_extreme_score(funding), WEIGHTS["LFS2"], "REAL", funding,
            threshold=FUNDING_EXTREME_RATE,
        )
    else:
        funding = None
        components["LFS2"] = _component(None, WEIGHTS["LFS2"], "UNAVAILABLE")

    # LFS3: نسبت لانگ/شورت؛ در نبود آن، رتبهٔ زمانی OI با علامت Funding.
    if long_short_ratio is not None and _finite(long_short_ratio) is not None and float(long_short_ratio) > 0:
        ratio = float(long_short_ratio)
        ratio_score = _clip((ratio - 1.0) / 0.5)
        components["LFS3"] = _component(
            ratio_score, WEIGHTS["LFS3"], "PROXY", ratio, source="OKX_LONG_SHORT_RATIO",
        )
    elif funding is not None:
        current_oi_change = _oi_change_24h(oi_1h)
        history_oi_changes = _daily_oi_changes(oi_1d)
        rank = (
            rank_time_series(current_oi_change, history_oi_changes)
            if current_oi_change is not None and len(history_oi_changes) >= 30 else None
        )
        if rank is not None:
            sign = 1.0 if funding > 0 else -1.0 if funding < 0 else 0.0
            raw_signed = sign * rank
            components["LFS3"] = _component(
                _clip(raw_signed), WEIGHTS["LFS3"], "PROXY", raw_signed,
                source="FUNDING_SIGN_X_OI_24H_90D_PERCENTILE",
                rank=rank, oi_change_24h=current_oi_change,
            )
        else:
            components["LFS3"] = _component(None, WEIGHTS["LFS3"], "UNAVAILABLE")
    else:
        components["LFS3"] = _component(None, WEIGHTS["LFS3"], "UNAVAILABLE")

    # LFS4: BB width جاری 15m در برابر توزیع ۹۰روزهٔ 1H.
    bb_history = _hourly_bb_distribution(bars_1h)
    p20, p50 = percentile(bb_history, 20), percentile(bb_history, 50)
    current_width = _bb_width_last(bars_15m)
    if current_width is not None and p20 is not None and p50 is not None:
        components["LFS4"] = _component(
            bb_squeeze_score(current_width, p20, p50), WEIGHTS["LFS4"], "REAL",
            current_width, p20=p20, p50=p50,
        )
    else:
        components["LFS4"] = _component(None, WEIGHTS["LFS4"], "UNAVAILABLE", current_width)

    # LFS5: افت/تغییر مطلق OI در ۲۴ ساعت؛ ۱۰٪ امتیاز کامل.
    oi_change = _oi_change_24h(oi_1h)
    if oi_change is not None:
        components["LFS5"] = _component(
            oi_drop_score(oi_change), WEIGHTS["LFS5"], "REAL", oi_change,
            oi_now=_oi_points(oi_1h)[-1][1], oi_change_24h=oi_change,
        )
    else:
        components["LFS5"] = _component(None, WEIGHTS["LFS5"], "UNAVAILABLE")

    coverage = sum(item["weight"] for item in components.values() if item["score"] is not None)
    score = sum(
        float(item["score"]) * float(item["weight"])
        for item in components.values() if item["score"] is not None
    )
    if coverage >= 0.80:
        status = "FULL"
    elif coverage >= 0.40:
        status = "PARTIAL_PROXY"
    else:
        status = "INSUFFICIENT"
    if status == "INSUFFICIENT":
        veto = "LFS_INSUFFICIENT_COVERAGE"
    elif score < 0.30:
        veto = "LFS_BELOW_THRESHOLD"
    else:
        veto = "PASS"

    return {
        "symbol": symbol,
        "lfs_score": None if status == "INSUFFICIENT" else round(_clip(score), 6),
        "lfs_coverage_pct": round(coverage * 100.0, 2),
        "lfs_coverage": round(coverage, 4),
        "lfs_status": status,
        "lfs_components": components,
        "lfs_veto": veto,
        "api_status": api_status,
        "lfs_threshold": 0.30,
    }


def get_lfs_veto(lfs_score: float, coverage_pct: float = 100.0) -> str:
    if float(coverage_pct) < 40.0:
        return "LFS_INSUFFICIENT_COVERAGE"
    return "PASS" if float(lfs_score) >= 0.30 else "LFS_BELOW_THRESHOLD"
