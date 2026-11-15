"""انتشار گزارش واقعی Stage 1B در قالب مصرفی داشبورد عمومی."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EXPECTED_UNIVERSE_SIZE = 27
MAX_REPORT_AGE = timedelta(hours=4)
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_REPORT_BYTES = 5_000_000
MAX_HISTORY_ROWS = 80_000
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,30}$")
HISTORY_FIELDS = (
    "generated_at_utc", "symbol", "decision", "htf_4h_kumo",
    "htf_1h_kijun", "confidence", "lfs_score", "lfs_status",
    "mode", "veto", "reason",
)


def _parse_utc(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label}_MISSING")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _load_universe(path: Path) -> set[str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
        raise ValueError("UNIVERSE_FILE_INVALID")
    payload = json.loads(path.read_text(encoding="utf-8"))
    symbols = payload.get("symbols") if isinstance(payload, dict) else None
    if not isinstance(symbols, list) or len(symbols) != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("UNIVERSE_DEFINITION_INVALID")
    if any(not isinstance(item, str) or not SYMBOL_RE.fullmatch(item) for item in symbols):
        raise ValueError("UNIVERSE_SYMBOL_INVALID")
    result = set(symbols)
    if len(result) != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("UNIVERSE_SYMBOL_DUPLICATE")
    return result


def _load_report(path: Path, expected: set[str], now: datetime) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError("REPORT_FILE_INVALID")
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("REPORT_ROOT_INVALID")
    if report.get("stage") != "STAGE_1_UNCALIBRATED":
        raise ValueError("REPORT_STAGE_INVALID")
    if report.get("decision_policy") != "WATCHLIST_ONLY_NO_BUY_NOW_NO_SELL_NOW":
        raise ValueError("REPORT_DECISION_POLICY_INVALID")
    if report.get("calibration") != "UNCALIBRATED":
        raise ValueError("REPORT_CALIBRATION_INVALID")
    if report.get("universe_count") != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("REPORT_UNIVERSE_COUNT_INVALID")
    if report.get("symbols_reported") != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("REPORT_SYMBOL_COUNT_INVALID")
    rows = report.get("symbols")
    if not isinstance(rows, list) or len(rows) != EXPECTED_UNIVERSE_SIZE:
        raise ValueError("REPORT_SYMBOL_ROWS_INVALID")

    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("REPORT_SYMBOL_ROW_INVALID")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or symbol in seen:
            raise ValueError("REPORT_SYMBOL_ID_INVALID")
        seen.add(symbol)
    if seen != expected:
        raise ValueError("REPORT_UNIVERSE_SET_MISMATCH")

    generated = _parse_utc(report.get("generated_at_utc"), "REPORT_TIMESTAMP")
    age = now.astimezone(timezone.utc) - generated
    if age > MAX_REPORT_AGE:
        raise ValueError("REPORT_STALE")
    if age < -MAX_FUTURE_SKEW:
        raise ValueError("REPORT_TIMESTAMP_TOO_FAR_IN_FUTURE")
    return report


def _decision(row: dict[str, Any]) -> str:
    mode = str(row.get("mode") or "")
    decision = str(row.get("decision") or "")
    veto = str(row.get("veto") or "")
    reason = str(row.get("reason") or "")
    if mode == "PRODUCTION" and decision == "WATCHLIST" and veto == "PASS":
        return "WATCHLIST"
    if veto.startswith("DATA_") or reason.startswith("UNAVAILABLE:"):
        return "MARKET_DATA_DEGRADED"
    return "NO_QUALIFIED_SETUP"


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None


def _validate_watchlist_levels(row: dict[str, Any]) -> None:
    if _decision(row) != "WATCHLIST":
        return
    direction = row.get("direction")
    if direction not in {"BUY", "SELL"}:
        raise ValueError("REPORT_WATCHLIST_DIRECTION_INVALID")
    entry = _finite_number(row.get("entry"))
    stop = _finite_number(row.get("stop_loss"))
    target = _finite_number(row.get("take_profit"))
    rr = _finite_number(row.get("rr"))
    if entry is None or stop is None or target is None or rr is None or min(entry, stop, target) <= 0 or rr <= 0:
        raise ValueError("REPORT_WATCHLIST_LEVELS_INVALID")
    risk, reward = (
        (entry - stop, target - entry)
        if direction == "BUY"
        else (stop - entry, entry - target)
    )
    if risk <= 0 or reward <= 0:
        raise ValueError("REPORT_WATCHLIST_LEVEL_DIRECTION_INVALID")
    if abs(rr - reward / risk) > max(0.05, abs(rr) * 0.10):
        raise ValueError("REPORT_WATCHLIST_RR_MISMATCH")


def build_dashboard_report(source: dict[str, Any]) -> dict[str, Any]:
    source_rows = source["symbols"]
    declared_candidates = source.get("production_watchlist_count")
    computed_candidates = sum(
        _decision(row) == "WATCHLIST" for row in source_rows
    )
    if isinstance(declared_candidates, bool) or declared_candidates != computed_candidates:
        raise ValueError("REPORT_WATCHLIST_COUNT_MISMATCH")
    for row in source_rows:
        _validate_watchlist_levels(row)
    rows: list[dict[str, Any]] = []
    data_sources: set[str] = set()
    cvd_sources: set[str] = set()
    for source_row in source_rows:
        bias = source_row.get("higher_timeframe_bias")
        bias = bias if isinstance(bias, dict) else {}
        cvd = source_row.get("cvd")
        cvd = cvd if isinstance(cvd, dict) else {}
        sources = source_row.get("data_sources")
        if isinstance(sources, list):
            data_sources.update(str(item) for item in sources if item)
        cvd_source = str(cvd.get("source") or "UNAVAILABLE")
        if cvd_source:
            cvd_sources.add(cvd_source)
        decision = _decision(source_row)
        rows.append({
            "symbol": source_row["symbol"],
            "timeframe": "15m",
            "decision": decision,
            "tier": source_row.get("tier") if decision == "WATCHLIST" else None,
            "mode": source_row.get("mode") or "UNAVAILABLE",
            "direction": source_row.get("direction"),
            "veto": source_row.get("veto") or "UNAVAILABLE",
            "reason": source_row.get("reason") or "UNAVAILABLE",
            "higher_timeframe_bias": {
                "4h_kumo": bias.get("4h_kumo", "UNAVAILABLE"),
                "1h_kijun": bias.get("1h_kijun", "UNAVAILABLE"),
            },
            "cvd_source": cvd_source,
            "rows_available": source_row.get("rows_available"),
            "stats_1h_rows_available": source_row.get("stats_1h_rows_available"),
            "confidence": "NOT_CALIBRATED",
            "lfs_score": source_row.get("lfs_score"),
            "lfs_status": source_row.get("lfs_status") or "UNAVAILABLE",
            "lfs_coverage_pct": source_row.get("lfs_coverage_pct"),
            "entry": source_row.get("entry"),
            "stop_loss": source_row.get("stop_loss"),
            "take_profit_1": source_row.get("take_profit_1"),
            "take_profit": source_row.get("take_profit"),
            "rr": source_row.get("rr"),
            "hypothesis": source_row.get("hypothesis"),
            "falsification": source_row.get("falsification"),
            "data_sources": sources if isinstance(sources, list) else [],
            "last_closed_candle_utc": source_row.get("last_closed_candle_utc"),
            "research_candidate": source_row.get("mode") == "RESEARCH",
        })

    return {
        "generated_at_utc": source["generated_at_utc"],
        "stage": source["stage"],
        "engine": "LRT-15m",
        "universe_count": EXPECTED_UNIVERSE_SIZE,
        "symbols_analyzed": len(rows),
        "candidate_setups": sum(row["decision"] == "WATCHLIST" for row in rows),
        "calibration_status": "UNCALIBRATED",
        "ev_status": "NOT_CALCULATED",
        "data_gate_status": "NOT_REPORTED",
        "decision_policy": source["decision_policy"],
        "data_sources": sorted(data_sources),
        "cvd_sources": sorted(cvd_sources),
        "signals": rows,
        "production_watchlist_count": source.get("production_watchlist_count", 0),
        "research_candidate_count": source.get("research_candidate_count", 0),
        "report_source": "stage1_lrt_report.json",
    }


def _load_history(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError("HISTORY_FILE_INVALID")
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != HISTORY_FIELDS:
            raise ValueError("HISTORY_SCHEMA_MISMATCH")
        return list(reader)


def _history_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    rows = []
    for item in report["signals"]:
        bias = item["higher_timeframe_bias"]
        rows.append({
            "generated_at_utc": report["generated_at_utc"],
            "symbol": item["symbol"],
            "decision": item["decision"],
            "htf_4h_kumo": str(bias.get("4h_kumo") or "UNAVAILABLE"),
            "htf_1h_kijun": str(bias.get("1h_kijun") or "UNAVAILABLE"),
            "confidence": "NOT_CALIBRATED",
            "lfs_score": "" if item.get("lfs_score") is None else str(item["lfs_score"]),
            "lfs_status": str(item.get("lfs_status") or "UNAVAILABLE"),
            "mode": str(item.get("mode") or "UNAVAILABLE"),
            "veto": str(item.get("veto") or "UNAVAILABLE"),
            "reason": str(item.get("reason") or "UNAVAILABLE").replace(",", ";").replace("\r", " ").replace("\n", " "),
        })
    return rows


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".lrt15m-report-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _atomic_write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".lrt15m-history-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def publish_dashboard(
    report_path: str | Path,
    universe_path: str | Path,
    output_dir: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("VALIDATION_CLOCK_NOT_TIMEZONE_AWARE")
    output = Path(output_dir)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("OUTPUT_DIRECTORY_INVALID")
    expected = _load_universe(Path(universe_path))
    source = _load_report(Path(report_path), expected, current_time)
    dashboard = build_dashboard_report(source)
    report_target = output / "lrt15m_signals.json"
    history_target = output / "lrt15m_history.csv"
    if report_target.is_symlink() or history_target.is_symlink():
        raise ValueError("DASHBOARD_OUTPUT_SYMLINK_REJECTED")

    if report_target.exists():
        existing = json.loads(report_target.read_text(encoding="utf-8"))
        existing_time = _parse_utc(existing.get("generated_at_utc"), "EXISTING_REPORT_TIMESTAMP")
        incoming_time = _parse_utc(dashboard.get("generated_at_utc"), "INCOMING_REPORT_TIMESTAMP")
        if existing_time > incoming_time:
            raise ValueError("OLDER_REPORT_CANNOT_REPLACE_NEWER_DASHBOARD")

    old_rows = _load_history(history_target)
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for row in old_rows + _history_rows(dashboard):
        key = (row["generated_at_utc"], row["symbol"])
        merged[key] = {field: row.get(field, "") for field in HISTORY_FIELDS}
    history = sorted(
        merged.values(),
        key=lambda row: (row["generated_at_utc"], row["symbol"]),
    )[-MAX_HISTORY_ROWS:]

    _atomic_write_json(report_target, dashboard)
    _atomic_write_csv(history_target, history)
    return {
        "status": "PUBLISHED",
        "report_path": str(report_target),
        "history_path": str(history_target),
        "symbols": len(dashboard["signals"]),
        "history_rows": len(history),
        "candidate_setups": dashboard["candidate_setups"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = publish_dashboard(args.report, args.universe, args.output_dir)
    print("STAGE1B_DASHBOARD_PUBLICATION " + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
