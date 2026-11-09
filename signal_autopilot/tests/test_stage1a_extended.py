import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from download_stage1a_extended_history import (
    month_iter, dates_for_month, build_report, request_bytes
)


class ArchiveWindowTests(unittest.TestCase):
    def test_months_cover_two_year_window(self):
        months = list(month_iter(date(2024, 11, 8), date(2026, 11, 8)))
        self.assertEqual(len(months), 24)
        self.assertEqual(months[0], date(2024, 11, 1))
        self.assertEqual(months[-1], date(2026, 10, 1))

    def test_daily_fallback_days_are_clipped_to_requested_window(self):
        days = list(dates_for_month(date(2026, 11, 1), date(2024, 11, 8), date(2026, 11, 8)))
        self.assertEqual(days, [date(2026, 11, d) for d in range(1, 8)])

    def test_listing_filter_count_is_reported(self):
        listing = {"BTCUSDT": {"listing_date": "2019-09-08"}}
        report = build_report(
            ["BTCUSDT", "NEWUSDT"], listing, ["BTCUSDT"],
            [{"symbol": "BTCUSDT", "continuity": True}],
            date(2024, 11, 8), date(2026, 11, 8), "RUNNING"
        )
        self.assertEqual(report["symbols_before_filter"], 2)
        self.assertEqual(report["symbols_after_listing_filter"], 1)
        self.assertEqual(report["symbols_full_history"], 1)


class HttpPolicyTests(unittest.TestCase):
    def test_404_is_not_retried(self):
        calls = {"n": 0}
        def fake_urlopen(request, timeout=0):
            calls["n"] += 1
            raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            status, payload = request_bytes("https://example.invalid/archive.zip", "HEAD")
        self.assertEqual(status, 404)
        self.assertEqual(payload, b"")
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
