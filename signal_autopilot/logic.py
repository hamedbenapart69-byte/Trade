"""Read-only market scan, signal computation and resilient publication."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from modules.data_fetcher import MarketDataFetcher
from legacy.signal_engine_1h import generate_signals  # موتور تاریخی؛ فقط پژوهش، خارج از مسیر تولید
from modules.storage import publish
from modules.notifier import notify_tier_a, notify_email


def main() -> None:
    fetcher = None
    try:
        fetcher = MarketDataFetcher(limit=100)
        raw = fetcher.fetch()
    except Exception as exc:
        # Preserve a fresh, explicit degraded snapshot instead of leaving stale signals online.
        raw = {
            "provider": "none",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "symbols": [],
            "symbols_processed": 0,
            "errors": {"market_data": f"{type(exc).__name__}: {str(exc)[:240]}"},
        }
    finally:
        if fetcher is not None:
            fetcher.close()

    payload = generate_signals(raw)
    # Defensive contract: the publisher must never crash on optional metadata.
    payload.setdefault("provider", raw.get("provider", "unknown"))
    payload.setdefault("quality", {})
    payload["quality"].setdefault("symbols_processed", len(raw.get("symbols") or []))
    payload["data_errors"] = raw.get("errors", {})
    notification = notify_tier_a(payload)
    email_notification = (
        notify_email(payload)
        if notification.get("status") in ("SKIPPED_NOT_CONFIGURED", "ERROR", "CHAT_NOT_FOUND")
        else {"status": "SKIPPED_NOT_NEEDED", "sent": 0}
    )
    # شناسه‌های برگشتی تلگرام باید پیش از انتشار snapshot در signals.json ثبت شوند.
    result = publish(payload)

    print(json.dumps({
        "pipeline_status": payload.get("pipeline_status", "DEGRADED"),
        "provider": payload.get("provider", "unknown"),
        "symbols_processed": payload["quality"]["symbols_processed"],
        "signals_added_to_history": result.get("signals_added_to_history", 0),
        "signals_total": result.get("signals_total", 0),
        "telegram": notification,
        "message_id_current": payload.get("message_id_current"),
        "message_id_audience": payload.get("message_id_audience"),
        "published_at": payload.get("published_at"),
        "email_fallback": email_notification,
        "manual_trade_only": True,
    }, ensure_ascii=False))

    # Data degradation is published as an explicit state; it is not a code failure.
    # This allows the dashboard to replace stale data with an honest degraded snapshot.


if __name__ == "__main__":
    main()
