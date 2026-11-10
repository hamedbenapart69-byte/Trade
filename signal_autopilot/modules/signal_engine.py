"""EMA trend-continuation V2 with conservative entry-quality gates.

این موتور فقط از دادهٔ عمومی بازار استفاده می‌کند و سفارش اجرا نمی‌کند.
سیگنال قابل‌اقدام فقط با زمان معتبر قیمت و تأیید روند/مومنتوم صادر می‌شود.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from math import isfinite
import hashlib
import json

C10 = {
    "BUY_NOW", "SELL_NOW", "CONDITIONAL_BUY", "CONDITIONAL_SELL",
    "WATCHLIST", "NO_QUALIFIED_SETUP", "MARKET_DATA_DEGRADED",
}

MIN_CANDLES = 200
MIN_EMA_SPREAD = 0.005
MIN_ADX = 20.0
MIN_VOLUME_RATIO = 1.2
MAX_RSI_LONG = 70.0
MIN_RSI_SHORT = 30.0
MAX_ENTRY_EXTENSION_ATR = 1.5
MAX_STOP_PCT = 3.0


def ema(values: list[float], period: int) -> list[float]:
    """محاسبه EMA با مقداردهی اولیه از میانگین ساده."""
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1.0)
    output = [sum(values[:period]) / period]
    for value in values[period:]:
        output.append(value * alpha + output[-1] * (1.0 - alpha))
    return output


def atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    """میانگین True Range چهارده کندل آخر."""
    if len(candles) < period + 1:
        return None
    true_ranges: list[float] = []
    for index in range(1, len(candles)):
        current = candles[index]
        previous_close = float(candles[index - 1]["close"])
        high = float(current["high"])
        low = float(current["low"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    recent = true_ranges[-period:]
    return sum(recent) / period if recent else None


def rsi(values: list[float], period: int = 14) -> float | None:
    """RSI با میانگین سادهٔ سود و زیان در پنجرهٔ اخیر."""
    if len(values) < period + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(len(values) - period, len(values))]
    gains = sum(max(change, 0.0) for change in changes) / period
    losses = sum(max(-change, 0.0) for change in changes) / period
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gains / losses)


def adx(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    """ADX تقریبی و شفاف بر پایهٔ پنجره‌های Wilder-style."""
    if len(candles) < 2 * period + 1:
        return None
    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, len(candles)):
        current, previous = candles[i], candles[i - 1]
        up = float(current["high"]) - float(previous["high"])
        down = float(previous["low"]) - float(current["low"])
        tr.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)

    dx_values: list[float] = []
    for end in range(period - 1, len(tr)):
        start = end - period + 1
        tr_sum = sum(tr[start:end + 1])
        if tr_sum <= 0:
            dx_values.append(0.0)
            continue
        plus_di = 100.0 * sum(plus_dm[start:end + 1]) / tr_sum
        minus_di = 100.0 * sum(minus_dm[start:end + 1]) / tr_sum
        denominator = plus_di + minus_di
        dx_values.append(100.0 * abs(plus_di - minus_di) / denominator if denominator else 0.0)
    if len(dx_values) < period:
        return None
    return sum(dx_values[-period:]) / period


def volume_ratio(candles: list[dict[str, Any]], period: int = 20) -> float | None:
    """حجم آخر کندل بسته‌شده نسبت به میانگین ۲۰ کندل قبل."""
    if len(candles) < period + 1:
        return None
    baseline = [float(c["volume"]) for c in candles[-period - 1:-1]]
    average = sum(baseline) / period
    return float(candles[-1]["volume"]) / average if average > 0 else None


def _finite_ohlcv(candles: list[dict[str, Any]]) -> bool:
    for candle in candles:
        try:
            values = [float(candle[k]) for k in ("open", "high", "low", "close", "volume")]
        except (KeyError, TypeError, ValueError):
            return False
        if not all(isfinite(value) for value in values):
            return False
        open_, high, low, close, volume = values
        if min(open_, high, low, close) <= 0 or volume < 0:
            return False
        if high < max(open_, close, low) or low > min(open_, close, high):
            return False
    return True


def _candle_confirmation(candles: list[dict[str, Any]], direction: str) -> bool:
    candle = candles[-1]
    open_, high, low, close = (float(candle[k]) for k in ("open", "high", "low", "close"))
    span = high - low
    if span <= 0:
        return False
    body_ratio = abs(close - open_) / span
    close_location = (close - low) / span
    if direction == "LONG":
        return close > open_ and body_ratio >= 0.35 and close_location >= 0.65
    return close < open_ and body_ratio >= 0.35 and close_location <= 0.35


def _higher_low_or_lower_high(candles: list[dict[str, Any]], direction: str) -> bool:
    """ساختار سادهٔ دو پنجرهٔ پنج‌کندلی؛ جایگزین ساختار کامل بازار نیست."""
    previous, recent = candles[-10:-5], candles[-5:]
    if len(previous) != 5 or len(recent) != 5:
        return False
    if direction == "LONG":
        return min(float(c["low"]) for c in recent) > min(float(c["low"]) for c in previous)
    return max(float(c["high"]) for c in recent) < max(float(c["high"]) for c in previous)


def _input_hash(row: dict[str, Any]) -> str:
    """هش SHA-256 ورودی بازار برای بازتولیدپذیری و ممیزی."""
    material = {
        "symbol": row.get("symbol"), "timeframe": row.get("timeframe", "1H"),
        "last": row.get("last"), "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
        "ticker_timestamp_source": row.get("ticker_timestamp_source"),
        "ohlcv": row.get("ohlcv") or [],
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _degraded(row: dict[str, Any], generated: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"), "status": "MARKET_DATA_DEGRADED", "side": None,
        "entry": None, "stop_loss": None, "take_profit": [], "ema20": None, "ema50": None,
        "atr14": None, "confidence": "NOT_CALIBRATED", "generated_at_utc": generated,
        "data_availability": row.get("availability") or {},
        "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
        "ticker_timestamp_source": row.get("ticker_timestamp_source", "EXCHANGE"),
        "entry_price_quality": None, "analysis_type": "EMA_TREND_CONTINUATION_V2",
        "timeframe": row.get("timeframe", "1H"), "hypothesis": None, "falsification": None,
        "chart_candles": [], "input_hash": _input_hash(row), "reason": reason,
    }


def build_signal(row: dict[str, Any], generated_at_utc: str) -> dict[str, Any]:
    """صدور سیگنال فقط پس از عبور از تمام دروازه‌های کیفیت."""
    candles = row.get("ohlcv") or []
    availability = row.get("availability") or {}
    if availability.get("ohlcv") != "OK" or len(candles) < MIN_CANDLES:
        return _degraded(row, generated_at_utc, "OHLCV unavailable or fewer than 200 completed 1H candles")
    if not _finite_ohlcv(candles):
        return _degraded(row, generated_at_utc, "Invalid or non-finite OHLCV")

    try:
        now_ms = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00")).timestamp() * 1000
        candle_age_hours = (now_ms - int(candles[-1]["timestamp"])) / 3_600_000
        if candle_age_hours < 0 or candle_age_hours > 2:
            return _degraded(row, generated_at_utc, "Latest completed 1H candle is stale or from the future")

        ticker_time = row.get("ticker_timestamp_utc")
        ticker_price = row.get("last")
        if ticker_time is None or ticker_price is None:
            return _degraded(row, generated_at_utc, "Fresh futures ticker price/timestamp unavailable")
        ticker_ms = datetime.fromisoformat(str(ticker_time).replace("Z", "+00:00")).timestamp() * 1000
        ticker_age_ms = now_ms - ticker_ms
        if ticker_age_ms < 0 or ticker_age_ms > 15 * 60 * 1000:
            return _degraded(row, generated_at_utc, "Futures ticker is stale or timestamp is from the future")
        entry = float(ticker_price)
        if not isfinite(entry) or entry <= 0:
            return _degraded(row, generated_at_utc, "Invalid futures ticker price")

        closes = [float(c["close"]) for c in candles]
        fast, slow = ema(closes, 20), ema(closes, 50)
        atr_value = atr(candles, 14)
        rsi_value = rsi(closes, 14)
        adx_value = adx(candles, 14)
        vol_ratio = volume_ratio(candles, 20)
        if not fast or not slow or any(x is None for x in (atr_value, rsi_value, adx_value, vol_ratio)) or atr_value <= 0:
            return _degraded(row, generated_at_utc, "Indicator calculation unavailable or invalid")

        ema20_value, ema50_value = fast[-1], slow[-1]
        close = closes[-1]
        spread = abs(ema20_value - ema50_value) / max(abs(ema50_value), 1e-12)
        fast_slope = (fast[-1] - fast[-6]) / max(abs(fast[-6]), 1e-12)
        slow_slope = (slow[-1] - slow[-6]) / max(abs(slow[-6]), 1e-12)

        direction = None
        if ema20_value > ema50_value and fast_slope > 0 and slow_slope > 0 and close > ema20_value > ema50_value:
            direction = "LONG"
        elif ema20_value < ema50_value and fast_slope < 0 and slow_slope < 0 and close < ema20_value < ema50_value:
            direction = "SHORT"

        if direction is None:
            return {
                **_degraded(row, generated_at_utc, "Trend alignment or EMA slopes do not confirm continuation"),
                "ema20": round(ema20_value, 10), "ema50": round(ema50_value, 10),
                "atr14": round(atr_value, 10), "entry": round(entry, 10),
            }

        gates = {
            "ema_spread": spread > MIN_EMA_SPREAD,
            "ema20_slope_aligned": fast_slope > 0 if direction == "LONG" else fast_slope < 0,
            "ema50_slope_aligned": slow_slope > 0 if direction == "LONG" else slow_slope < 0,
            "close_aligned": close > ema20_value if direction == "LONG" else close < ema20_value,
            "rsi_momentum": (50.0 <= rsi_value <= MAX_RSI_LONG) if direction == "LONG" else (MIN_RSI_SHORT <= rsi_value <= 50.0),
            "adx_trend_strength": adx_value >= MIN_ADX,
            "volume_confirmation": vol_ratio >= MIN_VOLUME_RATIO,
            "candle_confirmation": _candle_confirmation(candles, direction),
            "market_structure": _higher_low_or_lower_high(candles, direction),
            "anti_chase": abs(entry - ema20_value) / atr_value <= MAX_ENTRY_EXTENSION_ATR,
        }
        failed = [name for name, passed in gates.items() if not passed]
        metrics = {
            "ema_spread_pct": round(spread * 100, 4),
            "ema20_slope_pct_5bars": round(fast_slope * 100, 4),
            "ema50_slope_pct_5bars": round(slow_slope * 100, 4),
            "rsi14": round(rsi_value, 2), "adx14": round(adx_value, 2),
            "volume_ratio_20": round(vol_ratio, 3),
            "entry_extension_atr": round(abs(entry - ema20_value) / atr_value, 3),
        }
        base = {
            "symbol": row.get("symbol"), "side": "BUY" if direction == "LONG" else "SELL",
            "entry": round(entry, 10), "ema20": round(ema20_value, 10),
            "ema50": round(ema50_value, 10), "atr14": round(atr_value, 10),
            "confidence": "NOT_CALIBRATED", "generated_at_utc": generated_at_utc,
            "data_availability": availability, "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
            "ticker_timestamp_source": row.get("ticker_timestamp_source", "EXCHANGE"),
            "entry_price_quality": "PROXY_FETCH_TIME" if row.get("ticker_timestamp_source") == "FETCH_TIME_PROXY" else "EXCHANGE_TIMESTAMP",
            "analysis_type": "EMA_TREND_CONTINUATION_V2", "timeframe": row.get("timeframe", "1H"),
            "quality_gates": gates, "quality_metrics": metrics, "chart_candles": candles[-70:],
            "input_hash": _input_hash(row),
        }
        if failed:
            return {
                **base, "status": "NO_QUALIFIED_SETUP", "stop_loss": None, "take_profit": [],
                "reason": "Quality gates failed: " + ", ".join(failed),
                "hypothesis": None, "falsification": None,
            }

        recent = candles[-5:]
        if direction == "LONG":
            structural_stop = min(float(c["low"]) for c in recent) - 0.25 * atr_value
            atr_stop = entry - 1.5 * atr_value
            stop = min(structural_stop, atr_stop)
        else:
            structural_stop = max(float(c["high"]) for c in recent) + 0.25 * atr_value
            atr_stop = entry + 1.5 * atr_value
            stop = max(structural_stop, atr_stop)
        risk = abs(entry - stop)
        stop_pct = risk / entry * 100
        if risk <= 0 or stop_pct > MAX_STOP_PCT:
            return {
                **base, "status": "NO_QUALIFIED_SETUP", "stop_loss": None, "take_profit": [],
                "reason": f"Structural/ATR stop risk outside limit: {stop_pct:.3f}%",
                "quality_metrics": {**metrics, "stop_pct": round(stop_pct, 4)},
                "hypothesis": None, "falsification": None,
            }

        tp1 = entry + 1.5 * risk if direction == "LONG" else entry - 1.5 * risk
        tp2 = entry + 2.5 * risk if direction == "LONG" else entry - 2.5 * risk
        is_proxy = row.get("ticker_timestamp_source") == "FETCH_TIME_PROXY"
        status = ("CONDITIONAL_BUY" if direction == "LONG" else "CONDITIONAL_SELL") if is_proxy else (
            "BUY_NOW" if direction == "LONG" else "SELL_NOW"
        )
        reason = (
            f"V2: EMA20/50 aligned and rising/falling; spread={spread:.3%}; "
            f"RSI={rsi_value:.1f}; ADX={adx_value:.1f}; volume ratio={vol_ratio:.2f}; "
            f"structure, candle trigger and anti-chase gates passed."
        )
        if is_proxy:
            reason += " Entry timestamp is FETCH_TIME_PROXY; downgraded to CONDITIONAL, not an immediate entry."
        return {
            **base, "status": status, "stop_loss": round(stop, 10),
            "take_profit": [round(tp1, 10), round(tp2, 10)],
            "evidence_candles": candles[-MIN_CANDLES:],
            "reason": reason,
            "hypothesis": (
                f"ادامهٔ روند {row.get('timeframe', '1H')}؛ شیب هر دو EMA هم‌جهت است و "
                "مومنتوم، حجم، کندل تأییدی و ساختار کوتاه‌مدت نیز همسو هستند."
            ),
            "falsification": (
                f"بسته‌شدن کندل در سوی مخالف EMA50 یا شکست ساختار اخیر؛ حد ضرر {round(stop, 10)} "
                "ابطال عملی معامله است."
            ),
            "quality_metrics": {**metrics, "stop_pct": round(stop_pct, 4), "reward_risk_tp1": 1.5, "reward_risk_tp2": 2.5},
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return _degraded(row, generated_at_utc, "Invalid OHLCV/ticker input: " + type(exc).__name__)


def generate_signals(data: dict[str, Any]) -> dict[str, Any]:
    generated = data.get("generated_at_utc")
    rows = data.get("symbols") or []
    requested = max(int(data.get("symbols_requested") or len(rows)), len(rows))
    processed = len(rows)
    coverage_pct = round((processed / requested) * 100.0, 2) if requested else 0.0
    unscanned = max(requested - processed, 0)

    signals = [build_signal(row, generated) for row in rows]
    for signal in signals:
        signal["provider"] = data.get("provider", "unknown")
        signal["signal_id"] = f"{generated}|{signal.get('symbol')}|EMA20_EMA50_ATR14_QUALITY_GATES_V2"
    if not signals:
        signals = [{
            "symbol": "MARKET", "status": "MARKET_DATA_DEGRADED", "side": None,
            "entry": None, "stop_loss": None, "take_profit": [],
            "reason": "No market data returned", "confidence": "NOT_CALIBRATED",
            "generated_at_utc": generated,
        }]
    for signal in signals:
        if signal.get("status") not in C10:
            raise ValueError("invalid_C10_status:" + str(signal.get("status")))

    trade_signals = [s for s in signals if s["status"] in {"BUY_NOW", "SELL_NOW"}]
    conditional_signals = [s for s in signals if s["status"] in {"CONDITIONAL_BUY", "CONDITIONAL_SELL"}]
    symbol_data_degraded = any(s["status"] == "MARKET_DATA_DEGRADED" for s in signals)
    coverage_degraded = unscanned > 0
    degraded = symbol_data_degraded or coverage_degraded
    coverage_message = f"پوشش اسکن ناقص است: {processed} از {requested} نماد" if coverage_degraded else None

    if trade_signals:
        today_message = coverage_message
    elif conditional_signals:
        today_message = coverage_message or "تنظیم مشروط وجود دارد؛ ورود فوری مجاز نیست"
    elif degraded:
        today_message = coverage_message or "دادهٔ کافی برای ارزیابی بازار در دسترس نیست"
    else:
        today_message = "امروز سیگنال نیست"

    return {
        "schema_version": "1.3",
        "generated_at_utc": generated,
        "provider": data.get("provider", "unknown"),
        "engine": "EMA20_EMA50_ATR14_QUALITY_GATES_V2",
        "manual_trade_only": True,
        "pipeline_status": "DEGRADED" if degraded else "OK",
        "today_signal_message": today_message,
        "signals": signals,
        "trade_signals": trade_signals,
        "conditional_signals": conditional_signals,
        "quality": {
            "symbols_requested": requested, "symbols_processed": processed,
            "symbols_unscanned": unscanned, "coverage_pct": coverage_pct,
            "coverage_status": ("UNAVAILABLE" if requested == 0 else ("PARTIAL" if coverage_degraded else "COMPLETE")),
            "trade_signals": len(trade_signals), "conditional_signals": len(conditional_signals),
            "symbols_degraded": sum(1 for s in signals if s["status"] == "MARKET_DATA_DEGRADED"),
        },
    }
