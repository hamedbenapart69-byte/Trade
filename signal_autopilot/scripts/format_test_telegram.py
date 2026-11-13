"""Send a clearly labelled ARB-only Telegram format test using a stored research record."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.chart_renderer_lrt15m import render_lrt15m_chart
from modules.live_data_adapter import LiveOHLCVFetcher
from telegram_bot import send_signal_to_telegram


def load_arb_research_record() -> dict:
    raw = subprocess.run(
        ["git", "show", "origin/stage1-research-data:signal_autopilot/state/research_signals.json"],
        check=True, capture_output=True, text=True,
    ).stdout
    payload = json.loads(raw)
    matches = [
        row for row in payload.get("signals", [])
        if row.get("symbol") == "ARBUSDT"
        and row.get("mode") == "RESEARCH"
        and row.get("decision") == "RESEARCH_WATCHLIST"
        and row.get("telegram_status") == "SENT"
    ]
    if not matches:
        raise RuntimeError("NO_SENT_ARB_RESEARCH_RECORD")
    return sorted(matches, key=lambda row: row.get("created_at_utc", ""))[0]


def main() -> None:
    record = load_arb_research_record()
    fetcher = LiveOHLCVFetcher(limit=500, stats_limit=2500, fetch_stats=True)
    try:
        candles = fetcher.fetch_symbol("ARBUSDT")
    finally:
        fetcher.close()

    signal = {
        "symbol": "ARBUSDT",
        "direction": record["direction"],
        "engine": "LRT-15m",
        "timeframe": "15m",
        "signal_id": record["signal_id"],
        "mode": "RESEARCH",
        "decision": "RESEARCH_WATCHLIST",
        "calibration_status": "UNCALIBRATED",
        "format_test": True,
        "confluence_score": record.get("tier_score", record.get("raw_score")),
        "tier": "RESEARCH",
        "confluence_components": record.get("points", {}),
        "ichimoku": {
            "bias": record.get("higher_timeframe_bias", {}).get("4h_kumo", "UNAVAILABLE"),
            "price_vs_kumo": "UNAVAILABLE",
            "tenkan_kijun": "UNAVAILABLE",
            "chikou": "UNAVAILABLE",
        },
        "levels": {
            "entry": record.get("entry_reference"),
            "stop_loss": record.get("stop_reference"),
            "tp1": record.get("target_reference"),
            "tp2": None,
            "tp3": None,
            "rr": record.get("rr_reference"),
        },
        "calibration": {
            "lfs_status": record.get("lfs_status", "UNAVAILABLE"),
            "lfs_source": "LFS_V2",
            "lfs_coverage_pct": record.get("lfs_coverage_pct"),
            "coverage_per_symbol": record.get("data_sources"),
        },
        "costs": {},
        "risk_flags": [
            "FORMAT TEST ONLY: historical ARB research data, not a current trade signal",
            "Chart uses newly fetched closed candles and is not an entry recommendation",
        ],
        "hypothesis": record.get("hypothesis", "UNAVAILABLE"),
        "created_at_utc": record.get("created_at_utc", "UNAVAILABLE"),
    }
    chart_path = Path("artifacts/format_test/ARBUSDT_format_test.png")
    render_lrt15m_chart("ARBUSDT", list(candles), signal, chart_path)
    message_id = send_signal_to_telegram(signal, chart_path, format_test=True)
    if not isinstance(message_id, int) or message_id <= 0:
        raise RuntimeError("TELEGRAM_FORMAT_TEST_NOT_SENT")
    print(f"FORMAT_TEST_SIGNAL_ID={record['signal_id']}")
    print(f"FORMAT_TEST_MESSAGE_ID={message_id}")
    print(f"FORMAT_TEST_CHART_PATH={chart_path}")


if __name__ == "__main__":
    main()
