"""Simple EMA20/EMA50 + ATR14 signal MVP. Read-only; manual execution only."""
from __future__ import annotations

from datetime import datetime
from typing import Any

C10 = {
    "BUY_NOW", "SELL_NOW", "CONDITIONAL_BUY", "CONDITIONAL_SELL",
    "WATCHLIST", "NO_QUALIFIED_SETUP", "MARKET_DATA_DEGRADED",
}


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
    """محاسبه ATR ساده از True Range چهارده کندل آخر."""
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


def build_signal(row: dict[str, Any], generated_at_utc: str) -> dict[str, Any]:
    """ساخت سیگنال با شرط فاصله EMA حداقل نیم درصد و حدضرر/اهداف مبتنی بر ATR."""
    candles = row.get("ohlcv") or []
    availability = row.get("availability") or {}
    base: dict[str, Any] = {
        "symbol": row.get("symbol"),
        "status": "MARKET_DATA_DEGRADED",
        "side": None,
        "entry": None,
        "stop_loss": None,
        "take_profit": [],
        "ema20": None,
        "ema50": None,
        "atr14": None,
        "confidence": "NOT_CALIBRATED",
        "generated_at_utc": generated_at_utc,
        "data_availability": availability,
        "ticker_timestamp_utc": row.get("ticker_timestamp_utc"),
        "ticker_timestamp_source": row.get("ticker_timestamp_source", "EXCHANGE"),
        "entry_price_quality": None,
        "analysis_type": "EMA_TREND_CONTINUATION_MVP",
        "timeframe": "1H",
        "hypothesis": None,
        "falsification": None,
        "chart_candles": [],
    }
    if availability.get("ohlcv") != "OK" or len(candles) < 52:
        base["reason"] = "OHLCV unavailable or insufficient"
        return base

    try:
        now_ms = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00")).timestamp() * 1000
        candle_age_hours = (now_ms - int(candles[-1]["timestamp"])) / 3_600_000
        if candle_age_hours < 0 or candle_age_hours > 2:
            base["reason"] = "Latest completed 1h candle is stale or from the future"
            return base

        # ورود باید از قیمت لحظه‌ای قرارداد فیوچرز و زمان‌دار باشد، نه close قدیمی کندل.
        ticker_time = row.get("ticker_timestamp_utc")
        ticker_price = row.get("last")
        if ticker_time is None or ticker_price is None:
            base["reason"] = "Fresh futures ticker price/timestamp unavailable"
            return base
        ticker_ms = datetime.fromisoformat(str(ticker_time).replace("Z", "+00:00")).timestamp() * 1000
        ticker_age_ms = now_ms - ticker_ms
        if ticker_age_ms < 0 or ticker_age_ms > 15 * 60 * 1000:
            base["reason"] = "Futures ticker is stale or timestamp is from the future"
            return base
        entry = float(ticker_price)
        ticker_source = str(row.get("ticker_timestamp_source") or "EXCHANGE")
        base["entry_price_quality"] = "PROXY_FETCH_TIME" if ticker_source == "FETCH_TIME_PROXY" else "EXCHANGE_TIMESTAMP"
        if entry <= 0:
            base["reason"] = "Invalid futures ticker price"
            return base

        closes = [float(candle["close"]) for candle in candles]
        fast = ema(closes, 20)
        slow = ema(closes, 50)
        atr_value = atr(candles, 14)
        if not fast or not slow or atr_value is None or atr_value <= 0:
            base["reason"] = "Insufficient candles to calculate EMA/ATR"
            return base

        ema20_value = fast[-1]
        ema50_value = slow[-1]
        spread = abs(ema20_value - ema50_value) / max(abs(ema50_value), 1e-12)
        base.update(
            ema20=round(ema20_value, 10),
            ema50=round(ema50_value, 10),
            atr14=round(atr_value, 10),
            entry=round(entry, 10),
        )

        if spread <= 0.005:
            base.update(status="NO_QUALIFIED_SETUP", reason="EMA20/EMA50 distance is not greater than 0.5%")
            return base

        if ema20_value > ema50_value:
            side = "BUY"
            stop = entry - 1.5 * atr_value
            targets = [entry + 2.0 * atr_value, entry + 4.0 * atr_value]
            status = "BUY_NOW"
        else:
            side = "SELL"
            stop = entry + 1.5 * atr_value
            targets = [entry - 2.0 * atr_value, entry - 4.0 * atr_value]
            status = "SELL_NOW"

        base.update(
            status=status,
            side=side,
            stop_loss=round(stop, 10),
            take_profit=[round(target, 10) for target in targets],
            reason=f"EMA20 {"بالاتر" if side == "BUY" else "پایین‌تر"} از EMA50 است و فاصله آن‌ها {spread:.4%} است؛ شرط حداقل 0.5% برقرار است. حدضرر و اهداف با ATR14 محاسبه شده‌اند." + (" قیمت ورود با زمان دریافت API ثبت شده و PROXY است." if ticker_source == "FETCH_TIME_PROXY" else ""),
            hypothesis=f"ادامه حرکت در جهت روند 1H؛ EMA20 {'بالای' if side == 'BUY' else 'پایین'} EMA50 و فاصله نسبی {spread:.4%} است.",
            falsification=f"بسته‌شدن کندل 1H {"پایین‌تر" if side == "BUY" else "بالاتر"} از EMA50 یا فعال‌شدن حدضرر {round(stop, 10)} فرضیه را باطل می‌کند.",
            chart_candles=candles[-70:],
        )
        return base
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        base["reason"] = "Invalid OHLCV input: " + type(exc).__name__
        return base


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
        if signal.get("status") not in C10:
            raise ValueError("invalid_C10_status:" + str(signal.get("status")))

    trade_signals = [s for s in signals if s["status"] in {"BUY_NOW", "SELL_NOW"}]
    symbol_data_degraded = any(s["status"] == "MARKET_DATA_DEGRADED" for s in signals)
    coverage_degraded = unscanned > 0
    degraded = symbol_data_degraded or coverage_degraded

    if coverage_degraded:
        coverage_message = f"پوشش اسکن ناقص است: {processed} از {requested} نماد"
    else:
        coverage_message = None

    if trade_signals:
        today_message = coverage_message
    elif degraded:
        today_message = coverage_message or "دادهٔ کافی برای ارزیابی بازار در دسترس نیست"
    else:
        today_message = "امروز سیگنال نیست"

    return {
        "schema_version": "1.2",
        "generated_at_utc": generated,
        "provider": data.get("provider", "unknown"),
        "engine": "EMA20_EMA50_ATR14_MVP",
        "manual_trade_only": True,
        "pipeline_status": "DEGRADED" if degraded else "OK",
        "today_signal_message": today_message,
        "signals": signals,
        "trade_signals": trade_signals,
        "quality": {
            "symbols_requested": requested,
            "symbols_processed": processed,
            "symbols_unscanned": unscanned,
            "coverage_pct": coverage_pct,
            "coverage_status": ("UNAVAILABLE" if requested == 0 else ("PARTIAL" if coverage_degraded else "COMPLETE")),
            "trade_signals": len(trade_signals),
            "symbols_degraded": sum(1 for s in signals if s["status"] == "MARKET_DATA_DEGRADED"),
        },
    }
