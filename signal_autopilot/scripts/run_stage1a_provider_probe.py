"""اجرای مستقل Stage 1a و تولید گزارش پوشش داده."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.stage1a_data_provider import Stage1ADataProvider


def main() -> int:
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    provider = Stage1ADataProvider(config)
    try:
        report = provider.run()
    finally:
        provider.close()
    # قرارداد خروجی: کلید provider همیشه وجود دارد؛ هیچ مصرف‌کننده‌ای KeyError نمی‌گیرد.
    report.setdefault("provider_selected", "NONE")
    report.setdefault("coverage_per_symbol", [])
    for row in report["coverage_per_symbol"]:
        row.setdefault("provider", row.get("ohlcv_provider", "BINANCE_VISION"))
    out = ROOT / "data" / "stage1a_provider_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "stage1a_status": report.get("stage1a_status", "FAIL"),
        "symbols_scanned": report.get("symbols_scanned", 0),
        "symbols_qualifying": report.get("symbols_qualifying", 0),
        "symbols_proxy": report.get("symbols_proxy", 0),
        "provider_selected": report.get("provider_selected", "NONE"),
        "report": str(out),
    }, ensure_ascii=False))
    return 0 if report.get("stage1a_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
