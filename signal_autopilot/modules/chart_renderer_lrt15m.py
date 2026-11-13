"""رندر نمودار واقعی LRT-15m با کندل، ایچیموکو و سطوح مرجع."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def render_lrt15m_chart(
    symbol: str,
    candles: list[dict[str, Any]],
    signal: dict[str, Any],
    output_path: str | Path,
) -> Path:
    if len(candles) < 80:
        raise ValueError("chart_requires_at_least_80_closed_candles")

    frame = pd.DataFrame(candles[-160:])
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(15, 8), dpi=140)
    x = np.arange(len(frame))

    for i, row in frame.iterrows():
        idx = int(i)
        rising = float(row["close"]) >= float(row["open"])
        candle_color = "#16856b" if rising else "#c44e52"
        ax.vlines(idx, float(row["low"]), float(row["high"]), color=candle_color, linewidth=1)
        bottom = min(float(row["open"]), float(row["close"]))
        height = abs(float(row["close"]) - float(row["open"]))
        if height == 0:
            height = max(abs(float(row["close"])) * 0.00003, 1e-12)
        ax.bar(idx, height, bottom=bottom, width=0.62, color=candle_color, edgecolor=candle_color)

    ax.plot(x, tenkan, label="Tenkan 9", linewidth=1.0)
    ax.plot(x, kijun, label="Kijun 26", linewidth=1.0)
    ax.plot(x, span_a, label="Senkou A", linewidth=0.9)
    ax.plot(x, span_b, label="Senkou B", linewidth=0.9)

    a = span_a.to_numpy(dtype=float)
    b = span_b.to_numpy(dtype=float)
    valid = np.isfinite(a) & np.isfinite(b)
    if valid.any():
        ax.fill_between(x, a, b, where=valid, alpha=0.13, interpolate=True, label="Kumo")

    levels = signal.get("levels", {})
    line_specs = [
        ("Entry Reference", levels.get("entry"), "#2471a3"),
        ("SL Reference", levels.get("stop_loss"), "#c0392b"),
        ("TP1 Reference", levels.get("tp1"), "#239b56"),
        ("TP2 Reference", levels.get("tp2"), "#239b56"),
        ("TP3 Reference", levels.get("tp3"), "#239b56"),
    ]
    for label, value, color in line_specs:
        if isinstance(value, (int, float)) and np.isfinite(value):
            ax.axhline(float(value), linestyle="--", linewidth=1.0, color=color, label=f"{label}: {value:.8g}")

    test_prefix = "[FORMAT TEST - NOT A REAL SIGNAL] | " if signal.get("format_test") is True else ""
    ax.set_title(
        f"{test_prefix}{symbol} | 15m | Confluence {signal.get('confluence_score')} / 100 | "
        f"UNCALIBRATED | CLOSED CANDLES"
    )
    ax.set_xlabel("۱۵ دقیقه‌ای بسته‌شده")
    ax.set_ylabel("Price")
    ax.grid(alpha=0.2)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
