import unittest
from unittest.mock import Mock
from app.data_layer.quality import validate_ohlcv_rows, gap_report


class DataLayerQualityTests(unittest.TestCase):
    def test_sorts_and_deduplicates_by_utc_timestamp(self):
        rows=[
            {"timestamp":3600000,"open":2,"high":3,"low":1.5,"close":2.5,"volume":10},
            {"timestamp":0,"open":1,"high":2,"low":0.5,"close":1.5,"volume":9},
            {"timestamp":3600000,"open":2,"high":4,"low":1.5,"close":3,"volume":11},
        ]
        got=validate_ohlcv_rows(rows)
        self.assertEqual([x["timestamp"] for x in got],[0,3600000])
        self.assertEqual(got[-1]["close"],3)

    def test_rejects_invalid_ohlcv_schema(self):
        with self.assertRaisesRegex(ValueError,"ohlcv_missing_fields"):
            validate_ohlcv_rows([{"timestamp":1,"open":1}])

    def test_rejects_impossible_high_low(self):
        row={"timestamp":1,"open":2,"high":1,"low":1.5,"close":2,"volume":1}
        with self.assertRaisesRegex(ValueError,"ohlcv_high_below_price"):
            validate_ohlcv_rows([row])

    def test_gap_report_flags_missing_hour(self):
        rows=validate_ohlcv_rows([
            {"timestamp":0,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
            {"timestamp":7200000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        report=gap_report(rows)
        self.assertFalse(report["no_gap_over_1h"])
        self.assertEqual(report["missing_intervals"],1)

    def test_gap_report_passes_contiguous_hours(self):
        rows=validate_ohlcv_rows([
            {"timestamp":0,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
            {"timestamp":3600000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        self.assertTrue(gap_report(rows)["no_gap_over_1h"])


if __name__=="__main__":
    unittest.main()
