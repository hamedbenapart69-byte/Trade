"""Fail-closed tombstone for the retired 1H research engine."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    config_path = Path(__file__).with_name("config.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    engine = config.get("engine") or {}
    print(json.dumps({
        "pipeline_status": "DISABLED_LEGACY_ENGINE",
        "engine": engine.get("version", "RETIRED"),
        "market_scan": "DISABLED",
        "dashboard_publication": "DISABLED",
        "telegram_delivery": "DISABLED",
        "manual_trade_only": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
