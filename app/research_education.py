"""نمونه‌های پژوهشی مستقل H1/H6/H7؛ خارج از مسیر تولید سیگنال V5."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from app.signals import Candle

Side = Literal["LONG", "SHORT"]
Bias = Literal["UP", "DOWN", "NEUTRAL"]


@dataclass(frozen=True)
class ResearchEvent:
    """رویداد پژوهشی؛ به‌تنهایی دستور معامله یا سیگنال اجرایی نیست."""

    hypothesis_id: str
    side: Side
    signal_index: int
    level: float
    reference_index: int
    reason: str


def _ema(values: Sequence[float], period: int) -> float | None:
    """EMA با مقداردهی اولیه SMA؛ فقط برای آخرین کندل بسته‌شده."""
    if period <= 0 or len(values) < period:
        return None
    value = sum(values[:period]) / period
    alpha = 2.0 / (period + 1.0)
    for item in values[period:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def _atr(candles: Sequence[Candle], period: int) -> float | None:
    if period <= 0 or len(candles) < period:
        return None
    true_ranges: list[float] = []
    for i, candle in enumerate(candles):
        if i == 0:
            true_ranges.append(candle.high - candle.low)
        else:
            previous_close = candles[i - 1].close
            true_ranges.append(
                max(
                    candle.high - candle.low,
                    abs(candle.high - previous_close),
                    abs(candle.low - previous_close),
                )
            )
    return sum(true_ranges[-period:]) / period


def _valid_series(candles: Sequence[Candle]) -> bool:
    """ترتیب زمانی و بسته‌بودن کندل‌ها را بررسی می‌کند؛ اعتبارسنجی کامل داده جداست."""
    if not candles or any(not c.is_final for c in candles):
        return False
    return all(
        candles[i].open_time < candles[i + 1].open_time
        for i in range(len(candles) - 1)
    )


def detect_liquidity_sweeps(
    candles: Sequence[Candle],
    lookback: int = 20,
    atr_period: int = 14,
    atr_buffer_fraction: float = 0.10,
) -> list[ResearchEvent]:
    """H1: نفوذ از سقف/کف قبلی و بسته‌شدن دوباره داخل سطح.

    سطح فقط از کندل‌های قبل از کندل رویداد ساخته می‌شود. رویداد پس از بسته‌شدن
    کندل reclaim قابل‌شناسایی است؛ قیمت ورود باید در موتور بک‌تست از کندل بعدی
    تعیین شود. این تابع وجود سفارش حدضرر یا جمع‌آوری واقعی نقدینگی را اثبات نمی‌کند.
    """
    if (
        lookback < 2
        or atr_period < 1
        or atr_buffer_fraction < 0
        or not _valid_series(candles)
    ):
        return []

    events: list[ResearchEvent] = []
    for i in range(max(lookback, atr_period), len(candles)):
        prior = candles[i - lookback : i]
        atr_value = _atr(candles[i - atr_period : i], atr_period)
        if atr_value is None or atr_value <= 0:
            continue
        buffer = atr_value * atr_buffer_fraction
        upper = max(c.high for c in prior)
        lower = min(c.low for c in prior)
        current = candles[i]

        short_sweep = current.high > upper + buffer and current.close < upper
        long_sweep = current.low < lower - buffer and current.close > lower

        # اگر هر دو سمت در یک کندل رخ دهند، جهت قابل اتکا نیست.
        if short_sweep == long_sweep:
            continue
        if short_sweep:
            events.append(
                ResearchEvent(
                    "H1", "SHORT", i, upper, i - 1,
                    "swept_prior_high_and_closed_back_below",
                )
            )
        else:
            events.append(
                ResearchEvent(
                    "H1", "LONG", i, lower, i - 1,
                    "swept_prior_low_and_closed_back_above",
                )
            )
    return events


def detect_breakout_retests(
    candles: Sequence[Candle],
    range_lookback: int = 20,
    retest_window: int = 4,
    tolerance_atr: float = 0.10,
    atr_period: int = 14,
) -> list[ResearchEvent]:
    """H6: شکست محدوده و retest موفق با تأیید بسته‌شدن در سمت شکست.

    محدوده در لحظه شکست از کندل‌های قبلی ساخته می‌شود. سیگنال پژوهشی در کندل
    retest ثبت می‌شود، نه در کندل شکست؛ اجرای فرضی فقط از کندل بعدی مجاز است.
    """
    if (
        range_lookback < 2
        or retest_window < 1
        or tolerance_atr < 0
        or atr_period < 1
        or not _valid_series(candles)
    ):
        return []

    events: list[ResearchEvent] = []
    start = max(range_lookback, atr_period)
    i = start
    while i < len(candles):
        prior = candles[i - range_lookback : i]
        atr_value = _atr(candles[i - atr_period : i], atr_period)
        if atr_value is None or atr_value <= 0:
            i += 1
            continue

        upper = max(c.high for c in prior)
        lower = min(c.low for c in prior)
        breakout = candles[i]
        side: Side | None = None
        level = 0.0
        if breakout.close > upper:
            side, level = "LONG", upper
        elif breakout.close < lower:
            side, level = "SHORT", lower

        if side is None:
            i += 1
            continue

        tolerance = atr_value * tolerance_atr
        end = min(len(candles), i + retest_window + 1)
        for j in range(i + 1, end):
            bar = candles[j]
            if side == "LONG":
                if bar.close < level:
                    break
                touched = bar.low <= level + tolerance
                confirmed = bar.close > level
            else:
                if bar.close > level:
                    break
                touched = bar.high >= level - tolerance
                confirmed = bar.close < level
            if touched and confirmed:
                events.append(
                    ResearchEvent(
                        "H6", side, j, level, i,
                        "breakout_then_retest_held",
                    )
                )
                i = j
                break
        i += 1
    return events


def detect_breakout_acceptance(
    candles: Sequence[Candle],
    range_lookback: int = 20,
    acceptance_bars: int = 2,
) -> list[ResearchEvent]:
    """H5 price-only proxy: breakout beyond a prior range with consecutive closes.

    این نسخه فقط پذیرش قیمتی را می‌سنجد؛ به‌هیچ‌وجه تأیید دلتا یا جریان سفارش واقعی نیست.
    رویداد پس از بسته‌شدن آخرین کندل پذیرش ثبت می‌شود و ورود زودتر از کندل بعدی مجاز نیست.
    """
    if (
        range_lookback < 2
        or acceptance_bars < 1
        or not _valid_series(candles)
    ):
        return []

    events: list[ResearchEvent] = []
    i = range_lookback
    while i + acceptance_bars < len(candles):
        prior = candles[i - range_lookback : i]
        upper = max(c.high for c in prior)
        lower = min(c.low for c in prior)
        breakout = candles[i]
        side: Side | None = None
        level = 0.0
        if breakout.close > upper:
            side, level = "LONG", upper
        elif breakout.close < lower:
            side, level = "SHORT", lower

        if side is None:
            i += 1
            continue

        confirmation = candles[i + 1 : i + acceptance_bars + 1]
        if side == "LONG":
            accepted = all(c.close > level for c in confirmation)
        else:
            accepted = all(c.close < level for c in confirmation)

        if accepted:
            signal_index = i + acceptance_bars
            events.append(
                ResearchEvent(
                    "H5_PRICE_PROXY", side, signal_index, level, i,
                    "breakout_accepted_by_consecutive_closes_price_only",
                )
            )
            i = signal_index + 1
        else:
            i += 1
    return events


def detect_value_boundary_rejections(
    candles: Sequence[Candle],
    lookback: int = 24,
    rejection_bars: int = 2,
) -> list[ResearchEvent]:
    """H2_TIME_REJECTION_PROXY: شکست مرز دامنهٔ ۲۴ساعته و بازگشت پایدار به داخل.

    این فقط پذیرش/رد زمانیِ قیمت بر پایهٔ OHLCV یک‌ساعته است؛
    Volume Profile، POC، VAH یا VAL واقعی محاسبه نمی‌شود.
    سیگنال پس از بسته‌شدن همهٔ کندل‌های بازگشت ثبت می‌شود.
    """
    if (
        lookback < 2
        or rejection_bars < 1
        or not _valid_series(candles)
    ):
        return []

    events: list[ResearchEvent] = []
    i = lookback
    while i + rejection_bars < len(candles):
        prior = candles[i - lookback : i]
        upper = max(c.high for c in prior)
        lower = min(c.low for c in prior)
        breakout = candles[i]

        side: Side | None = None
        level = 0.0
        if breakout.close > upper:
            side, level = "SHORT", upper
        elif breakout.close < lower:
            side, level = "LONG", lower

        if side is None:
            i += 1
            continue

        confirmation = candles[i + 1 : i + rejection_bars + 1]
        if side == "SHORT":
            rejected = all(c.close < level for c in confirmation)
        else:
            rejected = all(c.close > level for c in confirmation)

        if rejected:
            signal_index = i + rejection_bars
            events.append(
                ResearchEvent(
                    "H2_TIME_REJECTION_PROXY",
                    side,
                    signal_index,
                    level,
                    i,
                    "two_completed_closes_returned_inside_prior_rolling_range",
                )
            )
            i = signal_index + 1
        else:
            i += 1
    return events


def higher_timeframe_bias(
    candles: Sequence[Candle],
    fast_period: int = 20,
    slow_period: int = 50,
) -> Bias:
    """H7: جهت HTF از EMAهای آخرین کندل‌های بسته‌شده؛ بدون کندل باز."""
    if (
        fast_period < 2
        or slow_period <= fast_period
        or not _valid_series(candles)
        or len(candles) < slow_period
    ):
        return "NEUTRAL"

    closes = [c.close for c in candles]
    fast = _ema(closes, fast_period)
    slow = _ema(closes, slow_period)
    if fast is None or slow is None:
        return "NEUTRAL"
    if closes[-1] > fast and fast > slow:
        return "UP"
    if closes[-1] < fast and fast < slow:
        return "DOWN"
    return "NEUTRAL"


def passes_higher_timeframe_gate(
    side: Side,
    higher_timeframe_candles: Sequence[Candle],
) -> bool:
    """H7: فقط هم‌جهتی صریح پذیرفته می‌شود؛ حالت خنثی سیگنال را رد می‌کند."""
    bias = higher_timeframe_bias(higher_timeframe_candles)
    return (side == "LONG" and bias == "UP") or (
        side == "SHORT" and bias == "DOWN"
    )
