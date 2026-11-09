"""اجرای زندهٔ LRT-15m روی Universe ثابت؛ فقط WATCHLIST و بدون اجرای سفارش."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.chart_renderer_lrt15m import render_lrt15m_chart
from modules.signal_tracker import SignalTracker
from modules.live_data_adapter import LiveOHLCVFetcher
from modules.lrt15m_engine import (
    MIN_LFS_SCORE_PROXY_CVD,
    MIN_LFS_SCORE_REAL_CVD,
    aggregate_bars,
    analyze_symbol,
    ichimoku,
)
from telegram_bot import send_signal_to_telegram, verify_telegram_connection

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "config" / "universe.json"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "charts"
STATE_PATH = Path(__file__).resolve().parent / "state" / "open_signals.json"

LOG = logging.getLogger("trader_me.main")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def load_universe() -> list[str]:
    payload = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    symbols = payload.get("symbols") if isinstance(payload, dict) else payload
    if not isinstance(symbols, list):
        raise ValueError("universe_symbols_must_be_a_list")
    cleaned = [str(item).strip().upper() for item in symbols if str(item).strip()]
    if len(cleaned) != 27 or len(set(cleaned)) != 27:
        raise ValueError(f"universe_must_contain_27_unique_symbols_found_{len(cleaned)}")
    return cleaned


def tenkan_kijun_cross(rows: list[dict[str, Any]], direction: str, lookback: int = 10) -> bool:
    """سازگاری API قدیمی؛ منطق اصلی Cross در موتور LRT پیاده‌سازی شده است."""
    from modules.lrt15m_engine import tenkan_kijun_cross as engine_cross
    return engine_cross(rows, direction, lookback)


def calculate_confluence(
    engine_result: dict[str, Any],
    rows: list[dict[str, Any]],
    direction: str,
) -> tuple[int, dict[str, bool]]:
    """پنج Gate مصوب: Bias 4H، Bias 1H، LFS، Cross-10 و فاصله Zone."""
    from modules.lrt15m_engine import (
        MAX_ZONE_DISTANCE_PCT, MIN_LFS_SCORE_PROXY_CVD,
        MIN_LFS_SCORE_REAL_CVD, WATCHLIST_CONFLUENCE_THRESHOLD,
    )
    expected = "BULLISH" if direction == "BUY" else "BEARISH"
    biases = engine_result.get("higher_timeframe_bias") or {}
    bias4_ok = biases.get("4h_kumo") == expected
    bias1_ok = biases.get("1h_kijun") == expected
    cvd = engine_result.get("cvd") or {}
    threshold = MIN_LFS_SCORE_REAL_CVD if cvd.get("source") == "AGGTRADES_REAL" else MIN_LFS_SCORE_PROXY_CVD
    lfs_score = engine_result.get("lfs_score")
    lfs_ok = isinstance(lfs_score, (int, float)) and float(lfs_score) >= threshold
    cross_ok = tenkan_kijun_cross(rows, direction, lookback=10)
    zone_distance_value = engine_result.get("zone_distance_pct")
    zone_ok = isinstance(zone_distance_value, (int, float)) and float(zone_distance_value) <= MAX_ZONE_DISTANCE_PCT
    components = {
        "bias_4h_aligned": bias4_ok,
        "bias_1h_aligned": bias1_ok,
        "lfs_above_threshold": lfs_ok,
        "tenkan_kijun_cross_10": cross_ok,
        "zone_distance_within_0_80_pct": zone_ok,
    }
    return 20 * sum(1 for value in components.values() if value), components


def _ichimoku_status(rows: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    bars_1h = aggregate_bars(rows, 4)
    bars_4h = aggregate_bars(rows, 16)
    i15 = ichimoku(rows)
    i4h = ichimoku(bars_4h) if bars_4h else {}
    current = float(rows[-1]["close"])
    a, b = i4h.get("span_a"), i4h.get("span_b")
    if a is None or b is None:
        price_vs_kumo = "UNAVAILABLE"
    elif current > max(a, b):
        price_vs_kumo = "ABOVE_KUMO"
    elif current < min(a, b):
        price_vs_kumo = "BELOW_KUMO"
    else:
        price_vs_kumo = "INSIDE_KUMO"

    tenkan, kijun = i15.get("tenkan"), i15.get("kijun")
    if tenkan is None or kijun is None:
        tk = "UNAVAILABLE"
    else:
        tk = "TENKAN_ABOVE_KIJUN" if tenkan > kijun else "TENKAN_BELOW_OR_EQUAL_KIJUN"

    chikou = (
        "ABOVE_PRICE_26_BARS_AGO"
        if len(rows) > 26 and current > float(rows[-27]["close"])
        else "BELOW_OR_EQUAL_PRICE_26_BARS_AGO"
        if len(rows) > 26
        else "UNAVAILABLE"
    )
    biases = result.get("higher_timeframe_bias") or {}
    return {
        "bias": f"4H Kumo={biases.get('4h_kumo', 'UNAVAILABLE')} | 1H Kijun={biases.get('1h_kijun', 'UNAVAILABLE')}",
        "price_vs_kumo": price_vs_kumo,
        "tenkan_kijun": tk,
        "chikou": chikou,
    }


def _levels(result: dict[str, Any]) -> dict[str, float | None]:
    entry = float(result["entry"])
    stop = float(result["stop_loss"])
    direction = result["direction"]
    risk = abs(entry - stop)
    sign = 1 if direction == "BUY" else -1
    # TP2 همان هدف 2R موجود در موتور است؛ TP1/TP3 فقط سطوح مرجع ریاضی‌اند.
    tp2 = float(result["take_profit"])
    return {
        "entry": entry,
        "stop_loss": stop,
        "tp1": entry + sign * risk,
        "tp2": tp2,
        "tp3": entry + sign * 3 * risk,
        "rr": float(result.get("rr", 2.0)),
    }


def _signal_id(symbol: str, direction: str, open_time: int) -> str:
    raw = f"{symbol}|15m|{direction}|{open_time}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def process_symbol(symbol: str, fetcher: LiveOHLCVFetcher) -> tuple[dict[str, Any] | None, str]:
    try:
        rows = fetcher.fetch_symbol(symbol)
        if len(rows) < 1300:
            return None, f"INSUFFICIENT_CLOSED_15M_BARS:{len(rows)}"

        result = analyze_symbol(symbol, rows)
        if result.get("decision") != "WATCHLIST" or result.get("direction") not in {"BUY", "SELL"}:
            reason = str(result.get("reason", result.get("decision", "NO_SETUP")))
            diagnostics = result.get("gate_diagnostics")
            if diagnostics:
                reason += "|" + json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":"))
            return None, reason

        confluence_score, confluence_components = calculate_confluence(
            result, rows, str(result["direction"])
        )
        if confluence_score < 60:
            return None, f"CONFLUENCE_BELOW_WATCHLIST_60:{confluence_score}"

        lfs_source = (result.get("cvd") or {}).get("source", "UNAVAILABLE")
        lfs_status = "REAL" if lfs_source == "AGGTRADES_REAL" else (
            "PROXY" if "PROXY" in lfs_source else "UNAVAILABLE"
        )
        levels = _levels(result)
        ichimoku_data = _ichimoku_status(rows, result)
        created = datetime.now(timezone.utc).isoformat()
        signal = {
            "symbol": symbol,
            "direction": result["direction"],
            "engine": "LRT-15m + ICT + Ichimoku",
            "timeframe": "15m",
            "status": "WATCHLIST",
            "calibration_status": "UNCALIBRATED",
            "confluence_score": confluence_score,
            "confluence_components": confluence_components,
            "stage1_threshold_label": "LFS_0.30_CROSS_10_ZONE_0.80_WATCHLIST_60",
            "signal_id": _signal_id(symbol, result["direction"], int(rows[-1]["open_time"])),
            "created_at_utc": created,
            "ichimoku": ichimoku_data,
            "levels": levels,
            "calibration": {
                "lfs_status": lfs_status,
                "lfs_source": lfs_source,
                "coverage_per_symbol": f"{len(rows)}/1500 closed 15m candles",
            },
            "costs": {
                "fee_pct": None,
                "slippage_pct": None,
                "spread_pct": None,
            },
            "risk_flags": [
                "UNCALIBRATED: confidence و EV کالیبره نشده‌اند.",
                "SPREAD_UNAVAILABLE: اسپرد تاریخی/لحظه‌ای معتبر به موتور داده نشده است.",
                "COSTS_INCOMPLETE: هزینهٔ کامل معامله محاسبه نشده است.",
                "TP1/TP3 فقط سطوح مرجع ریاضی هستند؛ TP2 از خروجی موتور آمده است.",
            ],
            "hypothesis": result.get("hypothesis", "UNAVAILABLE"),
            "falsification": result.get("falsification", "UNAVAILABLE"),
            "lfs_score": result.get("lfs_score"),
            "lfs_components": result.get("lfs_components"),
            "cvd": result.get("cvd"),
            "data_sources": result.get("data_sources", []),
            "last_closed_candle_utc": datetime.fromtimestamp(
                int(rows[-1]["open_time"]) / 1000, timezone.utc
            ).isoformat(),
        }
        chart_path = ARTIFACT_DIR / f"{symbol}_15m_{signal['signal_id']}.png"
        render_lrt15m_chart(symbol, rows, signal, chart_path)
        return {**signal, "chart_path": str(chart_path)}, "CANDIDATE"
    except Exception as exc:
        LOG.exception("%s processing failed; skipping symbol.", symbol)
        return None, f"{type(exc).__name__}:{str(exc)[:160]}"


def main() -> int:
    symbols = load_universe()
    telegram_ready = verify_telegram_connection()
    fetcher = LiveOHLCVFetcher(limit=1500)
    tracker = SignalTracker(STATE_PATH)

    processed = 0
    skipped = 0
    candidates = 0
    sent = 0
    try:
        for symbol in symbols:
            signal, reason = process_symbol(symbol, fetcher)
            if signal is None:
                skipped += 1
                LOG.info("SYMBOL_SKIPPED %s reason=%s", symbol, reason)
                continue

            processed += 1
            candidates += 1
            tracker.upsert({key: value for key, value in signal.items() if key != "chart_path"})
            chart_path = signal.pop("chart_path")
            if telegram_ready and send_signal_to_telegram(signal, chart_path):
                sent += 1
            else:
                LOG.warning("SIGNAL_NOT_DELIVERED %s", signal["signal_id"])
    finally:
        fetcher.close()

    tracker.save()
    summary = {
        "universe": len(symbols),
        "candidate_symbols": candidates,
        "symbols_skipped": skipped,
        "telegram_preflight": telegram_ready,
        "telegram_signals_sent": sent,
        "open_signals_in_state": len(tracker.snapshot()["open_signals"]),
        "signal_state_path": str(STATE_PATH),
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY",
    }
    LOG.info("RUN_SUMMARY %s", json.dumps(summary, ensure_ascii=False))

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("## Trader_me Stage 1 Signal Bot\n\n")
            handle.write("| شاخص | مقدار |\n|---|---:|\n")
            for key, value in summary.items():
                handle.write(f"| {key} | {value} |\n")

    return 0 if processed > 0 or skipped == len(symbols) else 1


if __name__ == "__main__":
    raise SystemExit(main())
