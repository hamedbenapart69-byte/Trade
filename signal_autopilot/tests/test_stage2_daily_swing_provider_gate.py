from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import stage2_daily_swing_provider_gate as gate


def zip_rows(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        text = io.StringIO()
        csv.writer(text).writerows(rows)
        zf.writestr("test.csv", text.getvalue())
    return buf.getvalue()


def rows_for(interval, now_ms):
    duration = gate.TIMEFRAMES[interval]
    count = 1 if interval == "1d" else 6
    day_start = (now_ms // 86_400_000 - 1) * 86_400_000
    return [[str(day_start + i * duration), "100", "105", "99", "103", "10",
             str(day_start + (i + 1) * duration - 1), "1030", "5", "5", "515", "0"]
            for i in range(count)]


class Stage2ProviderGateTests(unittest.TestCase):
    def test_universe_requires_exactly_27_unique_symbols(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "universe.json"
            path.write_text(json.dumps({"symbols": ["BTCUSDT"]}), encoding="utf-8")
            with self.assertRaises(gate.GateError):
                gate.load_universe(path)

    def test_daily_archive_parses_one_closed_candle(self):
        now = 1_800_000_000_000
        parsed = gate.parse_archive(zip_rows(rows_for("1d", now)), "BTCUSDT", "1d", now)
        self.assertEqual(len(parsed), 1)
        self.assertTrue(parsed[0]["closed"])

    def test_four_hour_archive_parses_six_closed_candles(self):
        now = 1_800_000_000_000
        parsed = gate.parse_archive(zip_rows(rows_for("4h", now)), "BTCUSDT", "4h", now)
        self.assertEqual(len(parsed), 6)

    def test_duplicate_timestamps_rejected(self):
        now = 1_800_000_000_000
        rows = rows_for("4h", now)
        rows[1][0] = rows[0][0]
        with self.assertRaises(gate.GateError):
            gate.parse_archive(zip_rows(rows), "BTCUSDT", "4h", now)

    def test_gap_rejected(self):
        now = 1_800_000_000_000
        rows = rows_for("4h", now)
        rows[3][0] = str(int(rows[3][0]) + gate.TIMEFRAMES["4h"])
        with self.assertRaises(gate.GateError):
            gate.parse_archive(zip_rows(rows), "BTCUSDT", "4h", now)

    def test_open_candle_is_excluded_and_count_fails(self):
        now = 1_800_000_000_000
        rows = rows_for("4h", now)
        rows[-1][6] = str(now)
        with self.assertRaises(gate.GateError):
            gate.parse_archive(zip_rows(rows), "BTCUSDT", "4h", now)

    def test_ohlc_inconsistency_rejected(self):
        now = 1_800_000_000_000
        rows = rows_for("1d", now)
        rows[0][2] = "101"
        with self.assertRaises(gate.GateError):
            gate.parse_archive(zip_rows(rows), "BTCUSDT", "1d", now)

    def test_checksum_mismatch_rejected(self):
        now = 1_800_000_000_000
        payload = zip_rows(rows_for("1d", now))
        checksum = hashlib.sha256(b"not-the-archive").hexdigest().encode()
        responses = {".CHECKSUM": checksum + b"  file.zip", ".zip": payload}
        def fake_fetch(url, timeout=40):
            return responses[".CHECKSUM"] if url.endswith(".CHECKSUM") else responses[".zip"]
        with patch.object(gate, "fetch", side_effect=fake_fetch):
            with self.assertRaises(gate.GateError):
                gate.probe_one("BTCUSDT", "1d", "2026-11-21", now)

    def test_signal_generation_is_never_enabled(self):
        self.assertIn("signal_generation_enabled", gate.run.__code__.co_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
