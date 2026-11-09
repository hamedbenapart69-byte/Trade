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
    WATCHLIST_CONFLUENCE_THRESHOLD,
    aggregate_bars,
    evaluate_stage1_symbol,
    score_stage1_confluence,
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
) -> tuple[int, dict[str, int]]:
    """امتیاز پنج مؤلفهٔ مصوب؛ LFS فقط Veto است و امتیاز Confluence نیست."""
    expected = "BULLISH" if direction == "BUY" else "BEARISH"
    biases = engine_result.get("higher_timeframe_bias") or {}
    lfs_parts = engine_result.get("lfs_components") or {}
    zone_ok = bool(engine_result.get("zone_present")) or (
        engine_result.get("zone_type") not in {None, "NONE"}
        and isinstance(engine_result.get("zone_distance_pct"), (int, float))
        and float(engine_result["zone_distance_pct"]) <= 0.80
    )
    components = {
        "bias_4h": biases.get("4h_kumo") == expected,
        "bias_1h": biases.get("1h_kijun") == expected,
        "sweep": bool(lfs_parts.get("liquidity_sweep", False)),
        "zone_reaction": zone_ok,
        "cross": tenkan_kijun_cross(rows, direction, lookback=10),
    }
    cvd = engine_result.get("cvd") or {}
    scored = score_stage1_confluence(
        components,
        str(cvd.get("source", "PROXY_OHLCV")),
        cvd.get("source") == "AGGTRADES_REAL" and (
            (float(cvd.get("delta", 0.0)) > 0 and direction == "BUY")
            or (float(cvd.get("delta", 0.0)) < 0 and direction == "SELL")
        ),
    )
    return int(scored["raw_score"]), scored["points"]

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


