"""سازگاری موقت برای تست‌ها؛ پیاده‌سازی یک‌ساعته فقط در legacy نگهداری می‌شود."""
from __future__ import annotations

from legacy.signal_engine_1h import C10, atr, build_signal, ema, generate_signals

__all__ = ["C10", "atr", "build_signal", "ema", "generate_signals"]
