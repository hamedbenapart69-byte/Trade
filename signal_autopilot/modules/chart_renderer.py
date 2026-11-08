"""ساخت نمودار کندلی واقعی برای پیوست سیگنال تلگرام."""
from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from datetime import datetime, timezone

from .signal_engine import ema


def render_signal_chart(signal: dict[str, Any]) -> bytes:
    """رندر نمودار ۱ساعته با EMA20/50 و Entry/SL/TP؛ فقط از کندل‌های همان سیگنال."""
    candles = signal.get("chart_candles") or []
    if len(candles) < 30:
        raise ValueError("chart_requires_at_least_30_candles")

    closes = [float(c["close"]) for c in candles]
    ema20_values = ema(closes, 20)
    ema50_values = ema(closes, 50)
    # EMA خروجی از دوره شروع می‌شود؛ محورهای متناظر جداگانه ساخته می‌شوند.
    x = [datetime.fromtimestamp(int(c["timestamp"]) / 1000, tz=timezone.utc) for c in candles]
    fig, ax = plt.subplots(figsize=(13, 7), dpi=150)
    fig.subplots_adjust(left=0.07, right=0.83, top=0.86, bottom=0.15)

    for i, candle in enumerate(candles):
        o, h, low, close = (float(candle[k]) for k in ("open", "high", "low", "close"))
        rising = close >= o
        candle_color = "#16a34a" if rising else "#dc2626"
        ax.vlines(x[i], low, h, color=candle_color, linewidth=1.0, zorder=2)
        body_low = min(o, close)
        body_height = max(abs(close - o), max(abs(close), 1.0) * 0.00005)
        width = 0.03
        ax.add_patch(Rectangle((mdates.date2num(x[i]) - width / 2, body_low),
                               width, body_height, facecolor=candle_color,
                               edgecolor=candle_color, linewidth=0.5, zorder=3))

    ax.plot(x[19:], ema20_values, label="EMA 20", linewidth=1.5, color="#2563eb")
    ax.plot(x[49:], ema50_values, label="EMA 50", linewidth=1.5, color="#f59e0b")

    levels = [
        ("ENTRY", signal.get("entry"), "#2563eb", "--"),
        ("STOP LOSS", signal.get("stop_loss"), "#dc2626", "-."),
        ("TP1", (signal.get("take_profit") or [None])[0], "#16a34a", ":"),
        ("TP2", (signal.get("take_profit") or [None, None])[1] if len(signal.get("take_profit") or []) > 1 else None, "#15803d", ":"),
    ]
    for label, value, color, style in levels:
        if value is not None:
            ax.axhline(float(value), color=color, linestyle=style, linewidth=1.25, alpha=0.95)
            ax.text(1.005, float(value), f"{label}  {float(value):.8g}",
                    transform=ax.get_yaxis_transform(), color=color, fontsize=8,
                    va="center", clip_on=False)

    direction = "LONG" if signal.get("side") == "BUY" else "SHORT"
    reason = "EMA20 above EMA50; relative spread > 0.5%; risk levels from ATR14" if direction == "LONG" else "EMA20 below EMA50; relative spread > 0.5%; risk levels from ATR14"
    title = f"{signal.get('symbol', 'UNKNOWN')}  |  {direction}  |  1H  |  EMA TREND"
    fig.suptitle(title, fontsize=15, fontweight="bold", x=0.07, ha="left")
    ax.set_title(reason[:160], fontsize=9, loc="left", color="#475569", pad=12)
    ax.set_ylabel("Price")
    ax.set_xlabel("UTC")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="upper left", frameon=False, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc))
    fig.autofmt_xdate(rotation=20)
    ax.text(0.01, -0.22,
            "Analysis: EMA20/EMA50 trend continuation | Confidence: NOT CALIBRATED | Manual trade only",
            transform=ax.transAxes, fontsize=8, color="#64748b")
    output = BytesIO()
    fig.savefig(output, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output.getvalue()
