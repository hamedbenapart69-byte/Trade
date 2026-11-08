"""اعتبارسنجی واحد funding در CoinGecko با قرارداد هم‌نام Bybit."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CG_URL = "https://api.coingecko.com/api/v3/derivatives"
BYBIT_URL = "https://api.bybit.com/v5/market/tickers"


def get_json(url: str, params: dict[str, str] | None = None) -> Any:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "Trade-Funding-Unit-Verification/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP_{response.status}")
        return json.loads(response.read().decode("utf-8"))


def relative_error(candidate: float, reference: float) -> float:
    return abs(candidate - reference) / max(abs(reference), 1e-12)


def classify_unit(cg_rate: float, bybit_rate: float) -> dict[str, Any]:
    """مقایسه raw و raw/100؛ هیچ تبدیل حدسی انجام نمی‌شود."""
    if not math.isfinite(cg_rate) or not math.isfinite(bybit_rate):
        return {"status": "UNVERIFIED", "reason": "NON_FINITE_RATE"}
    if abs(bybit_rate) < 1e-8 or abs(cg_rate) < 1e-8:
        return {"status": "UNVERIFIED", "reason": "RATE_TOO_CLOSE_TO_ZERO"}
    raw_error = relative_error(cg_rate, bybit_rate)
    percent_error = relative_error(cg_rate / 100.0, bybit_rate)
    best = min(raw_error, percent_error)
    other = max(raw_error, percent_error)
    if best > 0.25 or other < best * 5:
        return {
            "status": "UNVERIFIED", "reason": "NO_CLEAR_SCALE_MATCH",
            "raw_relative_error": raw_error, "divide_100_relative_error": percent_error,
        }
    unit = "DECIMAL" if raw_error < percent_error else "PERCENT"
    return {
        "status": "VERIFIED", "unit": unit,
        "conversion": "raw" if unit == "DECIMAL" else "raw/100",
        "raw_relative_error": raw_error, "divide_100_relative_error": percent_error,
    }


def verify() -> dict[str, Any]:
    captured_at = datetime.now(timezone.utc).isoformat()
    bybit = get_json(BYBIT_URL, {"category": "linear", "symbol": "BTCUSDT"})
    if bybit.get("retCode") != 0:
        raise RuntimeError(f"BYBIT_ERROR_{bybit.get('retCode')}")
    bybit_rows = (bybit.get("result") or {}).get("list") or []
    if not bybit_rows:
        raise RuntimeError("BYBIT_BTCUSDT_TICKER_MISSING")
    bybit_rate = float(bybit_rows[0]["fundingRate"])

    cg = get_json(CG_URL)
    matches = [
        row for row in cg if str(row.get("symbol", "")).upper().replace("/", "").replace("-", "") == "BTCUSDT"
        and "bybit" in str(row.get("market", "")).lower()
        and row.get("funding_rate") is not None
    ] if isinstance(cg, list) else []
    if not matches:
        return {
            "captured_at_utc": captured_at, "symbol": "BTCUSDT",
            "status": "UNVERIFIED", "reason": "COINGECKO_BYBIT_BTCUSDT_ROW_NOT_FOUND",
            "bybit_rate": bybit_rate, "funding_usage": "NOT_USED_BECAUSE_UNVERIFIED",
        }
    # در صورت وجود چند ردیف، تازه‌ترین last_traded_at انتخاب می‌شود.
    matches.sort(key=lambda row: float(row.get("last_traded_at") or 0), reverse=True)
    selected = matches[0]
    cg_rate = float(selected["funding_rate"])
    comparison = classify_unit(cg_rate, bybit_rate)
    return {
        "captured_at_utc": captured_at, "symbol": "BTCUSDT",
        "coingecko_market": selected.get("market"),
        "coingecko_pair": selected.get("symbol"),
        "coingecko_last_traded_at": selected.get("last_traded_at"),
        "coingecko_funding_rate_raw": cg_rate,
        "bybit_funding_rate": bybit_rate,
        **comparison,
        "funding_usage": "NOT_USED_BECAUSE_UNVERIFIED" if comparison["status"] != "VERIFIED" else "VERIFIED_UNIT_ONLY_NOT_YET_ENABLED",
        "note": "مقایسه snapshot دو API مستقل روی قرارداد BTCUSDT؛ این تست واحد را می‌سنجد، نه برابری کامل نرخ دو بازار.",
    }


if __name__ == "__main__":
    result = verify()
    Path("data").mkdir(exist_ok=True)
    Path("data/funding_unit_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "VERIFIED" else 3)
