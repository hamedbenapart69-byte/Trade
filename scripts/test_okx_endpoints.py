#!/usr/bin/env python3
"""آزمون فقط‌خواندنی ۳ Endpoint عمومی OKX روی ۵ نماد؛ بدون کلید API."""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://www.okx.com"
SYMBOLS = ("BTC", "ETH", "SOL", "RSR", "TAO")
TIMEOUT_SECONDS = 20
RETRIES = 2
PAUSE_SECONDS = 0.20
OUTPUT = Path("artifacts/okx_endpoints_test.json")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: Any) -> str | None:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return None
    return str(raw) if raw > 0 else None


def _get_json(path: str, params: dict[str, str]) -> tuple[int | None, dict[str, Any] | None, str | None]:
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Trade-OKX-Endpoint-Check/1.0"})
    last_error: str | None = None
    for attempt in range(RETRIES + 1):
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status = int(response.status)
                body = response.read().decode("utf-8")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                return status, None, f"invalid_json:{exc}"
            if not isinstance(payload, dict):
                return status, None, "response_root_not_object"
            return status, payload, None
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            return int(exc.code), None, f"http_error:{body}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = f"{type(exc).__name__}:{str(exc)[:300]}"
            if attempt < RETRIES:
                time.sleep(0.8 * (attempt + 1))
    return None, None, last_error or "request_failed"


def _validate_rows(endpoint: str, rows: Any) -> tuple[bool, dict[str, Any], str | None]:
    if not isinstance(rows, list) or not rows:
        return False, {"data_empty": True, "record_count": 0}, "empty_or_non_list_data"

    timestamps: list[str] = []
    values: list[Any] = []
    for row in rows:
        if endpoint == "funding":
            if not isinstance(row, dict):
                return False, {"data_empty": False, "record_count": len(rows)}, "funding_row_not_object"
            ts = _timestamp(row.get("fundingTime"))
            val = _number(row.get("fundingRate"))
            if ts is None or val is None:
                return False, {"data_empty": False, "record_count": len(rows)}, "funding_row_missing_valid_fundingTime_or_fundingRate"
            timestamps.append(ts)
            values.append({"fundingRate": str(row.get("fundingRate")), "fundingTime": ts})
        elif endpoint == "open_interest":
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                return False, {"data_empty": False, "record_count": len(rows)}, "oi_row_must_be_[timestamp,oi,volume]"
            ts = _timestamp(row[0])
            oi, volume = _number(row[1]), _number(row[2])
            if ts is None or oi is None or volume is None or oi <= 0 or volume < 0:
                return False, {"data_empty": False, "record_count": len(rows)}, "oi_row_has_invalid_timestamp_or_numeric_values"
            timestamps.append(ts)
            values.append({"oi": str(row[1]), "volume": str(row[2])})
        else:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                return False, {"data_empty": False, "record_count": len(rows)}, "long_short_row_must_be_[timestamp,ratio]"
            ts = _timestamp(row[0])
            ratio = _number(row[1])
            if ts is None or ratio is None or ratio <= 0:
                return False, {"data_empty": False, "record_count": len(rows)}, "long_short_row_has_invalid_timestamp_or_ratio"
            timestamps.append(ts)
            values.append({"ratio": str(row[1])})

    detail = {
        "data_empty": False,
        "record_count": len(rows),
        "first_timestamp": timestamps[0],
        "last_timestamp": timestamps[-1],
        "oldest_timestamp": min(timestamps, key=int),
        "newest_timestamp": max(timestamps, key=int),
        "first_value": values[0],
        "last_value": values[-1],
    }
    return True, detail, None


def test_one(symbol: str, endpoint: str) -> dict[str, Any]:
    if endpoint == "funding":
        path = "/api/v5/public/funding-rate"
        params = {"instId": f"{symbol}-USDT-SWAP"}
    elif endpoint == "open_interest":
        path = "/api/v5/rubik/stat/contracts/open-interest-volume"
        params = {"ccy": symbol, "period": "1H", "limit": "30"}
    else:
        path = "/api/v5/rubik/stat/contracts/long-short-account-ratio"
        params = {"ccy": symbol, "period": "1H", "limit": "30"}

    status, payload, error = _get_json(path, params)
    result: dict[str, Any] = {
        "symbol": symbol, "endpoint": endpoint, "path": path, "params": params,
        "http_status": status, "okx_code": None, "okx_message": None,
        "status": "NETWORK_ERROR", "data_empty": None, "record_count": 0,
    }
    if status is not None and status != 200:
        result["status"] = "HTTP_ERROR"
        result["error"] = error or f"unexpected_http_status:{status}"
        return result
    if error:
        result["status"] = "INVALID_JSON" if status == 200 and error.startswith("invalid_json") else "NETWORK_ERROR"
        result["error"] = error
        return result
    if payload is None:
        result["status"] = "INVALID_JSON"
        result["error"] = "empty_or_invalid_json_payload"
        return result

    result["okx_code"] = str(payload.get("code", "MISSING"))
    result["okx_message"] = str(payload.get("msg", ""))
    if result["okx_code"] != "0":
        result["status"] = "API_ERROR"
        result["error"] = "okx_code_not_zero"
        result["raw_data_count"] = len(payload.get("data") or []) if isinstance(payload.get("data"), list) else None
        return result

    valid, detail, validation_error = _validate_rows(endpoint, payload.get("data"))
    result.update(detail)
    if valid:
        result["status"] = "SUCCESS"
    else:
        result["status"] = "EMPTY" if validation_error == "empty_or_non_list_data" else "INVALID_SCHEMA"
        result["error"] = validation_error
    return result


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for endpoint in ("funding", "open_interest", "long_short_ratio"):
            results.append(test_one(symbol, endpoint))
            time.sleep(PAUSE_SECONDS)

    success_count = sum(item["status"] == "SUCCESS" for item in results)
    classification = "ALL_PASS" if success_count >= 13 else "PARTIAL_PASS" if success_count >= 8 else "MOSTLY_FAIL"
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "symbols": list(SYMBOLS),
        "endpoint_count": 3,
        "combination_count": len(results),
        "success_count": success_count,
        "failure_count": len(results) - success_count,
        "classification": classification,
        "gate_rules": {
            "ALL_PASS": "success_count >= 13",
            "PARTIAL_PASS": "8 <= success_count <= 12",
            "MOSTLY_FAIL": "success_count < 8; stop before LFS_v2 implementation",
        },
        "results": results,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = (
        "## OKX endpoint phase 0\n\n"
        f"- Classification: **{classification}**\n"
        f"- Successful combinations: **{success_count}/15**\n"
        f"- Failed combinations: **{len(results) - success_count}/15**\n"
        "- Artifact: artifacts/okx_endpoints_test.json\n"
    )
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(summary)
    print(summary)
    for item in results:
        print(
            f"{item['symbol']} | {item['endpoint']} | HTTP={item['http_status']} "
            f"| OKX={item['okx_code']} | records={item['record_count']} "
            f"| {item['status']} {item.get('error', '')}"
        )
    # MOSTLY_FAIL is a completed diagnostic result, not a script crash.
    # The next phase is gated by the JSON classification, not this exit code.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
