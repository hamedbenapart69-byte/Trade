from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import momentum_cash_futures_backtest as futures


def zipped_csv(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample.csv", text)
    return buffer.getvalue()


class FuturesKlineParserTests(unittest.TestCase):
    def test_legacy_headerless_usdm_layout_is_normalized_and_validated(self):
        csv = (
            "0,101871,1577836800000,1577923199999,208001969.84595,28834.200,409678760.56957,56801.329,7170.15,7189.43,7197.57,7260.43\n"
            "0,101000,1577923200000,1578009599999,209001969.84595,28934.200,410678760.56957,56901.329,7180.15,7197.57,7200.00,7280.43\n"
        )
        frame = futures.parse_kline_archive(zipped_csv(csv), "legacy-fixture")
        self.assertEqual(frame.attrs["schema_layout"], "HEADERLESS_LEGACY_UM_2020")
        self.assertEqual(frame.iloc[0]["date"], pd.Timestamp("2020-01-01", tz="UTC"))
        self.assertAlmostEqual(float(frame.iloc[0]["open"]), 7189.43)
        self.assertAlmostEqual(float(frame.iloc[0]["high"]), 7260.43)
        self.assertAlmostEqual(float(frame.iloc[0]["low"]), 7170.15)
        self.assertAlmostEqual(float(frame.iloc[0]["close"]), 7197.57)
        self.assertAlmostEqual(float(frame.iloc[0]["volume"]), 56801.329)

    def test_standard_headerless_usdm_layout_is_normalized(self):
        csv = (
            "1577836800000,7189.43,7260.43,7170.15,7197.57,56801.329,1577923199999,409678760.56957,101871,28834.2,208001969.84595,0\n"
        )
        frame = futures.parse_kline_archive(zipped_csv(csv), "standard-fixture")
        self.assertEqual(frame.attrs["schema_layout"], "HEADERLESS_STANDARD")
        self.assertAlmostEqual(float(frame.iloc[0]["open"]), 7189.43)
        self.assertAlmostEqual(float(frame.iloc[0]["close"]), 7197.57)

    def test_headered_usdm_layout_is_normalized(self):
        csv = (
            "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
            "1577836800000,7189.43,7260.43,7170.15,7197.57,56801.329,1577923199999,409678760.56957,101871,28834.2,208001969.84595,0\n"
        )
        frame = futures.parse_kline_archive(zipped_csv(csv), "headered-fixture")
        self.assertEqual(frame.attrs["schema_layout"], "HEADERED_STANDARD")
        self.assertAlmostEqual(float(frame.iloc[0]["volume"]), 56801.329)


class FundingAndMetricsTests(unittest.TestCase):
    def test_complete_eight_hour_funding_schedule_is_included_after_entry(self):
        monday = pd.Timestamp("2024-01-01T00:00:00Z")
        friday = pd.Timestamp("2024-01-05T00:00:00Z")
        times = pd.date_range(monday, monday + pd.Timedelta(hours=120), freq="8h")
        frame = pd.DataFrame({
            "time": times,
            "funding_interval_hours": 8.0,
            "last_funding_rate": 0.0001,
        })
        total, complete, count, reason = futures.funding_window(frame, monday, friday)
        self.assertTrue(complete, reason)
        self.assertEqual(count, 14)
        self.assertAlmostEqual(total, 0.0014, places=10)

    def test_missing_funding_event_fails_closed(self):
        monday = pd.Timestamp("2024-01-01T00:00:00Z")
        friday = pd.Timestamp("2024-01-05T00:00:00Z")
        times = pd.date_range(monday, monday + pd.Timedelta(hours=120), freq="8h")
        times = times.delete(4)
        frame = pd.DataFrame({
            "time": times,
            "funding_interval_hours": 8.0,
            "last_funding_rate": 0.0001,
        })
        _, complete, _, reason = futures.funding_window(frame, monday, friday)
        self.assertFalse(complete)
        self.assertEqual(reason, "FUNDING_SCHEDULE_GAP")

    def test_win_rate_uses_invested_weeks_not_cash_weeks(self):
        result = futures.extended_metrics(
            [0.0, 0.10, 0.0, -0.05],
            [False, True, False, True],
        )
        self.assertEqual(result["win_rate"], 0.5)
        self.assertEqual(result["invested_sample_count"], 2)


if __name__ == "__main__":
    unittest.main()
