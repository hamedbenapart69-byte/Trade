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




class RiskExitAndPboTests(unittest.TestCase):
    def _daily_frame(self, start="2024-01-01", count=35):
        dates = pd.date_range(start, periods=count, freq="D", tz="UTC")
        return pd.DataFrame({
            "date": dates,
            "open": [100.0] * count,
            "high": [101.0] * count,
            "low": [99.0] * count,
            "close": [100.0] * count,
            "volume": [1000.0] * count,
        })

    def test_trailing_stop_uses_prior_peak_and_gap_conservative_fill(self):
        frame = self._daily_frame()
        monday, friday = frame.loc[21, "date"], frame.loc[25, "date"]
        frame.loc[21, ["open", "high", "low", "close"]] = [100.0, 105.0, 99.0, 104.0]
        frame.loc[22, ["open", "high", "low", "close"]] = [104.0, 110.0, 103.0, 108.0]
        frame.loc[23, ["open", "high", "low", "close"]] = [90.0, 95.0, 89.0, 92.0]
        result = futures.risk_adjusted_exit(frame, monday, friday)
        self.assertEqual(result["exit_reason"], "TRAILING_STOP_15PCT")
        self.assertAlmostEqual(result["stop_level"], 93.5)
        self.assertAlmostEqual(result["exit_price"], 90.0)  # gap below stop
        self.assertAlmostEqual(result["return"], -0.10)

    def test_ma20_close_break_exits_at_daily_close(self):
        frame = self._daily_frame()
        monday, friday = frame.loc[21, "date"], frame.loc[25, "date"]
        frame.loc[21, ["open", "high", "low", "close"]] = [100.0, 101.0, 98.0, 99.0]
        result = futures.risk_adjusted_exit(frame, monday, friday)
        self.assertEqual(result["exit_reason"], "DAILY_CLOSE_BELOW_MA20")
        self.assertEqual(result["exit_price"], 99.0)
        self.assertAlmostEqual(result["return"], -0.01, places=12)


    def test_asset_trend_confirmation_requires_close_above_rising_ma20(self):
        rising = self._daily_frame(count=40)
        rising["close"] = [80.0 + i for i in range(40)]
        asof = rising.loc[39, "date"]
        self.assertTrue(futures.asset_trend_confirmed(rising, asof))

        falling = self._daily_frame(count=40)
        falling["close"] = [120.0 - i for i in range(40)]
        self.assertFalse(futures.asset_trend_confirmed(falling, asof))


    def test_market_breadth_requires_five_of_eight_above_ma20(self):
        dates = pd.date_range("2024-01-01", periods=25, freq="D", tz="UTC")
        frames = {}
        for i in range(8):
            closes = [100.0] * 25
            ma = [99.0 if i < 5 else 101.0] * 25
            frames[f"A{i}"] = pd.DataFrame({
                "date": dates, "close": closes, "sma20": ma,
            })
        asof = dates[-1]
        above = futures.market_breadth_assets(frames, asof)
        self.assertEqual(len(above), 5)
        self.assertTrue(all(x in above for x in ["A0", "A1", "A2", "A3", "A4"]))

    def test_cscv_pbo_builds_70_splits_and_a_weekly_return_matrix(self):
        dates = pd.date_range("2020-01-06", periods=80, freq="W-MON", tz="UTC")
        variants = {}
        for name, shift in (("BTC_MA40", 0.001), ("BTC_MA50", 0.0), ("BTC_MA60", -0.001)):
            rows = []
            for i, week in enumerate(dates):
                value = 0.01 * ((-1.0) ** i) + shift
                rows.append({"monday": week, "net_return": value})
            variants[name] = rows
        result = futures.cscv_pbo(variants, n_blocks=8)
        self.assertEqual(result["status"], "COMPUTED")
        self.assertEqual(result["split_count"], 70)
        self.assertEqual(len(result["weekly_return_matrix"]), 80)
        self.assertGreaterEqual(result["value"], 0.0)
        self.assertLessEqual(result["value"], 1.0)


if __name__ == "__main__":
    unittest.main()
