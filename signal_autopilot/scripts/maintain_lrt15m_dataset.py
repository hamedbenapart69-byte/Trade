"""مدیریت افزایشی تاریخچهٔ LRT-15m، دریافت tail زنده و کنترل تازگی داده."""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

INTERVAL_MS = 15 * 60 * 1000
WINDOW_MS = 730 * 24 * 60 * 60 * 1000
EXPECTED_ROWS = WINDOW_MS // INTERVAL_MS
MAX_TAIL_BARS_PER_RUN = 100
DEFAULT_MAX_AGE_MINUTES = 30


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _read_rows(path: Path) -> list[dict[str, Any]]:
    return pq.read_table(path).to_pylist()


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd", version="2.6")


def _legacy_end_date(path: Path) -> str:
    parts = path.stem.split("_")
    return parts[-1] if len(parts) >= 4 else ""


def _validate_baseline(path: Path) -> tuple[bool, int, int | None, int | None, str | None]:
    if not path.exists():
        return False, 0, None, None, "BASELINE_MISSING"
    rows = _read_rows(path)
    timestamps = sorted({int(row["open_time"]) for row in rows if row.get("open_time") is not None})
    if not timestamps:
        return False, 0, None, None, "BASELINE_EMPTY"
    gaps = sum(1 for left, right in zip(timestamps, timestamps[1:]) if right - left != INTERVAL_MS)
    complete = len(timestamps) == EXPECTED_ROWS and gaps == 0
    reason = None if complete else f"BASELINE_INCOMPLETE:rows={len(timestamps)}:gaps={gaps}"
    return complete, len(timestamps), timestamps[0], timestamps[-1], reason


def migrate_legacy_snapshots(storage_dir: Path, symbols: list[str]) -> dict[str, Any]:
    """آخرین snapshot تاریخ‌دار را یک‌بار به baseline پایدار منتقل می‌کند."""
    base_dir = storage_dir / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    migrated: list[str] = []
    removed: list[str] = []
    missing: list[str] = []
    validation: dict[str, Any] = {}

    for symbol in symbols:
        target = base_dir / f"{symbol}_15m.parquet"
        candidates = sorted(storage_dir.glob(f"{symbol}_15m_*.parquet"),
                            key=_legacy_end_date, reverse=True)
        valid, rows, first_ms, last_ms, reason = _validate_baseline(target)
        if not valid and candidates:
            # اگر baseline خراب بود، آخرین snapshot معتبر را جایگزین کن.
            candidate = candidates[0]
            temporary = base_dir / f".{symbol}_15m_candidate.parquet"
            shutil.copy2(candidate, temporary)
            candidate_valid, candidate_rows, candidate_first, candidate_last, candidate_reason = _validate_baseline(temporary)
            if candidate_valid:
                temporary.replace(target)
                migrated.append(symbol)
                valid, rows, first_ms, last_ms, reason = (
                    candidate_valid, candidate_rows, candidate_first, candidate_last, candidate_reason
                )
            else:
                temporary.unlink(missing_ok=True)

        validation[symbol] = {
            "valid": valid, "rows": rows, "first_open_ms": first_ms,
            "last_open_ms": last_ms, "reason": reason,
        }
        if not valid:
            missing.append(symbol)
            continue

        for candidate in candidates:
            candidate.unlink(missing_ok=True)
            removed.append(candidate.name)

    return {
        "base_dir": str(base_dir), "migrated_symbols": migrated,
        "removed_legacy_files": removed, "missing_symbols": missing,
        "validation": validation,
    }


def _load_downloader():
    scripts_dir = Path.cwd() / "signal_autopilot" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    return importlib.import_module("download_lrt15m_history")


