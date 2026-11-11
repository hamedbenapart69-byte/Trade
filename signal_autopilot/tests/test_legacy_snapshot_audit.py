"""تست‌های ممیزی read-only برای تعارض Snapshotهای خام."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_legacy_snapshots.py"
SPEC = importlib.util.spec_from_file_location("audit_legacy_snapshots", MODULE_PATH)
audit_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(audit_module)

STEP = 900_000


def row(ts: int, close: float = 101.0) -> dict:
    return {
        "open_time": ts, "open": 100.0, "high": max(102.0, close),
        "low": 99.0, "close": close, "volume": 10.0,
    }


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path)


class LegacySnapshotAuditTests(unittest.TestCase):
    def _fixture(self, root: Path):
        raw = root / "raw"
        canonical = root / "canonical"
        old_rows = [row(0), row(STEP), row(2 * STEP)]
        new_rows = [row(STEP), row(2 * STEP), row(3 * STEP)]
        old = raw / "BTCUSDT_15m_2024-11-09_2026-11-09.parquet"
        new = raw / "BTCUSDT_15m_2024-11-10_2026-11-10.parquet"
        target = canonical / "BTCUSDT_15m.parquet"
        write(old, old_rows)
        write(new, new_rows)
        write(target, new_rows)
        return raw, canonical, old_rows, new_rows, target

    def test_identical_overlap_and_newest_canonical_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, canonical, _, _, _ = self._fixture(root)
            report = audit_module.audit(raw, canonical, root / "report.json", 1, "raw-sha", "canonical-sha")
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["raw_files_seen"], 2)
            self.assertEqual(report["overlap_rows_compared"], 2)
            self.assertEqual(report["conflicting_ohlcv_rows"], 0)
            self.assertEqual(report["canonical_files_match_newest"], 1)

    def test_conflicting_ohlcv_is_reported_as_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, canonical, _, new_rows, _ = self._fixture(root)
            changed = list(new_rows)
            changed[0] = row(STEP, close=101.5)
            write(raw / "BTCUSDT_15m_2024-11-10_2026-11-10.parquet", changed)
            write(canonical / "BTCUSDT_15m.parquet", changed)
            report = audit_module.audit(raw, canonical, root / "report.json", 1, "raw-sha", "canonical-sha")
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["conflicting_ohlcv_rows"], 1)

    def test_canonical_must_match_newest_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, canonical, old_rows, _, target = self._fixture(root)
            write(target, old_rows)
            report = audit_module.audit(raw, canonical, root / "report.json", 1, "raw-sha", "canonical-sha")
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any(x["error"] == "CANONICAL_NOT_EXACTLY_NEWEST_VALID_SNAPSHOT"
                                for x in report["errors"]))

    def test_missing_raw_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw, canonical, _, _, _ = self._fixture(root)
            (raw / "BTCUSDT_15m_2024-11-09_2026-11-09.parquet").unlink()
            report = audit_module.audit(
                raw, canonical, root / "report.json", 1, "raw-sha", "canonical-sha"
            )
            self.assertEqual(report["status"], "FAIL")
            self.assertTrue(any(
                item["error"] == "EXPECTED_TWO_RAW_SNAPSHOTS:1"
                for item in report["errors"]
            ))


if __name__ == "__main__":
    unittest.main()
