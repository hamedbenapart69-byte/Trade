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
OUTPUT = Path("diagnostics/okx_api_test_result.json")


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
            if str(payload.get("code", "")) == "50011" and attempt < RETRIES:
                last_error = "okx_rate_limit_50011"
                time.sleep(1.5 * (attempt + 1))
                continue
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



def classify_endpoint_count(success_count: int) -> str:
    """طبقه‌بندی دقیق ۱۵ ترکیب Endpoint طبق Gate فاز صفر."""
    if success_count == 15:
        return "ALL_PASS"
    if 13 <= success_count <= 14:
        return "HIGH_PASS"
    if 8 <= success_count <= 12:
        return "PARTIAL_PASS"
    return "MOSTLY_FAIL"


def classify_oi_coverage(record_count: int, coverage_hours: int,
                          target_hours: int = 2160) -> str:
    """FULL=۹۰ روز، PARTIAL=حداقل ۳۰ روز، در غیر این صورت INSUFFICIENT."""
    if record_count >= target_hours and coverage_hours >= target_hours:
        return "FULL"
    partial_hours = 30 * 24
    if record_count >= partial_hours and coverage_hours >= partial_hours:
        return "PARTIAL"
    return "INSUFFICIENT"


def test_oi_hourly_history(
    symbol: str,
    target_hours: int = 2160,
    limit: int = 100,
    max_requests: int = 25,
) -> dict[str, Any]:
    """دریافت تاریخچهٔ OI ساعتی Rubik با صفحه‌بندی محدود و حذف رکورد تکراری."""
    path = "/api/v5/rubik/stat/contracts/open-interest-volume"
    records: dict[int, list[Any]] = {}
    request_count = 0
    last_http_status: int | None = None
    last_okx_code: str | None = None
    last_error: str | None = None
    before: str | None = None
    initial_params = {"ccy": symbol, "period": "1H", "limit": str(limit)}

    while request_count < max_requests:
        params = dict(initial_params)
        if before is not None:
            params["before"] = before
        previous_count = len(records)
        request_count += 1
        http_status, payload, error = _get_json(path, params)
        last_http_status = http_status
        if error:
            last_error = error
            break
        if http_status != 200 or not isinstance(payload, dict):
            last_error = f"unexpected_http_or_payload:{http_status}"
            break
        last_okx_code = str(payload.get("code", "MISSING"))
        if last_okx_code != "0":
            last_error = f"okx_code_not_zero:{last_okx_code}:{str(payload.get('msg', ''))[:160]}"
            break

        page = payload.get("data")
        if not isinstance(page, list) or not page:
            break
        for row in page:
            valid, _, _ = _validate_rows("open_interest", [row])
            if valid:
                records[int(row[0])] = list(row)

        # قرارداد Rubik: ادامهٔ صفحه‌بندی با timestamp آخرین رکورد همین صفحه.
        next_before = str(page[-1][0]) if isinstance(page[-1], (list, tuple)) and page[-1] else None
        if not records:
            break
        timestamps = sorted(records)
        coverage_hours = int((timestamps[-1] - timestamps[0]) / 3_600_000) + 1
        if len(records) >= target_hours and coverage_hours >= target_hours:
            break
        if len(page) < limit or len(records) == previous_count:
            break
        if next_before is None or next_before == before:
            last_error = "pagination_cursor_stalled"
            break
        before = next_before
        time.sleep(PAUSE_SECONDS)

    timestamps = sorted(records)
    record_count = len(timestamps)
    coverage_hours = (
        int((timestamps[-1] - timestamps[0]) / 3_600_000) + 1
        if record_count >= 2 else record_count
    )
    coverage_days = round(coverage_hours / 24.0, 2)
    coverage_status = classify_oi_coverage(record_count, coverage_hours, target_hours)
    result: dict[str, Any] = {
        "symbol": symbol,
        "endpoint": "open_interest_volume_1H_90d",
        "path": path,
        "params": initial_params,
        "http_status": last_http_status,
        "okx_code": last_okx_code,
        "status": coverage_status,
        "coverage_status": coverage_status,
        "target_hours": target_hours,
        "limit_per_request": limit,
        "max_requests": max_requests,
        "requests_made": request_count,
        "record_count": record_count,
        "coverage_hours": coverage_hours,
        "coverage_days": coverage_days,
        "oldest_timestamp": str(timestamps[0]) if timestamps else None,
        "newest_timestamp": str(timestamps[-1]) if timestamps else None,
        "last_before_cursor": before,
    }
    if last_error:
        result["error"] = last_error
    return result