def _fetch_symbol_tail(symbol: str, start_ms: int, end_ms: int, now_ms: int,
                       downloader: Any) -> tuple[dict[int, dict[str, Any]], dict[str, str]]:
    expected = set(range(start_ms, end_ms, INTERVAL_MS))
    if not expected:
        return {}, {"status": "NO_NEW_CLOSED_CANDLES"}

    if len(expected) > MAX_TAIL_BARS_PER_RUN:
        return {}, {"status": "BACKFILL_REQUIRED",
                    "reason": f"tail_bars={len(expected)} exceeds safe limit={MAX_TAIL_BARS_PER_RUN}"}

    collected: dict[int, dict[str, Any]] = {}
    statuses: dict[str, str] = {}

    try:
        okx_rows, okx_status = downloader.fetch_okx_history_15m(symbol, start_ms, end_ms)
        statuses["okx"] = okx_status
        for ts, row in okx_rows.items():
            ts = int(ts)
            if ts in expected and ts + INTERVAL_MS <= now_ms:
                collected[ts] = dict(row)
    except Exception as exc:
        statuses["okx"] = f"ERROR:{type(exc).__name__}:{exc}"

    missing = expected.difference(collected)
    if missing:
        try:
            mexc_rows, mexc_status = downloader.fetch_mexc_futures_15m(symbol, start_ms, end_ms)
            statuses["mexc"] = mexc_status
            for ts, row in mexc_rows.items():
                ts = int(ts)
                if ts in missing and ts + INTERVAL_MS <= now_ms:
                    collected[ts] = dict(row)
        except Exception as exc:
            statuses["mexc"] = f"ERROR:{type(exc).__name__}:{exc}"

    missing = expected.difference(collected)
    if missing and symbol == "1000PEPEUSDT":
        try:
            proxy_rows, proxy_status = downloader.fetch_okx_pepe_spot_as_1000pepe(
                symbol, start_ms, end_ms
            )
            statuses["okx_spot_proxy"] = proxy_status
            for ts, row in proxy_rows.items():
                ts = int(ts)
                if ts in missing and ts + INTERVAL_MS <= now_ms:
                    collected[ts] = dict(row)
        except Exception as exc:
            statuses["okx_spot_proxy"] = f"ERROR:{type(exc).__name__}:{exc}"

    statuses["expected_bars"] = str(len(expected))
    statuses["received_bars"] = str(len(collected))
    statuses["missing_bars"] = str(len(expected.difference(collected)))
    return collected, statuses


def _tail_partition_path(storage_dir: Path, symbol: str, end_ms: int) -> Path:
    last_open = end_ms - INTERVAL_MS
    bucket = datetime.fromtimestamp(last_open / 1000, timezone.utc)
    return (storage_dir / "live_tail" / bucket.strftime("%Y-%m-%d")
            / bucket.strftime("%H00") / f"{symbol}_15m.parquet")


