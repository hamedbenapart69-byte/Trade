"""موتور LRT-15m؛ خروجی تا کالیبراسیون فقط UNCALIBRATED است."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.cvd_proxy import CVD_SOURCE, calculate_cvd_proxy


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
WATCHLIST_CONFLUENCE_THRESHOLD = 60
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


def detect_sweep(bars: list[dict[str, Any]], lookback: int = 20) -> dict[str, Any]:
    if len(bars) < lookback + 1:
        return {"bullish": False, "bearish": False, "swept_low": None, "swept_high": None}
    previous = bars[-lookback - 1:-1]
    current = bars[-1]
    prior_low = min(float(x["low"]) for x in previous)
    prior_high = max(float(x["high"]) for x in previous)
    return {
        "bullish": float(current["low"]) < prior_low and float(current["close"]) > prior_low,
        "bearish": float(current["high"]) > prior_high and float(current["close"]) < prior_high,
        "swept_low": prior_low, "swept_high": prior_high,
    }


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
    if len(bars) < 8:
        return {"zone_type": "NONE", "distance_pct": None, "within_limit": False}
    current = bars[-1]
    close = float(current["close"])
    if close <= 0:
        return {"zone_type": "NONE", "distance_pct": None, "within_limit": False}
    zones: list[tuple[str, float, float]] = []
    displacement = 1.2 * atr_value if atr_value is not None else 0.0
    for candle in bars[-8:-2]:
        if direction == "BUY" and candle["close"] < candle["open"] and close > candle["high"] + displacement:
            zones.append(("OB", float(candle["low"]), float(candle["high"])))
        elif direction == "SELL" and candle["close"] > candle["open"] and close < candle["low"] - displacement:
            zones.append(("OB", float(candle["low"]), float(candle["high"])))
    left = bars[-3]
    if direction == "BUY" and float(current["low"]) > float(left["high"]):
        zones.append(("FVG", float(left["high"]), float(current["low"])))
    elif direction == "SELL" and float(current["high"]) < float(left["low"]):
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


def _score(parts: dict[str, float]) -> float:
    return round(sum(parts[name] * weight for name, weight in LFS_WEIGHTS.items()), 4)


def analyze_symbol(symbol: str, rows: list[dict[str, Any]],
                   aggtrades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if len(rows) < 300:
        return _no_setup(symbol, "INSUFFICIENT_15M_HISTORY", len(rows))
    bars = []
    for row in rows:
        bar = {}
        for key, value in row.items():
            if key == "open_time":
                bar[key] = int(value)
            elif key in {"data_source", "cvd_source"}:
                bar[key] = str(value)
            else:
                bar[key] = float(value)
        bars.append(bar)
    bars.sort(key=lambda x: x["open_time"])
    data_sources = sorted({x.get("data_source", "BINANCE_VISION_KLINES") for x in bars})
    bars_1h = aggregate_bars(bars, 4)
    bars_4h = aggregate_bars(bars, 16)
    if len(bars_1h) < 80 or len(bars_4h) < 80:
        return _no_setup(symbol, "INSUFFICIENT_HTF_HISTORY", len(rows))

    current = bars[-1]
    atr_value = atr(bars)
    sweep = detect_sweep(bars)
    bias4, cloud = _bias_4h(bars_4h)
    bias1, kijun = _bias_1h(bars_1h)
    cvd = None
    cvd_source = CVD_SOURCE
    if aggtrades is not None:
        current_bucket = int(current["open_time"])
        bucket_rows = [x for x in aggtrades if int(x.get("bucket_open_time", -1)) == current_bucket]
        if bucket_rows:
            cvd = sum(float(x.get("delta", 0.0)) for x in bucket_rows)
            cvd_source = "AGGTRADES_REAL"
        else:
            raw_rows = [x for x in aggtrades
                        if current_bucket <= int(x.get("timestamp", x.get("T", -1))) < current_bucket + 900_000]
            if raw_rows:
                cvd = cvd_delta_from_aggtrades(raw_rows)
                cvd_source = "AGGTRADES_REAL"
    if cvd is None:
        cvd = cvd_proxy_from_klines(bars)
        cvd_source = CVD_SOURCE
    cvd_sign = "BUY" if cvd > 0 else "SELL" if cvd < 0 else "NEUTRAL"

    candidates = []
    gate_diagnostics = []
    for direction in ("BUY", "SELL"):
        bullish = direction == "BUY"
        sweep_ok = sweep["bullish"] if bullish else sweep["bearish"]
        ob_ok = detect_order_block(bars, direction, atr_value)
        fvg_ok = detect_fvg(bars, direction)
        zone = zone_distance(bars, direction, atr_value)
        zone_ok = (ob_ok or fvg_ok) and bool(zone["within_limit"])
        cross_ok = tenkan_kijun_cross(bars, direction)
        bias_ok, bias_gate = higher_timeframe_gate(direction, bias4, bias1)
        cvd_ok = cvd_sign == direction
        minimum_score = MIN_LFS_SCORE_REAL_CVD if cvd_source == "AGGTRADES_REAL" else MIN_LFS_SCORE_PROXY_CVD
        parts = {
            "liquidity_sweep": 1.0 if sweep_ok else 0.0,
            "order_block": 1.0 if ob_ok else 0.0,
            "fair_value_gap": 1.0 if fvg_ok else 0.0,
            "ichimoku_bias": 1.0 if bias_ok else 0.0,
            "cvd": 1.0 if cvd_ok else 0.0,
        }
        score = _score(parts)
        trigger = sweep_ok and zone_ok and cvd_ok and score >= minimum_score
        gate_diagnostics.append({
            "direction": direction,
            "LIQUIDITY_SWEEP_GATE": "PASS" if sweep_ok else "FAIL",
            "ORDER_BLOCK_OR_FVG_GATE": "PASS" if (ob_ok or fvg_ok) else "FAIL",
            "ZONE_DISTANCE_PCT": zone["distance_pct"],
            "ZONE_DISTANCE_LIMIT_PCT": MAX_ZONE_DISTANCE_PCT,
            "ZONE_DISTANCE_GATE": "PASS" if zone_ok else "FAIL",
            "CROSS_10_GATE": "PASS" if cross_ok else "FAIL",
            "CROSS_LOOKBACK": CROSS_LOOKBACK,
            "HTF_BIAS_GATE": "PASS" if bias_ok else f"FAIL:{bias_gate}",
            "CVD_DIRECTION_GATE": "PASS" if cvd_ok else "FAIL",
            "CVD_SOURCE": cvd_source,
            "LFS_SCORE": score,
            "LFS_THRESHOLD": minimum_score,
            "LFS_SCORE_GATE": "PASS" if score >= minimum_score else "FAIL",
            "QUALIFIED_SETUP_GATE": "PASS" if trigger else "FAIL",
        })
        if trigger:
            entry = float(current["close"])
            if bullish:
                stop = min(float(current["low"]), float(sweep["swept_low"])) - (0.1 * (atr_value or 0))
                risk = entry - stop
                target = entry + 2.0 * risk
            else:
                stop = max(float(current["high"]), float(sweep["swept_high"])) + (0.1 * (atr_value or 0))
                risk = stop - entry
                target = entry - 2.0 * risk
            if risk > 0:
                candidates.append({
                    "symbol": symbol, "direction": direction, "timeframe": "15m",
                    "tier": "B", "decision": "WATCHLIST",
                    "entry": round(entry, 10), "stop_loss": round(stop, 10),
                    "take_profit": round(target, 10), "rr": 2.0,
                    "lfs_score": score, "lfs_components": parts,
                    "cross_10_pass": cross_ok,
                    "cross_lookback": CROSS_LOOKBACK,
                    "zone_type": zone["zone_type"],
                    "zone_distance_pct": zone["distance_pct"],
                    "zone_distance_limit_pct": MAX_ZONE_DISTANCE_PCT,
                    "zone_distance_pass": zone_ok,
                    "higher_timeframe_bias_confirmed": bias_ok,
                    "higher_timeframe_gate": bias_gate,
                    "hypothesis": f"{direction} liquidity sweep + OB/FVG retest with 4H Kumo and 1H Kijun confirmation",
                    "falsification": "15m close beyond stop-loss or loss of aligned 4H Kumo / 1H Kijun bias",
                    "confidence": "NOT_CALIBRATED", "brier_score": "NOT_CALIBRATED",
                    "ev": "NOT_CALCULATED_CALIBRATION_AND_COST_INPUTS_UNAVAILABLE",
                    "cvd": {"delta": round(cvd, 8), "source": cvd_source, "CVD_SOURCE": cvd_source},
                    "data_sources": data_sources,
                    "higher_timeframe_bias": {"4h_kumo": bias4, "1h_kijun": bias1},
                    "status": "UNCALIBRATED",
                    "note": "Tier A ممنوع تا زمانی که Brier OOS < 0.25 و کالیبراسیون معتبر موجود باشد.",
                })
    if candidates:
        return candidates[0]
    return {
        **_no_setup(symbol, "NO_QUALIFIED_LRT15M_SETUP", len(rows)),
        "higher_timeframe_bias": {"4h_kumo": bias4, "1h_kijun": bias1},
        "cvd_source": cvd_source,
        "CVD_SOURCE": cvd_source,
        "gate_diagnostics": gate_diagnostics,
        "data_sources": data_sources,
        "lfs_weights": LFS_WEIGHTS,
    }


def _no_setup(symbol: str, reason: str, rows: int) -> dict[str, Any]:
    return {
        "symbol": symbol, "timeframe": "15m", "decision": "NO_QUALIFIED_SETUP",
        "tier": None, "reason": reason, "rows_available": rows,
        "confidence": "NOT_CALIBRATED", "brier_score": "NOT_CALIBRATED",
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
        results.append(analyze_symbol(symbol, rows, trades))
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
