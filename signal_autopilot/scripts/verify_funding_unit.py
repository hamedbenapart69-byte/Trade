"""Funding unit: CoinGecko snapshot; Bybit known 403; no unsupported conversion."""
from __future__ import annotations
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CG_URL = "https://api.coingecko.com/api/v3/derivatives"


def get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Trade-Funding-Unit-Verification/2.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return json.loads(response.read().decode("utf-8"))


def verify() -> dict[str, Any]:
    captured = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "captured_at_utc": captured, "symbol": "BTCUSDT",
        "bybit_status": "UNAVAILABLE_KNOWN_HTTP_403_FROM_GITHUB_ACTIONS",
        "coinmarketcap_status": "UNAVAILABLE_NO_SUPPORTED_PUBLIC_FUNDING_RATE_ENDPOINT_VERIFIED",
        "coingecko_status": "PENDING", "status": "NOT_VERIFIED",
        "funding_usage": "NOT_USED_BECAUSE_UNVERIFIED",
        "conversion": None,
    }
    try:
        rows = get_json(CG_URL)
        matches = [x for x in rows if str(x.get("symbol", "")).upper().replace("/", "").replace("-", "") == "BTCUSDT"
                   and x.get("funding_rate") is not None] if isinstance(rows, list) else []
        if matches:
            matches.sort(key=lambda x: float(x.get("last_traded_at") or 0), reverse=True)
            chosen = matches[0]
            result.update({
                "coingecko_status": "AVAILABLE",
                "coingecko_market": chosen.get("market"),
                "coingecko_pair": chosen.get("symbol"),
                "coingecko_funding_rate_raw": float(chosen["funding_rate"]),
                "coingecko_last_traded_at": chosen.get("last_traded_at"),
                "reason": "SINGLE_SOURCE_CANNOT_VERIFY_SCALE; CoinMarketCap comparison not available",
            })
        else:
            result.update({"coingecko_status": "NO_MATCHING_BTCUSDT_FUNDING_ROW",
                           "reason": "NO_INDEPENDENT_COMPARISON_SOURCE"})
    except Exception as exc:
        result.update({"coingecko_status": f"UNAVAILABLE_{type(exc).__name__}",
                       "reason": str(exc)})
    return result


if __name__ == "__main__":
    report = verify()
    Path("data").mkdir(exist_ok=True)
    Path("data/funding_unit_verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0)