def _merge_rows(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            if row.get("open_time") is None:
                continue
            merged[int(row["open_time"])] = dict(row)
    return [merged[key] for key in sorted(merged)]


def _compute_window(storage_dir: Path, compute_dir: Path, symbol: str,
                    window_start_ms: int, window_end_ms: int) -> dict[str, Any]:
    base_path = storage_dir / "base" / f"{symbol}_15m.parquet"
    base_rows = _read_rows(base_path) if base_path.exists() else []
    tail_paths = sorted((storage_dir / "live_tail").glob(f"**/{symbol}_15m.parquet"))
    tail_groups = [_read_rows(path) for path in tail_paths]
    all_rows = _merge_rows(base_rows, *tail_groups)
    rows = [row for row in all_rows
            if window_start_ms <= int(row["open_time"]) < window_end_ms]
    timestamps = [int(row["open_time"]) for row in rows]
    gaps = sum(1 for left, right in zip(timestamps, timestamps[1:])
               if right - left != INTERVAL_MS)
    expected = (window_end_ms - window_start_ms) // INTERVAL_MS
    continuity = len(timestamps) == expected and gaps == 0
    target = compute_dir / f"{symbol}_15m_730d.parquet"
    if rows:
        _write_rows(target, rows)
    return {
        "symbol": symbol, "baseline_rows": len(base_rows),
        "tail_rows": sum(len(group) for group in tail_groups),
        "rows": len(rows), "expected_rows": expected, "gap_count": gaps,
        "continuity": continuity, "first_open_ms": timestamps[0] if timestamps else None,
        "last_open_ms": timestamps[-1] if timestamps else None,
        "compute_file": str(target) if rows else None,
        "sources": sorted({str(row.get("data_source", "UNAVAILABLE")) for row in rows}),
        "cvd_sources": sorted({str(row.get("cvd_source", "UNAVAILABLE")) for row in rows}),
    }


def maintain_dataset(storage_dir: Path, compute_dir: Path, report_path: Path,
                     output_path: Path, universe_path: Path,
                     now_ms: int | None = None, max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
                     downloader: Any | None = None, engine: Any | None = None) -> dict[str, Any]:
    now_ms = utc_now_ms() if now_ms is None else int(now_ms)
    downloader = downloader or _load_downloader()
    if engine is None:
        sys.path.insert(0, str(Path.cwd() / "signal_autopilot"))
        engine = importlib.import_module("modules.lrt15m_engine")

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; got {len(symbols)}")

    migration = migrate_legacy_snapshots(storage_dir, symbols)
    base_missing = migration["missing_symbols"]
    if base_missing:
        # فقط در نبود baseline معتبر، backfill دوساله اجرا می‌شود.
        end_date = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date()
        start_date = end_date - timedelta(days=730)
        report_tmp = report_path.with_name("stage1b_backfill_report.json")
        import asyncio
        asyncio.run(downloader.run(start_date, end_date, storage_dir, report_tmp, universe_path))
        migration = migrate_legacy_snapshots(storage_dir, symbols)
        base_missing = migration["missing_symbols"]

    closed_end_ms = (now_ms // INTERVAL_MS) * INTERVAL_MS
    window_start_ms = closed_end_ms - WINDOW_MS
    tail_status: dict[str, dict[str, str]] = {}
    new_rows_by_symbol: dict[str, int] = {}

    def collect_one(symbol: str):
        base_path = storage_dir / "base" / f"{symbol}_15m.parquet"
        if not base_path.exists():
            return symbol, {}, {"status": "BASELINE_MISSING"}
        base_rows = _read_rows(base_path)
        tail_paths = sorted((storage_dir / "live_tail").glob(f"**/{symbol}_15m.parquet"))
        tail_rows = _merge_rows(*[_read_rows(path) for path in tail_paths]) if tail_paths else []
        existing = _merge_rows(base_rows, tail_rows)
        latest = int(existing[-1]["open_time"]) if existing else None
        start_ms = (latest + INTERVAL_MS) if latest is not None else window_start_ms
        bars, statuses = _fetch_symbol_tail(symbol, start_ms, closed_end_ms, now_ms, downloader)
        if bars:
            partition = _tail_partition_path(storage_dir, symbol, closed_end_ms)
            prior = _read_rows(partition) if partition.exists() else []
            _write_rows(partition, _merge_rows(prior, [
                {"open_time": ts, **row} for ts, row in bars.items()
            ]))
        return symbol, bars, statuses

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(collect_one, symbol) for symbol in symbols]
        for future in as_completed(futures):
            symbol, bars, statuses = future.result()
            tail_status[symbol] = statuses
            new_rows_by_symbol[symbol] = len(bars)

    if compute_dir.exists():
        shutil.rmtree(compute_dir)
    compute_dir.mkdir(parents=True, exist_ok=True)
    compute_results = {
        symbol: _compute_window(storage_dir, compute_dir, symbol,
                                window_start_ms, closed_end_ms)
        for symbol in symbols
    }

    freshness: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        item = compute_results[symbol]
        last_open = item["last_open_ms"]
        age = None if last_open is None else round(
            (now_ms - (int(last_open) + INTERVAL_MS)) / 60_000, 2
        )
        fresh = (age is not None and -1 <= age <= max_age_minutes)
        fresh = fresh and item["continuity"] and symbol not in base_missing
        freshness[symbol] = {
            "fresh": bool(fresh), "age_minutes": age,
            "last_open_ms": last_open, "continuity": item["continuity"],
            "reason": None if fresh else (
                "BASELINE_MISSING_OR_INCOMPLETE" if symbol in base_missing or not item["continuity"]
                else "LATEST_15M_CANDLE_STALE"
            ),
            "provider_status": tail_status.get(symbol, {}),
            "new_rows": new_rows_by_symbol.get(symbol, 0),
        }

    symbols_complete = sum(1 for x in compute_results.values() if x["continuity"])
    symbols_fresh = sum(1 for x in freshness.values() if x["fresh"])
    gate_status = "PASS" if symbols_complete == 27 and symbols_fresh == 27 else "DEGRADED"

    # اجرای موتور فقط روی دادهٔ ادغام‌شده؛ نماد stale به MARKET_DATA_DEGRADED تبدیل می‌شود.
    engine_report = engine.run(compute_dir, output_path, universe_path)
    signals_by_symbol = {x.get("symbol"): x for x in engine_report.get("signals", [])}
    guarded_signals: list[dict[str, Any]] = []
    for symbol in symbols:
        signal = signals_by_symbol.get(symbol)
        state = freshness[symbol]
        if not state["fresh"]:
            signal = engine._no_setup(
                symbol,
                "MARKET_DATA_DEGRADED:" + str(state["reason"]),
                compute_results[symbol]["rows"],
            )
            signal["decision"] = "MARKET_DATA_DEGRADED"
            signal["status"] = "MARKET_DATA_DEGRADED"
        elif signal is None:
            signal = engine._no_setup(symbol, "NO_ENGINE_OUTPUT", compute_results[symbol]["rows"])
            signal["decision"] = "MARKET_DATA_DEGRADED"
            signal["status"] = "MARKET_DATA_DEGRADED"
        signal["data_freshness"] = state
        guarded_signals.append(signal)

    engine_report["signals"] = guarded_signals
    engine_report["symbols_analyzed"] = len(guarded_signals)
    engine_report["candidate_setups"] = sum(
        1 for x in guarded_signals
        if x.get("direction") in ("BUY", "SELL")
        and x.get("decision") != "MARKET_DATA_DEGRADED"
    )
    engine_report["data_gate_status"] = gate_status
    engine_report["data_coverage"] = {
        "universe_count": 27, "symbols_complete": symbols_complete,
        "symbols_fresh": symbols_fresh, "baseline_days": 730,
        "expected_rows_per_symbol": EXPECTED_ROWS,
        "interval": "15m", "max_age_minutes": max_age_minutes,
        "window_start_utc": datetime.fromtimestamp(window_start_ms / 1000, timezone.utc).isoformat(),
        "window_end_exclusive_utc": datetime.fromtimestamp(closed_end_ms / 1000, timezone.utc).isoformat(),
    }
    engine_report["data_freshness"] = freshness
    engine_report["ev_status"] = "NOT_CALIBRATED"
    engine_report["storage_layout"] = "BASELINE_PLUS_IMMUTABLE_4H_TAIL_PARTITIONS"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(engine_report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    report = {
        "generated_at_utc": datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
        "universe_as_of_utc": universe.get("as_of_utc"),
        "start_date_utc": datetime.fromtimestamp(window_start_ms / 1000, timezone.utc).date().isoformat(),
        "end_date_exclusive_utc": datetime.fromtimestamp(closed_end_ms / 1000, timezone.utc).isoformat(),
        "interval": "15m", "universe_count": 27,
        "symbols_complete": symbols_complete, "symbols_fresh": symbols_fresh,
        "symbols_processed": 27, "status": gate_status,
        "baseline_status": "PASS" if not base_missing else "DEGRADED",
        "storage_migration": {
            "migrated_symbols": migration["migrated_symbols"],
            "removed_legacy_files": len(migration["removed_legacy_files"]),
            "missing_symbols": base_missing,
        },
        "symbols": [
            {**compute_results[symbol], **freshness[symbol]}
            for symbol in symbols
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("STAGE1B_LIVE_DATA " + json.dumps({
        "complete": symbols_complete, "fresh": symbols_fresh,
        "universe": 27, "status": gate_status,
    }), flush=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain rolling LRT-15m data with fresh live tails.")
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--compute-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    args = parser.parse_args()
    report = maintain_dataset(
        args.storage_dir, args.compute_dir, args.report, args.output,
        args.universe, max_age_minutes=args.max_age_minutes,
    )
    return 0 if report["status"] in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
