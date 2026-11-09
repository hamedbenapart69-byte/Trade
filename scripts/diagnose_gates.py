"""گزارش مستقل Gateهای LRT-15m؛ بدون تغییر در موتور یا آستانه‌ها."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SIGNAL_ROOT = ROOT / "signal_autopilot"
if str(SIGNAL_ROOT) not in sys.path:
    sys.path.insert(0, str(SIGNAL_ROOT))

from modules import lrt15m_engine as engine
from modules.live_data_adapter import LiveOHLCVFetcher

LOG = logging.getLogger("diagnose_gates")
MIN_CLOSED_BARS = 1300
GATE_KEYS = (
    "g1_bias_4h",
    "g2_bias_1h",
    "g3_lfs",
    "g4_sweep",
    "g5_tenkan_kijun_cross",
    "g6_zone_reaction",
)
GATE_LABELS = {
    "g1_bias_4h": "Gate 1 (Bias 4H)",
    "g2_bias_1h": "Gate 2 (Bias 1H)",
    "g3_lfs": "Gate 3 (LFS)",
    "g4_sweep": "Gate 4 (Sweep)",
    "g5_tenkan_kijun_cross": "Gate 5 (Tenkan/Kijun Cross)",
    "g6_zone_reaction": "Gate 6 (Zone Reaction)",
}


def _position(close: float, span_a: float, span_b: float) -> str:
    upper, lower = max(span_a, span_b), min(span_a, span_b)
    if close > upper:
        return "ABOVE"
    if close < lower:
        return "BELOW"
    return "INSIDE"


def _cross_in_last_three(rows: list[dict[str, Any]], direction: str) -> tuple[bool, int | None]:
    """آخرین تقاطع تأییدشده در سه کندل بسته‌شده را پیدا می‌کند."""
    if len(rows) < 30:
        return False, None

    def values(index: int) -> tuple[float, float]:
        tenkan_window = rows[index - 8:index + 1]
        kijun_window = rows[index - 25:index + 1]
        tenkan = (
            max(float(x["high"]) for x in tenkan_window)
            + min(float(x["low"]) for x in tenkan_window)
        ) / 2.0
        kijun = (
            max(float(x["high"]) for x in kijun_window)
            + min(float(x["low"]) for x in kijun_window)
        ) / 2.0
        return tenkan, kijun

    first = max(26, len(rows) - 3)
    for index in range(len(rows) - 1, first - 1, -1):
        prev_t, prev_k = values(index - 1)
        curr_t, curr_k = values(index)
        crossed = (
            prev_t <= prev_k and curr_t > curr_k
            if direction == "BUY"
            else prev_t >= prev_k and curr_t < curr_k
        )
        if crossed:
            return True, len(rows) - 1 - index
    return False, None


def _unavailable(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "data_status": "DATA_UNAVAILABLE",
        "gates": {
            "g1_bias_4h": {
                "status": "DATA_UNAVAILABLE", "value": "UNKNOWN",
                "kumo_position": "INSIDE", "reason": reason,
            },
            "g2_bias_1h": {
                "status": "DATA_UNAVAILABLE", "value": "UNKNOWN",
                "kijun_position": "BELOW", "reason": reason,
            },
            "g3_lfs": {
                "status": "DATA_UNAVAILABLE", "score": None,
                "threshold": engine.MIN_LFS_SCORE_PROXY_CVD,
                "source": "UNAVAILABLE", "reason": reason,
            },
            "g4_sweep": {
                "status": "DATA_UNAVAILABLE", "sweep_type": "NONE",
                "volume_confirmed": False, "reason": reason,
            },
            "g5_tenkan_kijun_cross": {
                "status": "DATA_UNAVAILABLE", "cross_type": "NONE",
                "candles_ago": None, "reason": reason,
            },
            "g6_zone_reaction": {
                "status": "DATA_UNAVAILABLE", "zone_type": "NONE",
                "distance_pct": None, "reason": reason,
            },
        },
        "confluence_score": 0,
        "final_decision": "NO_TRADE",
        "primary_rejection_gate": "DATA_UNAVAILABLE",
    }


def _diagnose_direction(
    rows: list[dict[str, Any]],
    direction: str,
    bias4: str,
    bias1: str,
    kumo_position: str,
    kijun_position: str,
    sweep: dict[str, Any],
    atr_value: float | None,
    cvd_delta: float,
) -> dict[str, Any]:
    bullish = direction == "BUY"
    sweep_detected = bool(sweep["bullish"] if bullish else sweep["bearish"])
    order_block = engine.detect_order_block(rows, direction, atr_value)
    fvg = engine.detect_fvg(rows, direction)
    cross, candles_ago = _cross_in_last_three(rows, direction)
    cvd_aligned = cvd_delta > 0 if bullish else cvd_delta < 0
    bias_aligned = bias4 == ("BULLISH" if bullish else "BEARISH") and bias1 == (
        "BULLISH" if bullish else "BEARISH"
    )

    # همان وزن‌ها و آستانه‌های موجود موتور؛ OHLCV فقط PROXY است.
    parts = {
        "liquidity_sweep": 1.0 if sweep_detected else 0.0,
        "order_block": 1.0 if order_block else 0.0,
        "fair_value_gap": 1.0 if fvg else 0.0,
        "ichimoku_bias": 1.0 if bias_aligned else 0.0,
        "cvd": 1.0 if cvd_aligned else 0.0,
    }
    lfs_score = engine._score(parts)
    threshold = engine.MIN_LFS_SCORE_PROXY_CVD
    lfs_pass = lfs_score >= threshold
    zone_type = "OB" if order_block else "FVG" if fvg else "NONE"

    prior_volumes = [float(x.get("volume", 0.0)) for x in rows[-21:-1]]
    current_volume = float(rows[-1].get("volume", 0.0))
    volume_confirmed = bool(
        prior_volumes and sum(prior_volumes) > 0
        and current_volume > (sum(prior_volumes) / len(prior_volumes))
    )

    gates = {
        "g1_bias_4h": {
            "status": "PASS" if bias4 == ("BULLISH" if bullish else "BEARISH") else "FAIL",
            "value": bias4 if bias4 in {"BULLISH", "BEARISH"} else "NEUTRAL",
            "kumo_position": kumo_position,
            "reason": None if bias4 == ("BULLISH" if bullish else "BEARISH") else "BIAS_4H_NOT_ALIGNED",
        },
        "g2_bias_1h": {
            "status": "PASS" if bias1 == ("BULLISH" if bullish else "BEARISH") else "FAIL",
            "value": bias1 if bias1 in {"BULLISH", "BEARISH"} else "NEUTRAL",
            "kijun_position": kijun_position,
            "reason": None if bias1 == ("BULLISH" if bullish else "BEARISH") else "BIAS_1H_NOT_ALIGNED",
        },
        "g3_lfs": {
            "status": "PASS" if lfs_pass else "FAIL",
            "score": lfs_score,
            "threshold": threshold,
            "source": "PROXY_OHLCV",
            "reason": None if lfs_pass else "LFS_BELOW_THRESHOLD",
        },
        "g4_sweep": {
            "status": "PASS" if sweep_detected else "FAIL",
            "sweep_type": ("BULLISH" if sweep["bullish"] else "BEARISH" if sweep["bearish"] else "NONE"),
            "volume_confirmed": volume_confirmed,
            "reason": None if sweep_detected else "NO_SWEEP_DETECTED",
        },
        "g5_tenkan_kijun_cross": {
            "status": "PASS" if cross else "FAIL",
            "cross_type": direction if cross else "NONE",
            "candles_ago": candles_ago,
            "reason": None if cross else "NO_CROSS_IN_LAST_3",
        },
        "g6_zone_reaction": {
            "status": "PASS" if zone_type != "NONE" else "FAIL",
            "zone_type": zone_type,
            # موتور فعلی فاصله عددی Zone را expose نمی‌کند؛ عدد ساختگی تولید نمی‌شود.
            "distance_pct": None,
            "reason": None if zone_type != "NONE" else "PRICE_NOT_IN_ZONE",
        },
    }
    pass_count = sum(gates[key]["status"] == "PASS" for key in GATE_KEYS)
    return {
        "direction": direction,
        "gates": gates,
        "pass_count": pass_count,
        "lfs_score": lfs_score,
    }


def diagnose_symbol(symbol: str, fetcher: LiveOHLCVFetcher) -> dict[str, Any]:
    try:
        rows = fetcher.fetch_symbol(symbol)
        rows = sorted(rows, key=lambda item: int(item["open_time"]))
    except Exception as exc:
        return _unavailable(symbol, f"DATA_FETCH_FAILED:{type(exc).__name__}:{str(exc)[:180]}")

    if len(rows) < MIN_CLOSED_BARS:
        return _unavailable(symbol, f"INSUFFICIENT_CLOSED_15M_BARS:{len(rows)}")

    bars_1h = engine.aggregate_bars(rows, 4)
    bars_4h = engine.aggregate_bars(rows, 16)
    if len(bars_1h) < 80 or len(bars_4h) < 80:
        return _unavailable(
            symbol,
            f"INSUFFICIENT_HTF_HISTORY:1h={len(bars_1h)}:4h={len(bars_4h)}",
        )

    bias4_raw, cloud = engine._bias_4h(bars_4h)
    bias1_raw, kijun_data = engine._bias_1h(bars_1h)
    bias4 = "NEUTRAL" if bias4_raw == "RANGE" else bias4_raw
    bias1 = bias1_raw
    if bias4 not in {"BULLISH", "BEARISH", "NEUTRAL"} or bias1 not in {"BULLISH", "BEARISH"}:
        return _unavailable(symbol, "ICHIMOKU_VALUES_UNAVAILABLE")

    current_close = float(rows[-1]["close"])
    span_a, span_b = cloud.get("span_a"), cloud.get("span_b")
    kijun = kijun_data.get("kijun")
    if span_a is None or span_b is None or kijun is None:
        return _unavailable(symbol, "ICHIMOKU_VALUES_UNAVAILABLE")
    kumo_position = _position(current_close, float(span_a), float(span_b))
    kijun_position = "ABOVE" if current_close > float(kijun) else "BELOW"

    sweep = engine.detect_sweep(rows)
    atr_value = engine.atr(rows)
    cvd_delta = engine.cvd_proxy_from_klines(rows)
    directions = [
        _diagnose_direction(
            rows, direction, bias4, bias1, kumo_position, kijun_position,
            sweep, atr_value, cvd_delta,
        )
        for direction in ("BUY", "SELL")
    ]
    selected = max(
        directions,
        key=lambda item: (item["pass_count"], item["lfs_score"], item["direction"] == "BUY"),
    )
    gates = selected["gates"]
    pass_count = selected["pass_count"]
    confluence = round((pass_count / len(GATE_KEYS)) * 100)
    failures = [key for key in GATE_KEYS if gates[key]["status"] == "FAIL"]
    primary = failures[0].upper() if failures else "NONE"
    decision = "WATCHLIST" if confluence > 80 else "MONITORING" if pass_count else "NO_TRADE"

    return {
        "symbol": symbol,
        "data_status": "AVAILABLE",
        "gates": gates,
        "confluence_score": confluence,
        "final_decision": decision,
        "primary_rejection_gate": primary,
    }


def build_summary(results: list[dict[str, Any]]) -> str:
    lines = ["LRT-15m Gate Diagnostics — 27-symbol universe", ""]
    counts: dict[str, Counter[str]] = {}
    for key in GATE_KEYS:
        counter: Counter[str] = Counter()
        for item in results:
            counter[item["gates"][key]["status"]] += 1
        counts[key] = counter
        lines.append(
            f"{GATE_LABELS[key]}: {counter['PASS']} PASS / "
            f"{counter['FAIL']} FAIL / {counter['DATA_UNAVAILABLE']} UNAVAILABLE"
        )

    rejected = Counter(
        item["primary_rejection_gate"]
        for item in results
        if item["primary_rejection_gate"] not in {"NONE", "DATA_UNAVAILABLE"}
    )
    if rejected:
        highest = max(rejected.items(), key=lambda pair: pair[1])
        lowest = min(rejected.items(), key=lambda pair: pair[1])
        lines.extend([
            "",
            f"بیشترین علت رد: {highest[0]} — {highest[1]} نماد",
            f"کمترین علت رد: {lowest[0]} — {lowest[1]} نماد",
        ])
    else:
        lines.extend(["", "علت رد غالب: قابل تعیین نیست؛ هیچ Gate ردکننده ثبت نشده است."])

    lines.extend([
        "",
        f"نمادهای دارای داده: {sum(x['data_status'] == 'AVAILABLE' for x in results)} / {len(results)}",
        f"نمادهای فاقد داده: {sum(x['data_status'] == 'DATA_UNAVAILABLE' for x in results)} / {len(results)}",
        "",
        "تعریف امتیاز: تعداد Gateهای PASS تقسیم بر ۶ و ضرب در ۱۰۰.",
        "LFS از وزن‌ها و آستانه‌های موجود موتور استفاده می‌کند؛ OHLCV با برچسب PROXY_OHLCV.",
        "distance_pct به‌علت نبود این مقدار در خروجی موتور، عمداً null باقی می‌ماند.",
        "این گزارش تشخیصی است و هیچ آستانه یا منطق معاملاتی را تغییر نمی‌دهد.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="تشخیص مستقل شش Gate برای ۲۷ نماد LRT-15m")
    parser.add_argument("--universe", default="config/universe.json")
    parser.add_argument("--output", default="diagnostics/gates_report.json")
    parser.add_argument("--summary", default="diagnostics/summary.txt")
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    universe_path = Path(args.universe)
    payload = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = payload.get("symbols", []) if isinstance(payload, dict) else payload
    symbols = [str(symbol).strip().upper() for symbol in symbols]
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; found {len(symbols)}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    fetcher = LiveOHLCVFetcher(limit=args.limit)
    results: list[dict[str, Any]] = []
    try:
        for index, symbol in enumerate(symbols, start=1):
            result = diagnose_symbol(symbol, fetcher)
            results.append(result)
            print(
                f"GATE_DIAG {index}/27 {symbol} data={result['data_status']} "
                f"decision={result['final_decision']} score={result['confluence_score']} "
                f"primary={result['primary_rejection_gate']}",
                flush=True,
            )
    finally:
        fetcher.close()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_count": 27,
        "symbols_analyzed": len(results),
        "data_available_count": sum(item["data_status"] == "AVAILABLE" for item in results),
        "data_unavailable_count": sum(item["data_status"] == "DATA_UNAVAILABLE" for item in results),
        "results": results,
    }
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(build_summary(results), encoding="utf-8")
    print(f"DIAGNOSTICS_WRITTEN symbols={len(results)} json={output_path} summary={summary_path}", flush=True)
    return 0 if len(results) == 27 else 1


if __name__ == "__main__":
    raise SystemExit(main())
