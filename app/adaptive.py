"""Adaptive multi-pattern signal qualification (V6).

This module supplements, rather than mutates, the frozen V3/V5 baseline.
It identifies trend pullbacks, range reversals, confirmed breakouts and
liquidity-sweep reversals from completed OHLCV candles. Scores are ranking
scores, never probabilities of profit.
"""
from __future__ import annotations


def adaptive_setup(
    candles_1h,
    candles_15m,
    tech: dict,
    trends: dict,
    regime: str,
    structure_long: dict,
    structure_short: dict,
    ema20_15m: float,
    atr15m: float,
    funding_8h: float,
) -> dict | None:
    if len(candles_1h) < 30 or len(candles_15m) < 3 or not atr15m or atr15m <= 0:
        return None

    close = float(tech["close"])
    ema20 = float(tech["ema20"])
    ema50 = float(tech["ema50"])
    rsi = float(tech["rsi"])
    volume = float(tech["volume_ratio"])
    adx = float(tech.get("adx") or 0)
    macd_up = bool(tech.get("macd_aligned"))
    obv_up = bool(tech.get("obv_aligned"))
    mfi_up = bool(tech.get("mfi_aligned"))
    last15, prev15 = candles_15m[-1], candles_15m[-2]
    confirm_long = last15.close > prev15.close and last15.close >= ema20_15m
    confirm_short = last15.close < prev15.close and last15.close <= ema20_15m
    distance_ema_atr = abs(close - ema20) / max(float(tech.get("atr14") or 0), 1e-12)
    prior = candles_1h[-21:-1]
    prior_high = max(x.high for x in prior)
    prior_low = min(x.low for x in prior)
    breakout_long = close > prior_high and volume >= 1.15 and adx >= 18
    breakout_short = close < prior_low and volume >= 1.15 and adx >= 18

    candidates = []
    for direction in ("LONG", "SHORT"):
        aligned4h = trends.get("4h") == ("UP" if direction == "LONG" else "DOWN")
        aligned1d = trends.get("1d") == ("BULLISH" if direction == "LONG" else "BEARISH")
        aligned1h = trends.get("1h") == ("UP" if direction == "LONG" else "DOWN")
        opposite4h = trends.get("4h") == ("DOWN" if direction == "LONG" else "UP")
        opposite1d = trends.get("1d") == ("BEARISH" if direction == "LONG" else "BULLISH")
        ema_aligned = close > ema20 > ema50 if direction == "LONG" else close < ema20 < ema50
        momentum_aligned = macd_up if direction == "LONG" else macd_up
        flow_aligned = obv_up and mfi_up
        rsi_ok = 38 <= rsi <= 68 if direction == "LONG" else 32 <= rsi <= 62
        pullback = distance_ema_atr <= 1.25 and rsi_ok and aligned4h and not opposite1d
        breakout = breakout_long if direction == "LONG" else breakout_short
        structure = structure_long if direction == "LONG" else structure_short
        sweep = bool(structure.get("liquidity_sweep_aligned"))
        sweep_confirm = confirm_long if direction == "LONG" else confirm_short
        range_reversal = (
            regime == "RANGING"
            and ((direction == "LONG" and rsi <= 38 and tech.get("bb_position") in {"lower_band", "lower_half"})
                 or (direction == "SHORT" and rsi >= 62 and tech.get("bb_position") in {"upper_band", "upper_half"}))
        )
        if direction == "LONG":
            ema15_confirm = confirm_long
        else:
            ema15_confirm = confirm_short

        score = 0
        evidence = []
        if aligned4h:
            score += 18; evidence.append("4H trend aligned")
        if aligned1d:
            score += 12; evidence.append("1D regime aligned")
        if aligned1h:
            score += 8; evidence.append("1H trend aligned")
        if ema_aligned:
            score += 10; evidence.append("EMA structure aligned")
        if momentum_aligned:
            score += 7; evidence.append("MACD momentum aligned")
        if rsi_ok:
            score += 5; evidence.append("RSI in directional operating band")
        if adx >= 18:
            score += 6; evidence.append("trend strength confirmed")
        if adx >= 25:
            score += 3
        if volume >= 0.9:
            score += 5; evidence.append("volume not materially below baseline")
        if volume >= 1.3:
            score += 4; evidence.append("volume expansion")
        if flow_aligned:
            score += 5; evidence.append("OBV and MFI aligned")
        if structure.get("classification") == ("BULLISH" if direction == "LONG" else "BEARISH"):
            score += 8; evidence.append("4H swing structure aligned")
        if sweep and sweep_confirm:
            score += 13; evidence.append("liquidity sweep with 15m reversal confirmation")
        if structure.get("fvg_aligned"):
            score += 4; evidence.append("unmitigated aligned fair-value gap")
        if structure.get("order_block_aligned"):
            score += 4; evidence.append("unmitigated aligned order block")
        if breakout:
            score += 14; evidence.append("20-bar range breakout with volume and ADX")
        if ema15_confirm:
            score += 8; evidence.append("15m directional close confirmed")
        if abs(last15.close - ema20_15m) <= 1.5 * atr15m:
            score += 3; evidence.append("15m entry distance acceptable")
        if range_reversal:
            score += 12; evidence.append("range-edge mean-reversion setup")
        if opposite4h:
            score -= 18; evidence.append("4H trend conflict")
        if opposite1d:
            score -= 12; evidence.append("1D regime conflict")
        if abs(funding_8h) >= 0.0005:
            score -= 5; evidence.append("funding elevated; entry needs stronger confirmation")
        score = max(0, min(100, score))

        if sweep and sweep_confirm:
            family = "LIQUIDITY_SWEEP_REVERSAL"
        elif breakout:
            family = "BREAKOUT_RETEST"
        elif range_reversal:
            family = "RANGE_MEAN_REVERSION"
        elif pullback and ema15_confirm:
            family = "TREND_PULLBACK"
        elif pullback:
            family = "TREND_PULLBACK"
        else:
            family = None

        if family and score >= 52:
            candidates.append({
                "direction": direction,
                "strategy_family": family,
                "strategy_score": score,
                "strategy_evidence": evidence,
                "pattern_confirmed": bool(ema15_confirm or (sweep and sweep_confirm) or breakout),
                "confirmation_required": None if (ema15_confirm or breakout) else "wait for a completed 15m candle to confirm the direction at/through EMA20",
                "trigger_level": float(ema20_15m),
            })

    if not candidates:
        return None
    candidates.sort(key=lambda x: (x["strategy_score"], x["pattern_confirmed"]), reverse=True)
    if len(candidates) > 1 and candidates[0]["strategy_score"] - candidates[1]["strategy_score"] < 8:
        return None
    return candidates[0]
