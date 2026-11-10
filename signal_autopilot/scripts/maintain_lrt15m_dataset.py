"""مدیریت افزایشی تاریخچهٔ LRT-15m، دریافت tail زنده و کنترل تازگی داده."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
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
MAX_TAIL_BARS_PER_RUN = 7 * 96
MAX_BARS_PER_API_REQUEST = 100
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


def freshness_state(last_open_ms: int | None, now_ms: int,
                    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
                    continuity: bool = True) -> dict[str, Any]:
    """فقط کندل بسته‌شده و پیوسته با سن حداکثر تعیین‌شده تازه محسوب می‌شود."""
    if last_open_ms is None:
        return {"fresh": False, "age_minutes": None}
    age = round((now_ms - (int(last_open_ms) + INTERVAL_MS)) / 60_000, 2)
    fresh = continuity and -1 <= age <= max_age_minutes
    return {"fresh": bool(fresh), "age_minutes": age}


def _legacy_end_date(path: Path) -> str:
    parts = path.stem.split("_")
    return parts[-1] if len(parts) >= 4 else ""


def _validate_baseline(path: Path) -> tuple[bool, int, int | None, int | None, str | None]:
    """اعتبارسنجی کامل baseline؛ فقط شمارش Timestamp برای پذیرش کافی نیست."""
    if not path.exists():
        return False, 0, None, None, "BASELINE_MISSING"
    rows = _read_rows(path)
    if not rows:
        return False, 0, None, None, "BASELINE_EMPTY"

    required = ("open_time", "open", "high", "low", "close", "volume")
    for index, row in enumerate(rows):
        if any(row.get(field) is None for field in required):
            return False, len(rows), None, None, f"BASELINE_REQUIRED_FIELD_MISSING:row={index}"
        try:
            timestamp = int(row["open_time"])
            values = [float(row[field]) for field in ("open", "high", "low", "close", "volume")]
        except (TypeError, ValueError, OverflowError):
            return False, len(rows), None, None, f"BASELINE_INVALID_VALUE:row={index}"
        if timestamp % INTERVAL_MS:
            return False, len(rows), None, None, f"BASELINE_TIMESTAMP_ALIGNMENT:row={index}"
        if not all(math.isfinite(value) for value in values):
            return False, len(rows), None, None, f"BASELINE_NON_FINITE_OHLCV:row={index}"
        opn, high, low, close, volume = values
        if min(opn, high, low, close) <= 0 or volume < 0:
            return False, len(rows), None, None, f"BASELINE_OHLCV_RANGE:row={index}"
        if high < max(opn, close, low) or low > min(opn, close, high):
            return False, len(rows), None, None, f"BASELINE_OHLC_RELATION:row={index}"

    raw_timestamps = [int(row["open_time"]) for row in rows]
    if raw_timestamps != sorted(raw_timestamps):
        return False, len(rows), min(raw_timestamps), max(raw_timestamps), "BASELINE_OUT_OF_ORDER"
    if len(raw_timestamps) != len(set(raw_timestamps)):
        return False, len(rows), min(raw_timestamps), max(raw_timestamps), "BASELINE_DUPLICATE_TIMESTAMPS"
    timestamps = raw_timestamps
    gaps = sum(1 for left, right in zip(timestamps, timestamps[1:]) if right - left != INTERVAL_MS)
    complete = len(timestamps) == EXPECTED_ROWS and gaps == 0
    reason = None if complete else f"BASELINE_INCOMPLETE:rows={len(timestamps)}:gaps={gaps}"
    return complete, len(timestamps), timestamps[0], timestamps[-1], reason


def migrate_legacy_snapshots(storage_dir: Path, symbols: list[str]) -> dict[str, Any]:
    """جدیدترین snapshot کامل و معتبر را انتخاب و نسخه‌های قدیمی را از مسیر فعال جمع می‌کند."""
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

        if not valid:
            # از جدیدترین به قدیمی‌ترین حرکت می‌کنیم؛ snapshot ناقص انتخاب نمی‌شود.
            for candidate in candidates:
                temporary = base_dir / f".{symbol}_15m_candidate.parquet"
                temporary.unlink(missing_ok=True)
                shutil.copy2(candidate, temporary)
                candidate_valid, candidate_rows, candidate_first, candidate_last, candidate_reason = _validate_baseline(temporary)
                if candidate_valid:
                    temporary.replace(target)
                    migrated.append(symbol)
                    valid, rows, first_ms, last_ms, reason = (
                        candidate_valid, candidate_rows, candidate_first, candidate_last, candidate_reason
                    )
                    break
                temporary.unlink(missing_ok=True)
                reason = candidate_reason

        validation[symbol] = {
            "valid": valid, "rows": rows, "first_open_ms": first_ms,
            "last_open_ms": last_ms, "reason": reason,
        }
        if not valid:
            missing.append(symbol)
            continue

        # فایل‌های اصلی از تاریخچه Git حذف نمی‌شوند؛ فقط از مسیر فعال خارج می‌شوند.
        # Commit قبلی market-data منبع بازیابی نسخه‌های خام باقی می‌ماند.
        for candidate in candidates:
            candidate.unlink(missing_ok=True)
            removed.append(candidate.name)

    return {
        "base_dir": str(base_dir), "migrated_symbols": migrated,
        "removed_legacy_files": removed, "missing_symbols": missing,
        "validation": validation,
        "raw_snapshots_preserved_in_git_history": True,
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
    chunk_count = 0

    for chunk_start in range(start_ms, end_ms, MAX_BARS_PER_API_REQUEST * INTERVAL_MS):
        chunk_end = min(end_ms, chunk_start + MAX_BARS_PER_API_REQUEST * INTERVAL_MS)
        chunk_expected = set(range(chunk_start, chunk_end, INTERVAL_MS))
        chunk_count += 1

        try:
            okx_rows, okx_status = downloader.fetch_okx_history_15m(
                symbol, chunk_start, chunk_end
            )
            statuses["okx"] = okx_status
            for ts, row in okx_rows.items():
                ts = int(ts)
                if ts in chunk_expected and ts + INTERVAL_MS <= now_ms:
                    collected[ts] = dict(row)
        except Exception as exc:
            statuses["okx"] = f"ERROR:{type(exc).__name__}:{exc}"

        missing = chunk_expected.difference(collected)
        if missing:
            try:
                mexc_rows, mexc_status = downloader.fetch_mexc_futures_15m(
                    symbol, chunk_start, chunk_end
                )
                statuses["mexc"] = mexc_status
                for ts, row in mexc_rows.items():
                    ts = int(ts)
                    if ts in missing and ts + INTERVAL_MS <= now_ms:
                        collected[ts] = dict(row)
            except Exception as exc:
                statuses["mexc"] = f"ERROR:{type(exc).__name__}:{exc}"

        missing = chunk_expected.difference(collected)
        if missing and symbol == "1000PEPEUSDT":
            try:
                proxy_rows, proxy_status = downloader.fetch_okx_pepe_spot_as_1000pepe(
                    symbol, chunk_start, chunk_end
                )
                statuses["okx_spot_proxy"] = proxy_status
                for ts, row in proxy_rows.items():
                    ts = int(ts)
                    if ts in missing and ts + INTERVAL_MS <= now_ms:
                        collected[ts] = dict(row)
            except Exception as exc:
                statuses["okx_spot_proxy"] = f"ERROR:{type(exc).__name__}:{exc}"

    statuses["chunks"] = str(chunk_count)
    statuses["expected_bars"] = str(len(expected))
    statuses["received_bars"] = str(len(collected))
    statuses["missing_bars"] = str(len(expected.difference(collected)))
    return collected, statuses

def _missing_baseline_result(symbol: str) -> tuple[str, dict[int, dict[str, Any]], dict[str, str], dict[int, dict[str, Any]]]:
    """Return the same four-field worker contract when a baseline is unavailable."""
    return symbol, {}, {"status": "BASELINE_MISSING"}, {}


def _tail_partition_path(storage_dir: Path, symbol: str, open_time_ms: int) -> Path:
    day = datetime.fromtimestamp(open_time_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    return storage_dir / "live_tail" / day / f"{symbol}_15m.parquet"


def _merge_rows(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for group in groups:
        for row in group:
            if row.get("open_time") is None:
                continue
            merged[int(row["open_time"])] = dict(row)
    return [merged[key] for key in sorted(merged)]


def _compute_window(storage_dir: Path, compute_dir: Path, symbol: str,
                    window_start_ms: int, window_end_ms: int,
                    ephemeral_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    base_path = storage_dir / "base" / f"{symbol}_15m.parquet"
    base_rows = _read_rows(base_path) if base_path.exists() else []
    tail_paths = sorted((storage_dir / "live_tail").glob(f"**/{symbol}_15m.parquet"))
    tail_groups = [_read_rows(path) for path in tail_paths]
    all_rows = _merge_rows(base_rows, *tail_groups, ephemeral_rows or [])
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
        "tail_rows": sum(len(group) for group in tail_groups) + len(ephemeral_rows or []),
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
                     downloader: Any | None = None, engine: Any | None = None,
                     data_only: bool = False) -> dict[str, Any]:
    now_ms = utc_now_ms() if now_ms is None else int(now_ms)
    downloader = downloader or _load_downloader()
    if not data_only and engine is None:
        sys.path.insert(0, str(Path.cwd() / "signal_autopilot"))
        engine = importlib.import_module("modules.lrt15m_engine")

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    symbols = universe.get("symbols", [])
    if len(symbols) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"Expected exactly 27 unique symbols; got {len(symbols)}")

    migration = migrate_legacy_snapshots(storage_dir, symbols)
    base_missing = migration["missing_symbols"]
    if base_missing and not data_only:
        # backfill کامل فقط خارج از P0 data-only و پس از تشخیص baseline نامعتبر مجاز است.
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
    ephemeral_by_symbol: dict[str, list[dict[str, Any]]] = {}

    current_day_start = datetime.fromtimestamp(now_ms / 1000, timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    current_day_start_ms = int(current_day_start.timestamp() * 1000)

    def collect_one(symbol: str):
        base_path = storage_dir / "base" / f"{symbol}_15m.parquet"
        if not base_path.exists():
            return _missing_baseline_result(symbol)
        base_rows = _read_rows(base_path)
        tail_paths = sorted((storage_dir / "live_tail").glob(f"**/{symbol}_15m.parquet"))
        tail_rows = _merge_rows(*[_read_rows(path) for path in tail_paths]) if tail_paths else []
        existing = _merge_rows(base_rows, tail_rows)
        existing_timestamps = {int(row["open_time"]) for row in existing}
        latest = int(existing[-1]["open_time"]) if existing else None
        recent_start_ms = max(window_start_ms, closed_end_ms - 7 * 24 * 60 * 60 * 1000)
        missing_recent = [
            ts for ts in range(recent_start_ms, closed_end_ms, INTERVAL_MS)
            if ts not in existing_timestamps
        ]
        start_ms = min(missing_recent) if missing_recent else (
            (latest + INTERVAL_MS) if latest is not None else window_start_ms
        )
        bars, statuses = _fetch_symbol_tail(symbol, start_ms, closed_end_ms, now_ms, downloader)
        # فقط روزهای کامل‌شده در Git ذخیره می‌شوند؛ tail روز جاری موقت است.
        persist_by_day: dict[str, list[dict[str, Any]]] = {}
        for ts, row in bars.items():
            if ts >= current_day_start_ms:
                continue
            day = datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d")
            persist_by_day.setdefault(day, []).append({"open_time": ts, **row})
        for day_rows in persist_by_day.values():
            partition = _tail_partition_path(storage_dir, symbol, int(day_rows[0]["open_time"]))
            prior = _read_rows(partition) if partition.exists() else []
            _write_rows(partition, _merge_rows(prior, day_rows))
        ephemeral = {
            ts: row for ts, row in bars.items() if ts >= current_day_start_ms
        }
        return symbol, bars, statuses, ephemeral

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(collect_one, symbol) for symbol in symbols]
        for future in as_completed(futures):
            symbol, bars, statuses, ephemeral = future.result()
            tail_status[symbol] = statuses
            new_rows_by_symbol[symbol] = len(bars)
            ephemeral_by_symbol[symbol] = [
                {"open_time": ts, **row} for ts, row in ephemeral.items()
            ]

    if compute_dir.exists():
        shutil.rmtree(compute_dir)
    compute_dir.mkdir(parents=True, exist_ok=True)
    compute_results = {
        symbol: _compute_window(storage_dir, compute_dir, symbol,
                                window_start_ms, closed_end_ms,
                                ephemeral_by_symbol.get(symbol, []))
        for symbol in symbols
    }

    freshness: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        item = compute_results[symbol]
        last_open = item["last_open_ms"]
        freshness_result = freshness_state(
            int(last_open) if last_open is not None else None,
            now_ms, max_age_minutes, item["continuity"] and symbol not in base_missing,
        )
        fresh = freshness_result["fresh"]
        freshness[symbol] = {
            "fresh": fresh, "age_minutes": freshness_result["age_minutes"],
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

    # حذف tailهای قدیمی‌تر از پنجرهٔ ۷۳۰روزه از درخت فعلی مخزن.
    tail_root = storage_dir / "live_tail"
    if tail_root.exists():
        cutoff_day = datetime.fromtimestamp(window_start_ms / 1000, timezone.utc).date()
        for path in tail_root.glob("*/*.parquet"):
            try:
                partition_day = date.fromisoformat(path.parent.name)
            except ValueError:
                continue
            if partition_day < cutoff_day:
                path.unlink(missing_ok=True)

    if not data_only:
        # اجرای موتور فقط در فاز مجاز؛ P0 با --data-only هیچ سیگنالی محاسبه یا منتشر نمی‌کند.
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
        engine_report["storage_layout"] = "BASELINE_PLUS_COMPLETED_DAILY_TAIL_PARTITIONS"
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_manifest(storage_dir: Path, report_path: Path, manifest_path: Path,
                           workflow_commit: str, engine_commit: str,
                           workflow_run_id: str, legacy_source_commit: str) -> dict[str, Any]:
    """Manifest مستقل از خروجی استراتژی؛ فقط دادهٔ فعال baseline و tail را هش می‌کند."""
    base_dir = storage_dir / "base"
    base_files = sorted(base_dir.glob("*_15m.parquet"))
    symbols = [path.name.removesuffix("_15m.parquet") for path in base_files]
    if len(base_files) != 27 or len(set(symbols)) != 27:
        raise ValueError(f"MANIFEST_SYMBOL_COVERAGE_FAIL:files={len(base_files)}:symbols={len(set(symbols))}")

    files: list[dict[str, Any]] = []
    timestamps_by_symbol: dict[str, set[int]] = {}
    for path in base_files:
        symbol = path.name.removesuffix("_15m.parquet")
        valid, rows, first_ms, last_ms, reason = _validate_baseline(path)
        if not valid:
            raise ValueError(f"MANIFEST_BASELINE_INVALID:{symbol}:{reason}")
        table_rows = _read_rows(path)
        timestamps_by_symbol[symbol] = {int(row["open_time"]) for row in table_rows}
        files.append({
            "path": str(path.relative_to(storage_dir)),
            "symbol": symbol, "kind": "BASELINE",
            "rows": rows, "size_bytes": path.stat().st_size,
            "first_open_ms": first_ms, "last_open_ms": last_ms,
            "sha256": _sha256_file(path),
        })

    tail_root = storage_dir / "live_tail"
    tail_files = sorted(tail_root.glob("**/*.parquet")) if tail_root.exists() else []
    for path in tail_files:
        rows = _read_rows(path)
        if not rows:
            raise ValueError(f"MANIFEST_EMPTY_TAIL:{path}")
        symbol = path.name.removesuffix("_15m.parquet")
        if symbol not in timestamps_by_symbol:
            raise ValueError(f"MANIFEST_UNKNOWN_TAIL_SYMBOL:{symbol}")
        timestamps = [int(row["open_time"]) for row in rows if row.get("open_time") is not None]
        if len(timestamps) != len(rows) or timestamps != sorted(timestamps):
            raise ValueError(f"MANIFEST_TAIL_TIMESTAMP_ORDER:{path}")
        if len(timestamps) != len(set(timestamps)):
            raise ValueError(f"MANIFEST_TAIL_DUPLICATE_TIMESTAMP:{path}")
        if any(ts % INTERVAL_MS for ts in timestamps):
            raise ValueError(f"MANIFEST_TAIL_ALIGNMENT:{path}")
        overlap = timestamps_by_symbol[symbol].intersection(timestamps)
        if overlap:
            raise ValueError(f"MANIFEST_CROSS_FILE_DUPLICATE:{symbol}:{min(overlap)}")
        timestamps_by_symbol[symbol].update(timestamps)
        files.append({
            "path": str(path.relative_to(storage_dir)),
            "symbol": symbol, "kind": "LIVE_TAIL",
            "rows": len(rows), "size_bytes": path.stat().st_size,
            "first_open_ms": min(timestamps), "last_open_ms": max(timestamps),
            "sha256": _sha256_file(path),
        })

    data_report = json.loads(report_path.read_text(encoding="utf-8"))
    files.sort(key=lambda item: (item["symbol"], item["kind"], item["path"]))
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {
        "schema_version": 1,
        "dataset": "stage1b_lrt15m_rolling_730d",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_gate_status": data_report.get("status", "UNKNOWN"),
        "universe_count": 27,
        "symbols": sorted(symbols),
        "symbols_count": len(symbols),
        "files_count": len(files),
        "baseline_files_count": len(base_files),
        "live_tail_files_count": len(tail_files),
        "rows_total": sum(item["rows"] for item in files),
        "files": files,
        "dataset_sha256": hashlib.sha256(canonical).hexdigest(),
        "hash_algorithm": "SHA-256",
        "hash_scope": "canonical sorted file list with per-file SHA-256, path, size and row count",
        "workflow_commit": workflow_commit,
        "engine_commit": engine_commit,
        "workflow_run_id": workflow_run_id,
        "legacy_source_commit": legacy_source_commit,
        "raw_legacy_snapshots_recoverable_from_git_history": True,
        "signal_engine_executed": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "status": manifest["data_gate_status"],
        "files": manifest["files_count"],
        "symbols": manifest["symbols_count"],
        "rows": manifest["rows_total"],
        "dataset_sha256": manifest["dataset_sha256"],
        "signal_engine_executed": False,
    }, ensure_ascii=False))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain rolling LRT-15m data with fresh live tails.")
    parser.add_argument("--storage-dir", type=Path, required=True)
    parser.add_argument("--compute-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    parser.add_argument("--data-only", action="store_true",
                        help="فقط نگهداری و اعتبارسنجی داده؛ موتور سیگنال اجرا نمی‌شود.")
    parser.add_argument("--manifest", type=Path,
                        help="مسیر خروجی Manifest نهایی SHA-256.")
    parser.add_argument("--workflow-commit", default="UNKNOWN")
    parser.add_argument("--engine-commit", default="UNKNOWN")
    parser.add_argument("--workflow-run-id", default="UNKNOWN")
    parser.add_argument("--legacy-source-commit", default="UNKNOWN")
    args = parser.parse_args()
    report = maintain_dataset(
        args.storage_dir, args.compute_dir, args.report, args.output,
        args.universe, max_age_minutes=args.max_age_minutes, data_only=args.data_only,
    )
    if args.manifest:
        build_dataset_manifest(
            args.storage_dir, args.report, args.manifest,
            args.workflow_commit, args.engine_commit, args.workflow_run_id,
            args.legacy_source_commit,
        )
    return 0 if report["status"] in {"PASS", "DEGRADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
