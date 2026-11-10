"""تنظیم مسیر import برای تست‌های ریشه و signal_autopilot بدون تداخل بسته‌ها."""
from pathlib import Path
import sys

SIGNAL_AUTOPILOT_PATH = str(Path(__file__).resolve().parent / "signal_autopilot")
if SIGNAL_AUTOPILOT_PATH not in sys.path:
    # مسیر را بعد از ریشه اضافه می‌کنیم تا app/ ریشه بر signal_autopilot/app مقدم بماند.
    sys.path.append(SIGNAL_AUTOPILOT_PATH)
