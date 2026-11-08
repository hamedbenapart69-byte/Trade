import unittest
from app.data_layer.quality import validate_ohlcv_rows, gap_report


class DataLayerQualityTests(unittest.TestCase):
    BASE = 1_700_000_000_000

    def test_sorts_and_deduplicates_by_utc_timestamp(self):
        rows=[
            {"timestamp":self.BASE+3_600_000,"open":2,"high":3,"low":1.5,"close":2.5,"volume":10},
            {"timestamp":self.BASE,"open":1,"high":2,"low":0.5,"close":1.5,"volume":9},
            {"timestamp":self.BASE+3_600_000,"open":2,"high":4,"low":1.5,"close":3,"volume":11},
        ]
        got=validate_ohlcv_rows(rows)
        self.assertEqual([x["timestamp"] for x in got],[self.BASE,self.BASE+3_600_000])
        self.assertEqual(got[-1]["close"],3)

    def test_rejects_invalid_ohlcv_schema(self):
        with self.assertRaisesRegex(ValueError,"ohlcv_missing_fields"):
            validate_ohlcv_rows([{"timestamp":self.BASE,"open":1}])

    def test_rejects_impossible_high_low(self):
        row={"timestamp":self.BASE,"open":2,"high":1,"low":1.5,"close":2,"volume":1}
        with self.assertRaisesRegex(ValueError,"ohlcv_high_below_price"):
            validate_ohlcv_rows([row])

    def test_gap_report_flags_missing_hour(self):
        rows=validate_ohlcv_rows([
            {"timestamp":self.BASE,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
            {"timestamp":self.BASE+7_200_000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        report=gap_report(rows)
        self.assertFalse(report["no_gap_over_1h"])
        self.assertEqual(report["missing_intervals"],1)

    def test_gap_report_passes_contiguous_hours(self):
        rows=validate_ohlcv_rows([
            {"timestamp":self.BASE,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
            {"timestamp":self.BASE+3_600_000,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        self.assertTrue(gap_report(rows)["no_gap_over_1h"])


if __name__=="__main__":
    unittest.main()