def process_symbol(
    symbol: str, fetcher: LiveOHLCVFetcher
) -> tuple[dict[str, Any] | None, str, dict[str, Any]]:
    try:
        rows = fetcher.fetch_symbol(symbol)
        result = evaluate_stage1_symbol(symbol, rows)
        diagnostic = {
            key: result.get(key)
            for key in (
                "symbol", "direction", "veto", "decision", "tier", "raw_score",
                "tier_score", "points", "components", "lfs_score", "lfs_source",
                "lfs_coverage_pct", "lfs_status", "lfs_components", "api_status",
                "reason", "higher_timeframe_bias", "price_vs_kumo", "zone_type",
                "zone_distance_pct", "rows_available",
            )
        }
        if result.get("decision") != "WATCHLIST":
            return None, str(result.get("reason", result.get("decision", "NO_TRADE"))), diagnostic

        lfs_source = str(result.get("lfs_source", "UNAVAILABLE"))
        lfs_status = str(result.get("lfs_status", "INSUFFICIENT"))
        levels = {
            "entry": float(result["entry"]),
            "stop_loss": float(result["stop_loss"]),
            "tp1": float(result["entry"]) + (1 if result["direction"] == "BUY" else -1) * abs(float(result["entry"]) - float(result["stop_loss"])),
            "tp2": float(result["take_profit"]),
            "tp3": float(result["entry"]) + (3 if result["direction"] == "BUY" else -3) * abs(float(result["entry"]) - float(result["stop_loss"])),
            "rr": float(result.get("rr", 2.0)),
        }
        ichimoku_data = {
            "bias": (
                f"4H Kumo={result['higher_timeframe_bias']['4h_kumo']} | "
                f"1H Kijun={result['higher_timeframe_bias']['1h_kijun']}"
            ),
            "price_vs_kumo": result.get("price_vs_kumo", "UNAVAILABLE"),
            "tenkan_kijun": "SEE_CONFLUENCE_BREAKDOWN",
            "chikou": "NOT_USED_AS_STAGE_1_GATE",
        }
        created = datetime.now(timezone.utc).isoformat()
        spread_pct = 0.0008  # PROXY مصوب کاربر؛ نه Spread اندازه‌گیری‌شده
        points = result.get("points") or {}
        signal = {
            "symbol": symbol,
            "direction": result["direction"],
            "engine": "LRT-15m + ICT + Ichimoku",
            "timeframe": "15m",
            "status": "WATCHLIST",
            "tier": result.get("tier"),
            "calibration_status": "UNCALIBRATED",
            "stage_label": "STAGE_1_UNCALIBRATED",
            "confluence_score": result.get("raw_score"),
            "confluence_tier_score": result.get("tier_score"),
            "confluence_components": points,
            "stage1_threshold_label": "VETO_3_LFS_0.30_PROXY_0.70_REAL|CONFLUENCE_100_A_80_B_60_MONITORING",
            "signal_id": _signal_id(symbol, result["direction"], int(rows[-1]["open_time"])),
            "created_at_utc": created,
            "ichimoku": ichimoku_data,
            "levels": levels,
            "calibration": {
                "lfs_status": lfs_status,
                "lfs_source": lfs_source,
                "coverage_per_symbol": f"{len(rows)}/500 closed 15m + {len(getattr(rows, 'stats_1h', []) or [])}/2500 closed 1H candles",
            },
            "costs": {
                "fee_pct": None,
                "slippage_pct": None,
                "spread_pct": spread_pct,
                "spread_source": "PROXY",
            },
            "risk_flags": [
                "STAGE_1_UNCALIBRATED: confidence و EV کالیبره نشده‌اند.",
                "SPREAD_SOURCE=PROXY: مقدار 0.0008 (0.08%) طبق مصوبه؛ Bid/Ask واقعی متصل نیست.",
                "SPREAD_LIMIT_UNCONFIGURED: سقف عددی مصوب ارائه نشده؛ هیچ ادعای RISK_FLAG_SPREAD_HIGH نمی‌شود.",
                "COSTS_INCOMPLETE: Fee و Slippage کامل محاسبه نشده‌اند.",
                "سطوح Entry/SL/TP مرجع تحلیلی‌اند و بک‌تست/تأیید نشده‌اند.",
            ],
            "hypothesis": result.get("hypothesis", "UNAVAILABLE"),
            "falsification": result.get("falsification", "UNAVAILABLE"),
            "lfs_score": result.get("lfs_score"),
            "lfs_coverage_pct": result.get("lfs_coverage_pct"),
            "lfs_status": result.get("lfs_status"),
            "lfs_components": result.get("lfs_components"),
            "api_status": result.get("api_status"),
            "cvd": result.get("cvd"),
            "data_sources": result.get("data_sources", []),
            "last_closed_candle_utc": datetime.fromtimestamp(
                int(rows[-1]["open_time"]) / 1000, timezone.utc
            ).isoformat(),
        }
        chart_path = ARTIFACT_DIR / f"{symbol}_15m_{signal['signal_id']}.png"
        render_lrt15m_chart(symbol, rows, signal, chart_path)
        return {**signal, "chart_path": str(chart_path)}, "CANDIDATE", diagnostic
    except Exception as exc:
        LOG.exception("%s processing failed; skipping symbol.", symbol)
        return None, f"{type(exc).__name__}:{str(exc)[:160]}", {
            "symbol": symbol,
            "direction": None,
            "veto": "DATA_INSUFFICIENT",
            "decision": "NO_TRADE",
            "reason": f"{type(exc).__name__}:{str(exc)[:160]}",
        }

