"""تشخیص شفاف Gateهای LRT-15m برای Universe ثابت ۲۷ نماد."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import tenkan_kijun_cross
from modules.live_data_adapter import LiveOHLCVFetcher
from modules import lrt15m_engine as engine

LOG = logging.getLogger("diagnose_gates")
MIN_CLOSED_BARS = 1300


def _inside_kumo(close: float, span_a: float | None, span_b: float | None) -> bool | None:
    if span_a is None or span_b is None:
        return None
    return min(span_a, span_b) <= close <= max(span_a, span_b)


def _direction_diagnostic(
    rows: list[dict[str, Any]],
    direction: str,
    bias4: str,
    bias1: str,
    sweep: dict[str, Any],
    atr_value: float | None,
    cvd_delta: float,
    cvd_source: str,
    cross: bool,
) -> dict[str, Any]:
    bullish = direction == "BUY"
    sweep_ok = bool(sweep["bullish"] if bullish else sweep["bearish"])
    ob_ok = engine.detect_order_block(rows, direction, atr_value)
    fvg_ok = engine.detect_fvg(rows, direction)
    zone = engine.zone_distance(rows, direction, atr_value)
    zone_ok = (ob_ok or fvg_ok) and bool(zone["within_limit"])
    bias_ok, bias_reason = engine.higher_timeframe_gate(direction, bias4, bias1)
    cvd_ok = (cvd_delta > 0) if bullish else (cvd_delta < 0)
    threshold = (
        engine.MIN_LFS_SCORE_REAL_CVD
        if cvd_source == "AGGTRADES_REAL"
        else engine.MIN_LFS_SCORE_PROXY_CVD
    )
    components = {
        "liquidity_sweep": 1.0 if sweep_ok else 0.0,
        "order_block": 1.0 if ob_ok else 0.0,
        "fair_value_gap": 1.0 if fvg_ok else 0.0,
        "ichimoku_bias": 1.0 if bias_ok else 0.0,
        "cvd": 1.0 if cvd_ok else 0.0,
    }
    lfs = engine._score(components)
    lfs_pass = lfs >= threshold
    expected = "BULLISH" if bullish else "BEARISH"
    confluence_parts = {
        "bias_4h_aligned": bias4 == expected,
        "bias_1h_aligned": bias1 == expected,
        "lfs_above_threshold": lfs_pass,
        "tenkan_kijun_cross_10": cross,
        "zone_distance_within_0_80_pct": zone_ok,
    }
    confluence = 20 * sum(confluence_parts.values())
    # ترتیب رد، همان ترتیب منطقی موتور و فیلتر نهایی main.py است.
    if bias4 != expected:
        rejected = "BIAS_4H_NOT_ALIGNED"
    elif bias1 != expected:
        rejected = "BIAS_1H_NOT_ALIGNED"
    elif not lfs_pass:
        rejected = "LFS_THRESHOLD"
    elif not cross:
        rejected = "CROSS_10_NOT_FOUND"
    elif not zone_ok:
        rejected = "ZONE_DISTANCE_OVER_0_80_PCT_OR_NO_ZONE"
    elif not sweep_ok:
        rejected = "LIQUIDITY_SWEEP"
    elif not cvd_ok:
        rejected = "CVD_DIRECTION"
    elif confluence < 60:
        rejected = "WATCHLIST_SCORE_BELOW_60"
    else:
        rejected = "NONE"

    return {
        "direction": direction,
        "lfs_score": lfs,
        "lfs_threshold": threshold,
        "lfs_pass": lfs_pass,
        "sweep_detected": sweep_ok,
        "order_block_detected": ob_ok,
        "fvg_detected": fvg_ok,
        "ob_fvg_reaction": zone_ok,
        "zone_type": zone["zone_type"],
        "zone_distance_pct": zone["distance_pct"],
        "zone_distance_limit_pct": engine.MAX_ZONE_DISTANCE_PCT,
        "tenkan_kijun_cross": cross,
        "cross_lookback": engine.CROSS_LOOKBACK,
        "confluence_score": confluence,
        "confluence_components": confluence_parts,
        "cvd_direction_pass": cvd_ok,
        "htf_bias_pass": bias_ok,
        "rejected_by_gate": rejected,
    }


def diagnose_symbol(symbol: str, fetcher: LiveOHLCVFetcher) -> dict[str, Any]:
    try:
        rows = fetcher.fetch_symbol(symbol)
    except Exception as exc:
        return {
            "symbol": symbol,
            "gates": {
                "data_available": False,
                "cvd_source": "UNAVAILABLE",
                "bias_4h": "UNAVAILABLE",
                "bias_1h": "UNAVAILABLE",
                "inside_kumo_4h": None,
                "lfs_score": None,
                "lfs_threshold": None,
                "lfs_pass": False,
                "sweep_detected": False,
                "tenkan_kijun_cross": False,
                "ob_fvg_reaction": False,
                "confluence_score": 0,
                "rejected_by_gate": "DATA_FETCH_FAILED",
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            },
            "directions": [],
        }

    if len(rows) < MIN_CLOSED_BARS:
        return {
            "symbol": symbol,
            "gates": {
                "data_available": False,
                "closed_15m_bars": len(rows),
                "cvd_source": "UNAVAILABLE",
                "bias_4h": "UNAVAILABLE",
                "bias_1h": "UNAVAILABLE",
                "inside_kumo_4h": None,
                "lfs_score": None,
                "lfs_threshold": None,
                "lfs_pass": False,
                "sweep_detected": False,
                "tenkan_kijun_cross": False,
                "ob_fvg_reaction": False,
                "confluence_score": 0,
                "rejected_by_gate": "INSUFFICIENT_CLOSED_15M_BARS",
            },
            "directions": [],
        }

    rows = sorted(rows, key=lambda row: int(row["open_time"]))
    bars_1h = engine.aggregate_bars(rows, 4)
    bars_4h = engine.aggregate_bars(rows, 16)
    if len(bars_1h) < 80 or len(bars_4h) < 80:
        return {
            "symbol": symbol,
            "gates": {
                "data_available": True,
                "closed_15m_bars": len(rows),
                "bars_1h": len(bars_1h),
                "bars_4h": len(bars_4h),
                "cvd_source": "UNAVAILABLE",
                "bias_4h": "UNKNOWN",
                "bias_1h": "UNKNOWN",
                "inside_kumo_4h": None,
                "lfs_score": None,
                "lfs_threshold": None,
                "lfs_pass": False,
                "sweep_detected": False,
                "tenkan_kijun_cross": False,
                "ob_fvg_reaction": False,
                "confluence_score": 0,
                "rejected_by_gate": "INSUFFICIENT_HTF_HISTORY",
            },
            "directions": [],
        }

    bias4, cloud = engine._bias_4h(bars_4h)
    bias1, _ = engine._bias_1h(bars_1h)
    current_close = float(rows[-1]["close"])
    inside = _inside_kumo(current_close, cloud.get("span_a"), cloud.get("span_b"))
    sweep = engine.detect_sweep(rows)
    atr_value = engine.atr(rows)
    cvd_delta = engine.cvd_proxy_from_klines(rows)
    cvd_source = "PROXY_OHLCV"
    cross_buy = tenkan_kijun_cross(rows, "BUY")
    cross_sell = tenkan_kijun_cross(rows, "SELL")

    buy = _direction_diagnostic(
        rows, "BUY", bias4, bias1, sweep, atr_value,
        cvd_delta, cvd_source, cross_buy,
    )
    sell = _direction_diagnostic(
        rows, "SELL", bias4, bias1, sweep, atr_value,
        cvd_delta, cvd_source, cross_sell,
    )
    directions = [buy, sell]
    selected = max(
        directions,
        key=lambda item: (item["confluence_score"], item["lfs_score"]),
    )
    return {
        "symbol": symbol,
        "gates": {
            "data_available": True,
            "closed_15m_bars": len(rows),
            "bars_1h": len(bars_1h),
            "bars_4h": len(bars_4h),
            "data_source": rows[-1].get("data_source", "UNSPECIFIED"),
            "cvd_source": cvd_source,
            "cvd_delta": round(cvd_delta, 10),
            "diagnostic_direction": selected["direction"],
            "bias_4h": bias4,
            "bias_1h": bias1,
            "inside_kumo_4h": inside,
            "lfs_score": selected["lfs_score"],
            "lfs_threshold": selected["lfs_threshold"],
            "lfs_pass": selected["lfs_pass"],
            "sweep_detected": selected["sweep_detected"],
            "tenkan_kijun_cross": selected["tenkan_kijun_cross"],
            "ob_fvg_reaction": selected["ob_fvg_reaction"],
            "confluence_score": selected["confluence_score"],
            "rejected_by_gate": selected["rejected_by_gate"],
            "watchlist_threshold": engine.WATCHLIST_CONFLUENCE_THRESHOLD,
            "stage1_threshold_label": "LFS_0.30_CROSS_10_ZONE_0.80_WATCHLIST_60",
        },
        "directions": directions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="تشخیص Gateها برای ۲۷ نماد LRT-15m")
    parser.add_argument("--universe", default="../config/universe.json")
    parser.add_argument("--output", default="artifacts/diagnostics/gates_diagnostic.json")
    parser.add_argument("--limit", type=int, default=1500)
    args = parser.parse_args()

    universe = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; found {len(symbols)}")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    fetcher = LiveOHLCVFetcher(limit=args.limit)
    results = []
    try:
        for index, symbol in enumerate(symbols, start=1):
            item = diagnose_symbol(symbol, fetcher)
            results.append(item)
            gates = item["gates"]
            print(
                f"GATE_DIAG {index}/27 {symbol} "
                f"data={gates['data_available']} "
                f"direction={gates.get('diagnostic_direction', 'NA')} "
                f"lfs={gates['lfs_score']} "
                f"confluence={gates['confluence_score']} "
                f"reject={gates['rejected_by_gate']}",
                flush=True,
            )
            print(json.dumps(item, ensure_ascii=False, separators=(",", ":")), flush=True)
    finally:
        fetcher.close()

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "universe_count": 27,
        "symbols_analyzed": len(results),
        "data_available_count": sum(bool(x["gates"]["data_available"]) for x in results),
        "rejected_by_gate_counts": {},
        "results": results,
    }
    for item in results:
        gate = item["gates"]["rejected_by_gate"]
        report["rejected_by_gate_counts"][gate] = report["rejected_by_gate_counts"].get(gate, 0) + 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("DIAGNOSTIC_REPORT " + json.dumps({
        "symbols_analyzed": len(results),
        "data_available": report["data_available_count"],
        "rejected_by_gate_counts": report["rejected_by_gate_counts"],
        "output": str(output),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
