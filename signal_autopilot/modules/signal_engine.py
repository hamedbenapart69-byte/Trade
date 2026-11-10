"""EMA continuation V2: 4H regime + 1H pullback/rejection.

این مسیر مستقل از LRT/NMT است؛ فقط دادهٔ عمومی بازار می‌خواند و سفارش اجرا نمی‌کند.
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

# پارامترهای V2؛ منطق از EMA-state به 4H regime + 1H pullback/rejection تغییر می‌کند.
MIN_BARS = 200
PULLBACK_TOLERANCE_ATR = 0.25
STOP_BUFFER_ATR = 0.25
MAX_STOP_PCT = 3.0
TP1_R = 1.5
TP2_R = 2.5


def ema(values: list[float], period: int) -> list[float]:
    """EMA با seed میانگین ساده."""
    if len(values) < period:
        return []
    alpha = 2.0 / (period + 1.0)
    output = [sum(values[:period]) / period]
    for value in values[period:]:
        output.append(value * alpha + output[-1] * (1.0 - alpha))
    return output


def atr(candles: list[dict[str, Any]], period: int = 14) -> float | None:
    """ATR14 با میانگین True Range چهارده کندل اخیر."""
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for index in range(1, len(candles)):
        current, previous = candles[index], candles[index - 1]
        true_ranges.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    return sum(true_ranges[-period:]) / period


def _finite_ohlcv(candles: list[dict[str, Any]]) -> bool:
    for candle in candles:
        try:
            open_, high, low, close, volume = (
                float(candle[key]) for key in ("open", "high", "low", "close", "volume")
            )
        except (KeyError, TypeError, ValueError):
            return False
        if not all(isfinite(x) for x in (open_, high, low, close, volume)):
            return False
        if min(open_, high, low, close) <= 0 or volume < 0:
            return False
        if high < max(open_, close, low) or low > min(open_, close, high):
            return False
    return True


def _validate_candle_clock(candles: list[dict[str, Any]], interval_ms: int, now_ms: float) -> str | None:
    try:
        timestamps = [int(c["timestamp"]) for c in candles]
    except (KeyError, TypeError, ValueError):
        return "CANDLE_TIMESTAMP_MISSING_OR_INVALID"
    if any(b - a != interval_ms for a, b in zip(timestamps, timestamps[1:])):
        return "DUPLICATE_MISSING_OR_IRREGULAR_CANDLES"
    if timestamps[-1] + interval_ms > now_ms:
        return "LATEST_CANDLE_NOT_COMPLETED"
    age = now_ms - timestamps[-1]
    if age < interval_ms or age > 2 * interval_ms:
        return "LATEST_CANDLE_STALE_OR_FUTURE"
    return None


def _input_hash(row: dict[str, Any]) -> str:
    material = {
        "symbol": row.get("symbol"), "timeframe": "1H",
        "last": row.get("last"), "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
        "ticker_timestamp_source": row.get("ticker_timestamp_source"),
        "ohlcv_1h": row.get("ohlcv") or [], "ohlcv_4h": row.get("ohlcv_4h") or [],
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _base(row: dict[str, Any], generated: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": row.get("symbol"), "status": status, "side": None,
        "entry": None, "stop_loss": None, "take_profit": [],
        "ema20": None, "ema50": None, "ema50_1h": None,
        "ema50_4h": None, "ema200_4h": None, "atr14": None,
        "confidence": "NOT_CALIBRATED", "generated_at_utc": generated,
        "data_availability": row.get("availability") or {},
        "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
        "ticker_timestamp_source": row.get("ticker_timestamp_source", "EXCHANGE"),
        "entry_price_quality": None, "analysis_type": "EMA_TREND_CONTINUATION_V2",
        "timeframe": "1H", "hypothesis": None, "falsification": None,
        "quality_gates": {}, "quality_metrics": {}, "chart_candles": [],
        "input_hash": _input_hash(row), "reason": reason,
    }


def build_signal(row: dict[str, Any], generated_at_utc: str) -> dict[str, Any]:
    """V2: regime چهارساعته + پولبک و کندل رد قیمت یک‌ساعته."""
    candles_1h = row.get("ohlcv") or []
    candles_4h = row.get("ohlcv_4h") or []
    availability = row.get("availability") or {}
    if (
        availability.get("ohlcv") != "OK"
        or availability.get("ohlcv_4h") != "OK"
        or len(candles_1h) < MIN_BARS
        or len(candles_4h) < MIN_BARS
    ):
        return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED",
                     "Insufficient completed 1H/4H history; 200 bars required per timeframe")
    if not _finite_ohlcv(candles_1h) or not _finite_ohlcv(candles_4h):
        return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED", "Invalid or non-finite OHLCV")

    try:
        now_ms = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00")).timestamp() * 1000
        clock_error = _validate_candle_clock(candles_1h, 3_600_000, now_ms)
        if clock_error:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED", clock_error)
        clock_error = _validate_candle_clock(candles_4h, 14_400_000, now_ms)
        if clock_error:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED", "4H_" + clock_error)

        ticker_time = row.get("ticker_timestamp_utc")
        ticker_price = row.get("last")
        if ticker_time is None or ticker_price is None:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED",
                         "Fresh futures ticker price/timestamp unavailable")
        ticker_ms = datetime.fromisoformat(str(ticker_time).replace("Z", "+00:00")).timestamp() * 1000
        ticker_age_ms = now_ms - ticker_ms
        if ticker_age_ms < 0 or ticker_age_ms > 15 * 60 * 1000:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED",
                         "Futures ticker timestamp stale or from the future")
        entry = float(ticker_price)
        if not isfinite(entry) or entry <= 0:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED", "Invalid futures ticker price")

        close_1h = [float(c["close"]) for c in candles_1h]
        close_4h = [float(c["close"]) for c in candles_4h]
        ema20_1h = ema(close_1h, 20)[-1]
        ema50_1h_series = ema(close_1h, 50)
        ema50_4h_series = ema(close_4h, 50)
        ema200_4h_series = ema(close_4h, 200)
        atr_1h = atr(candles_1h, 14)
        if not ema50_1h_series or not ema50_4h_series or not ema200_4h_series or atr_1h is None or atr_1h <= 0:
            return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED", "EMA/ATR calculation unavailable")

        ema50_1h = ema50_1h_series[-1]
        ema50_4h = ema50_4h_series[-1]
        ema200_4h = ema200_4h_series[-1]
        last = candles_1h[-1]
        close = float(last["close"])
        open_ = float(last["open"])
        low = float(last["low"])
        high = float(last["high"])
        close4h = close_4h[-1]

        regime = None
        if ema50_4h > ema200_4h and close4h > ema50_4h:
            regime = "LONG"
        elif ema50_4h < ema200_4h and close4h < ema50_4h:
            regime = "SHORT"

        pullback_distance = (
            abs(low - ema50_1h) / atr_1h if regime == "LONG"
            else abs(high - ema50_1h) / atr_1h if regime == "SHORT"
            else None
        )
        pullback_touch = pullback_distance is not None and pullback_distance <= PULLBACK_TOLERANCE_ATR
        rejection = (
            close > ema50_1h and close > open_ if regime == "LONG"
            else close < ema50_1h and close < open_ if regime == "SHORT"
            else False
        )
        gates = {
            "4h_ema50_200_regime": regime is not None,
            "4h_close_on_regime_side": (
                close4h > ema50_4h if regime == "LONG"
                else close4h < ema50_4h if regime == "SHORT"
                else False
            ),
            "1h_pullback_to_ema50": bool(pullback_touch),
            "1h_closed_candle_rejection": bool(rejection),
        }
        metrics = {
            "ema20_1h": round(ema20_1h, 10),
            "ema50_1h": round(ema50_1h, 10),
            "ema50_4h": round(ema50_4h, 10),
            "ema200_4h": round(ema200_4h, 10),
            "atr14_1h": round(atr_1h, 10),
            "pullback_distance_atr": round(pullback_distance, 4) if pullback_distance is not None else None,
        }
        base = _base(row, generated_at_utc, "NO_QUALIFIED_SETUP",
                     "4H regime or 1H EMA50 pullback/rejection conditions not satisfied")
        base.update(
            ema20=round(ema20_1h, 10), ema50=round(ema50_1h, 10),
            ema50_1h=round(ema50_1h, 10), ema50_4h=round(ema50_4h, 10),
            ema200_4h=round(ema200_4h, 10), atr14=round(atr_1h, 10),
            entry=round(entry, 10), quality_gates=gates, quality_metrics=metrics,
            chart_candles=candles_1h[-70:],
        )
        if regime is None or not pullback_touch or not rejection:
            return base

        recent = candles_1h[-5:]
        if regime == "LONG":
            stop = min(low, *(float(c["low"]) for c in recent)) - STOP_BUFFER_ATR * atr_1h
            risk = entry - stop
            side = "BUY"
        else:
            stop = max(high, *(float(c["high"]) for c in recent)) + STOP_BUFFER_ATR * atr_1h
            risk = stop - entry
            side = "SELL"
        stop_pct = risk / entry * 100 if risk > 0 else float("inf")
        metrics["stop_pct"] = round(stop_pct, 4) if isfinite(stop_pct) else None
        if risk <= 0 or stop_pct > MAX_STOP_PCT:
            base["reason"] = f"Structural stop risk exceeds {MAX_STOP_PCT:.1f}% limit"
            base["quality_metrics"] = metrics
            return base

        sign = 1.0 if side == "BUY" else -1.0
        tp1 = entry + sign * TP1_R * risk
        tp2 = entry + sign * TP2_R * risk
        is_proxy = row.get("ticker_timestamp_source") == "FETCH_TIME_PROXY"
        status = (
            "CONDITIONAL_BUY" if side == "BUY" else "CONDITIONAL_SELL"
        ) if is_proxy else ("BUY_NOW" if side == "BUY" else "SELL_NOW")
        metrics.update({
            "reward_risk_tp1": TP1_R, "reward_risk_tp2": TP2_R,
        })
        base.update({
            "status": status, "side": side, "stop_loss": round(stop, 10),
            "take_profit": [round(tp1, 10), round(tp2, 10)],
            "entry_price_quality": "PROXY_FETCH_TIME" if is_proxy else "EXCHANGE_TIMESTAMP",
            "evidence_candles": {
                "1h": candles_1h[-MIN_BARS:],
                "4h": candles_4h[-MIN_BARS:],
            },
            "reason": (
                f"V2: 4H EMA50/EMA200 regime confirmed; 1H pullback to EMA50 "
                f"({pullback_distance:.3f} ATR) and closed-candle rejection passed."
                + (" FETCH_TIME_PROXY: conditional only, not immediate." if is_proxy else "")
            ),
            "hypothesis": (
                f"ادامهٔ روند {side} پس از هم‌جهتی رژیم 4H و پولبک/رد قیمت در EMA50 تایم‌فریم 1H."
            ),
            "falsification": (
                f"بسته‌شدن کندل 1H در سمت مخالف EMA50 یا شکست کف/سقف ساختاری؛ "
                f"حد ضرر {round(stop, 10)} ابطال عملی معامله است."
            ),
            "quality_metrics": metrics,
        })
        return base
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError) as exc:
        return _base(row, generated_at_utc, "MARKET_DATA_DEGRADED",
                     "Invalid OHLCV/ticker input: " + type(exc).__name__)


def generate_signals(data: dict[str, Any]) -> dict[str, Any]:
    generated = data.get("generated_at_utc")
    rows = data.get("symbols") or []
    requested = max(int(data.get("symbols_requested") or len(rows)), len(rows))
    processed = len(rows)
    coverage_pct = round((processed / requested) * 100.0, 2) if requested else 0.0
    unscanned = max(requested - processed, 0)
    signals = [build_signal(row, generated) for row in rows]
    if not signals:
        signals = [{
            "symbol": "MARKET", "status": "MARKET_DATA_DEGRADED", "side": None,
            "entry": None, "stop_loss": None, "take_profit": [],
            "reason": "No market data returned", "confidence": "NOT_CALIBRATED",
            "generated_at_utc": generated,
        }]
    for signal in signals:
        signal["provider"] = data.get("provider", "unknown")
        signal["signal_id"] = f"{generated}|{signal.get('symbol')}|EMA_4H_REGIME_1H_PULLBACK_V2"
        if signal.get("status") not in C10:
            raise ValueError("invalid_C10_status:" + str(signal.get("status")))

    trade_signals = [s for s in signals if s["status"] in {"BUY_NOW", "SELL_NOW"}]
    conditional_signals = [s for s in signals if s["status"] in {"CONDITIONAL_BUY", "CONDITIONAL_SELL"}]
    degraded = any(s["status"] == "MARKET_DATA_DEGRADED" for s in signals) or unscanned > 0
    coverage_message = f"پوشش اسکن ناقص است: {processed} از {requested} نماد" if unscanned > 0 else None
    if trade_signals:
        today_message = coverage_message
    elif conditional_signals:
        today_message = coverage_message or "تنظیم مشروط وجود دارد؛ ورود فوری مجاز نیست"
    elif degraded:
        today_message = coverage_message or "دادهٔ کافی برای ارزیابی بازار در دسترس نیست"
    else:
        today_message = "امروز سیگنال نیست"

    return {
        "schema_version": "1.4", "generated_at_utc": generated,
        "provider": data.get("provider", "unknown"),
        "engine": "EMA_4H_REGIME_1H_PULLBACK_V2",
        "manual_trade_only": True,
        "pipeline_status": "DEGRADED" if degraded else "OK",
        "today_signal_message": today_message,
        "signals": signals, "trade_signals": trade_signals,
        "conditional_signals": conditional_signals,
        "quality": {
            "symbols_requested": requested, "symbols_processed": processed,
            "symbols_unscanned": unscanned, "coverage_pct": coverage_pct,
            "coverage_status": ("UNAVAILABLE" if requested == 0 else ("PARTIAL" if unscanned else "COMPLETE")),
            "trade_signals": len(trade_signals), "conditional_signals": len(conditional_signals),
            "symbols_degraded": sum(1 for s in signals if s["status"] == "MARKET_DATA_DEGRADED"),
        },
    }