def test_oi_daily_history(symbol: str) -> dict[str, Any]:
    """تست تکمیلی: آیا Rubik می‌دهد تاریخچهٔ روزانهٔ کافی برای رتبهٔ OI نودروزه؟"""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    begin_ms = now_ms - 100 * 24 * 60 * 60 * 1000
    path = "/api/v5/rubik/stat/contracts/open-interest-volume"
    params = {
        "ccy": symbol,
        "period": "1D",
        "begin": str(begin_ms),
        "end": str(now_ms),
    }
    status, payload, error = _get_json(path, params)
    result: dict[str, Any] = {
        "symbol": symbol,
        "endpoint": "open_interest_volume_1D_100d_supplemental",
        "path": path,
        "params": params,
        "http_status": status,
        "okx_code": None,
        "status": "NETWORK_ERROR",
        "record_count": 0,
    }
    if status is not None and status != 200:
        result["status"] = "HTTP_ERROR"
        result["error"] = error or f"unexpected_http_status:{status}"
        return result
    if error:
        result["status"] = "INVALID_JSON" if status == 200 and error.startswith("invalid_json") else "NETWORK_ERROR"
        result["error"] = error
        return result
    if not isinstance(payload, dict):
        result["status"] = "INVALID_JSON"
        return result
    result["okx_code"] = str(payload.get("code", "MISSING"))
    result["okx_message"] = str(payload.get("msg", ""))
    if result["okx_code"] != "0":
        result["status"] = "API_ERROR"
        result["error"] = "okx_code_not_zero"
        return result

    rows = payload.get("data")
    valid, detail, validation_error = _validate_rows("open_interest", rows)
    result.update(detail)
    if not valid:
        result["status"] = "EMPTY" if validation_error == "empty_or_non_list_data" else "INVALID_SCHEMA"
        result["error"] = validation_error
        return result

    oldest = int(result["oldest_timestamp"])
    newest = int(result["newest_timestamp"])
    span_days = (newest - oldest) / (24 * 60 * 60 * 1000)
    result["history_span_days"] = round(span_days, 2)
    result["coverage_days"] = round(span_days, 2)
    # برای رتبهٔ روزانه، حداقل ۳۰ مشاهدهٔ روزانه لازم است؛ FULL یعنی ۹۰ روز کامل.
    if result["record_count"] >= 91 and span_days >= 89:
        result["coverage_status"] = "FULL"
        result["status"] = "SUCCESS_90D_HISTORY"
    elif result["record_count"] >= 30 and span_days >= 29:
        result["coverage_status"] = "PARTIAL"
        result["status"] = "PARTIAL_HISTORY"
    else:
        result["coverage_status"] = "INSUFFICIENT"
        result["status"] = "INSUFFICIENT_HISTORY"
    return result


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        for endpoint in ("funding", "open_interest", "long_short_ratio"):
            results.append(test_one(symbol, endpoint))
            time.sleep(PAUSE_SECONDS)

    success_count = sum(item["status"] == "SUCCESS" for item in results)
    classification = classify_endpoint_count(success_count)
    supplemental_oi_1h = []
    supplemental_oi_1d = []
    for symbol in SYMBOLS:
        supplemental_oi_1h.append(test_oi_hourly_history(symbol))
        time.sleep(0.5)
        supplemental_oi_1d.append(test_oi_daily_history(symbol))
        time.sleep(0.5)
    supplemental_oi_1h_ready = all(item["coverage_status"] == "FULL" for item in supplemental_oi_1h)
    supplemental_oi_1d_ready = all(item.get("coverage_status") == "FULL" for item in supplemental_oi_1d)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "symbols": list(SYMBOLS),
        "endpoint_count": 3,
        "combination_count": len(results),
        "success_count": success_count,
        "failure_count": len(results) - success_count,
        "classification": classification,
        "supplemental_checks": {
            "oi_1h_90d_history": supplemental_oi_1h,
            "all_symbols_have_90d_hourly_oi": supplemental_oi_1h_ready,
            "oi_1d_100d_history": supplemental_oi_1d,
            "all_symbols_have_90d_daily_oi": supplemental_oi_1d_ready,
            "note": "Supplemental OI history checks; not included in the 15-combination endpoint gate count.",
        },
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
        f"- 90-day hourly OI FULL: **{sum(item['coverage_status'] == 'FULL' for item in supplemental_oi_1h)}/5 symbols**\n"
        f"- 90-day daily OI FULL: **{sum(item.get('coverage_status') == 'FULL' for item in supplemental_oi_1d)}/5 symbols**\n"
        "- Artifact: diagnostics/okx_api_test_result.json\n"
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
    for item in supplemental_oi_1h:
        print(
            f"{item['symbol']} | oi_1h_90d | records={item['record_count']} "
            f"| coverage_days={item['coverage_days']} | {item['coverage_status']} {item.get('error', '')}"
        )
    for item in supplemental_oi_1d:
        print(
            f"{item['symbol']} | oi_1d_100d_supplemental | records={item['record_count']} "
            f"| coverage_days={item.get('coverage_days')} | {item.get('coverage_status')} {item.get('error', '')}"
        )
    # MOSTLY_FAIL یک Gate واقعی است: خروجی تشخیصی حفظ می‌شود اما workflow fail می‌شود.
    return 1 if success_count < 8 else 0


if __name__ == "__main__":
    raise SystemExit(main())
