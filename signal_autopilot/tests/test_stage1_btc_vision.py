from __future__ import annotations

import csv
import hashlib
import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage1_btc_vision as stage1

HOUR = stage1.INTERVAL_MS
NOW = 1_800_000_000_000


def archive_with_rows(rows: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerows(rows)
        archive.writestr("BTCUSDT-1h-test.csv", csv_buffer.getvalue())
    return buffer.getvalue()


def valid_rows(count: int = 24) -> list[list[str]]:
    start = ((NOW - 25 * HOUR) // HOUR) * HOUR
    result = []
    for i in range(count):
        ts = start + i * HOUR
        result.append([
            str(ts), "100", "105", "99", "103", "1.25",
            str(ts + HOUR - 1), "128.75", "100", "0.75", "77.25", "0",
        ])
    return result


class Stage1VisionTests(unittest.TestCase):
    def test_01_sha256_is_deterministic(self):
        self.assertEqual(stage1.sha256_hex(b"abc"), hashlib.sha256(b"abc").hexdigest())

    def test_02_checksum_parser_accepts_sha256(self):
        digest = "a" * 64
        self.assertEqual(stage1.parse_checksum(f"{digest}  sample.zip".encode()), digest)

    def test_03_checksum_parser_rejects_malformed_value(self):
        with self.assertRaises(stage1.Stage1DataError):
            stage1.parse_checksum(b"not-a-sha")

    def test_04_daily_zip_parses_24_rows(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW)
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0]["open"], 100.0)
        self.assertEqual(rows[-1]["taker_buy_base"], 0.75)

    def test_05_corrupt_zip_is_rejected(self):
        with self.assertRaises(stage1.Stage1DataError):
            stage1.parse_daily_zip(b"not-a-zip", NOW)

    def test_06_ohlc_relationship_is_rejected(self):
        rows = valid_rows()
        rows[5][2] = "101"
        with self.assertRaises(stage1.Stage1DataError):
            stage1.parse_daily_zip(archive_with_rows(rows), NOW)

    def test_07_incomplete_close_is_excluded(self):
        rows = valid_rows()
        ts = NOW
        rows.append([
            str(ts), "100", "105", "99", "103", "1.25",
            str(ts + HOUR - 1), "128.75", "100", "0.75", "77.25", "0",
        ])
        parsed = stage1.parse_daily_zip(archive_with_rows(rows), NOW)
        self.assertEqual(len(parsed), 24)

    def test_08_exactly_24_closed_contiguous_candles_are_selected(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW)
        selected = stage1.select_latest_24(rows, NOW)
        self.assertEqual(len(selected), 24)
        self.assertEqual(selected[-1]["timestamp_ms"] - selected[0]["timestamp_ms"], 23 * HOUR)

    def test_09_less_than_24_closed_candles_is_rejected(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows(23)), NOW)
        with self.assertRaises(stage1.Stage1DataError):
            stage1.select_latest_24(rows, NOW)

    def test_10_gap_in_latest_window_is_rejected(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW)
        rows[12]["timestamp_ms"] += HOUR
        with self.assertRaises(stage1.Stage1DataError):
            stage1.select_latest_24(rows, NOW)

    def test_11_staleness_over_26_hours_is_rejected(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW)
        latest = rows[-1]["close_time_ms"]
        late_now = latest + stage1.MAX_STALENESS_MS + 1
        with self.assertRaises(stage1.Stage1DataError):
            stage1.select_latest_24(rows, late_now)

    def test_12_exact_26_hour_boundary_is_rejected(self):
        rows = stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW)
        latest = rows[-1]["close_time_ms"]
        with self.assertRaises(stage1.Stage1DataError):
            stage1.select_latest_24(rows, latest + stage1.MAX_STALENESS_MS)

    def test_13_contract_explicitly_disables_signal_generation(self):
        candles = stage1.select_latest_24(
            stage1.parse_daily_zip(archive_with_rows(valid_rows()), NOW), NOW
        )
        contract = stage1.build_l1_contract(
            candles, NOW, "https://example.invalid/archive.zip",
            "https://example.invalid/archive.zip.CHECKSUM",
            "a" * 64, "b" * 64, 123, "archive.zip", "test-run"
        )
        self.assertFalse(contract["signal_generation_enabled"])
        self.assertEqual(contract["trading_decision"], "NOT_IN_SCOPE")
        self.assertEqual(contract["instruments"][0]["availability"]["funding"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
