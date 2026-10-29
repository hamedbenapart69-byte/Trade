"""Small explicit execution schemas. Unknown workflows are never queueable until registered."""
from __future__ import annotations
import re
from typing import Any

MARKET_COINS = {"bitcoin", "ethereum", "solana", "ripple", "dogecoin", "binancecoin", "tether"}

def validate_workflow_input(workflow: str, payload: dict[str, Any]) -> str | None:
    if workflow in {"sample.review", "test.echo"}:
        return None
    if workflow == "market.snapshot":
        if set(payload) - {"coin_id", "currency"}:
            return "unknown_fields:" + ",".join(sorted(set(payload) - {"coin_id", "currency"}))
        if payload.get("coin_id") not in MARKET_COINS:
            return "coin_id_not_allowlisted"
        if payload.get("currency", "usd") not in {"usd", "eur"}:
            return "currency_must_be_usd_or_eur"
        return None
    if workflow == "research.scan":
        allowed = {"symbol", "market", "timeframe", "venue", "context"}
        unknown = set(payload) - allowed
        if unknown:
            return "unknown_fields:" + ",".join(sorted(unknown))
        symbol = payload.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9._-]{2,30}", symbol):
            return "symbol_must_be_2_to_30_safe_characters"
        if payload.get("market") not in {"spot", "futures"}:
            return "market_must_be_spot_or_futures"
        if payload.get("timeframe") not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
            return "unsupported_timeframe"
        if "venue" in payload and (not isinstance(payload["venue"], str) or len(payload["venue"]) > 100):
            return "venue_must_be_a_string_up_to_100_chars"
        if "context" in payload and (not isinstance(payload["context"], str) or len(payload["context"]) > 3000):
            return "context_must_be_a_string_up_to_3000_chars"
        return None
    return "workflow_schema_not_registered"