def main() -> int:
    symbols = load_universe()
    telegram_ready = verify_telegram_connection()
    fetcher = LiveOHLCVFetcher(limit=500, stats_limit=2500)
    tracker = SignalTracker(STATE_PATH)

    processed = 0
    skipped = 0
    candidates = 0
    sent = 0
    telegram_message_ids: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    try:
        for symbol in symbols:
            signal, reason, diagnostic = process_symbol(symbol, fetcher)
            diagnostics.append(diagnostic)
            if signal is None:
                skipped += 1
                LOG.info("SYMBOL_SKIPPED %s reason=%s", symbol, reason)
                continue

            processed += 1
            candidates += 1
            tracker.upsert({key: value for key, value in signal.items() if key != "chart_path"})
            chart_path = signal.pop("chart_path")
            message_id = (
                send_signal_to_telegram(signal, chart_path)
                if telegram_ready else None
            )
            if isinstance(message_id, int) and message_id > 0:
                sent += 1
                telegram_message_ids.append({
                    "symbol": signal["symbol"],
                    "signal_id": signal["signal_id"],
                    "message_id": message_id,
                })
                LOG.info(
                    "TELEGRAM_SIGNAL_MESSAGE_ID symbol=%s message_id=%s",
                    signal["symbol"], message_id,
                )
            else:
                LOG.warning("SIGNAL_NOT_DELIVERED %s", signal["signal_id"])
    finally:
        fetcher.close()

    tracker.save()
    REPORT_PATH = Path(__file__).resolve().parent / "artifacts" / "stage1_lrt_report.json"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    veto_counts: dict[str, list[str]] = {}
    for row in diagnostics:
        veto = str(row.get("veto", "UNAVAILABLE"))
        if veto != "PASS":
            veto_counts.setdefault(veto, []).append(str(row["symbol"]))
    api_keys = ("funding", "oi_1h", "oi_1d", "long_short_ratio")
    okx_api_distribution = {
        key: {
            "available_symbols": sum(1 for row in diagnostics if (row.get("api_status") or {}).get(key, False)),
            "unavailable_symbols": sum(1 for row in diagnostics if not (row.get("api_status") or {}).get(key, False)),
        }
        for key in api_keys
    }
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "okx_api_distribution": okx_api_distribution,
        "stage": "STAGE_1_UNCALIBRATED",
        "universe_count": len(symbols),
        "symbols_reported": len(diagnostics),
        "watchlist_count": candidates,
        "telegram_preflight": telegram_ready,
        "telegram_signals_sent": sent,
        "telegram_message_ids": telegram_message_ids,
        "okx_api_distribution": okx_api_distribution,
        "veto_distribution": {
            key: {"count": len(value), "symbols": value}
            for key, value in sorted(veto_counts.items())
        },
        "symbols": diagnostics,
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW",
        "spread": {"value": 0.0008, "source": "PROXY", "limit": None},
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "universe": len(symbols),
        "symbols_reported": len(diagnostics),
        "candidate_symbols": candidates,
        "symbols_skipped": skipped,
        "telegram_preflight": telegram_ready,
        "telegram_signals_sent": sent,
        "telegram_message_ids": telegram_message_ids,
        "open_signals_in_state": len(tracker.snapshot()["open_signals"]),
        "report_path": str(REPORT_PATH),
        "calibration": "UNCALIBRATED",
        "decision_policy": "WATCHLIST_ONLY",
    }
    LOG.info("RUN_SUMMARY %s", json.dumps(summary, ensure_ascii=False))

    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("## Stage 1 LRT: گزارش ۲۷ نماد\\n\\n")
            handle.write("| شاخص | مقدار |\\n|---|---:|\\n")
            for key, value in summary.items():
                handle.write(f"| {key} | {json.dumps(value, ensure_ascii=False)} |\\n")
            handle.write("\\n### Confluence و Veto به تفکیک نماد\\n\\n")
            handle.write("| Symbol | Veto | Bias4H | Bias1H | Sweep | Zone | Cross | Total | Tier |\\n")
            handle.write("|---|---|---|---|---|---|---|---:|---|\\n")
            for row in diagnostics:
                components = row.get("components") or {}
                points = row.get("points") or {}
                total = row.get("raw_score")
                tier = row.get("tier") or row.get("decision") or "NO_TRADE"
                handle.write(
                    f"| {row['symbol']} | {row.get('veto')} | "
                    f"{components.get('bias_4h', '—')} | {components.get('bias_1h', '—')} | "
                    f"{components.get('sweep', '—')} | {points.get('zone_reaction', '—')} | "
                    f"{components.get('cross', '—')} | {total if total is not None else '—'} | {tier} |\\n"
                )
            if candidates == 0:
                handle.write("\\n### توزیع Veto Gateها\\n\\n")
                handle.write("| Veto Gate | تعداد نماد رد شده | نمادهای رد شده |\\n|---|---:|---|\\n")
                for gate, names in sorted(veto_counts.items()):
                    handle.write(f"| {gate} | {len(names)} | {', '.join(names)} |\\n")
                if not veto_counts:
                    handle.write("| بدون Veto؛ رد در Scoring | 0 | — |\\n")

    return 0 if len(diagnostics) == len(symbols) else 1


if __name__ == "__main__":
    raise SystemExit(main())
