import tempfile
import unittest
from app.data_layer.collector import Stage1Collector, MS_HOUR, MS_DAY
from app.data_layer.quality import validate_ohlcv_rows, gap_report


class FakeOIExchange:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    def market(self, symbol):
        return {"id":"BTCUSDT"}

    def request(self, path, api, method, params):
        self.calls += 1
        start = int(params["startTime"])
        end = int(params["endTime"])
        return [row for row in self.rows if start <= row["timestamp"] <= end][:500]


class DataLayerQualityTests(unittest.TestCase):
    BASE = 1_700_000_000_000

    def test_sorts_and_deduplicates_by_utc_timestamp(self):
        rows=[
            {"timestamp":self.BASE+MS_HOUR,"open":2,"high":3,"low":1.5,"close":2.5,"volume":10},
            {"timestamp":self.BASE,"open":1,"high":2,"low":0.5,"close":1.5,"volume":9},
            {"timestamp":self.BASE+MS_HOUR,"open":2,"high":4,"low":1.5,"close":3,"volume":11},
        ]
        got=validate_ohlcv_rows(rows)
        self.assertEqual([x["timestamp"] for x in got],[self.BASE,self.BASE+MS_HOUR])
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
            {"timestamp":self.BASE+2*MS_HOUR,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        report=gap_report(rows)
        self.assertFalse(report["no_gap_over_1h"])
        self.assertEqual(report["missing_intervals"],1)

    def test_gap_report_passes_contiguous_hours(self):
        rows=validate_ohlcv_rows([
            {"timestamp":self.BASE,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
            {"timestamp":self.BASE+MS_HOUR,"open":1,"high":2,"low":0.5,"close":1.5,"volume":1},
        ])
        self.assertTrue(gap_report(rows)["no_gap_over_1h"])

    def test_open_interest_paginates_more_than_500_rows(self):
        start=self.BASE
        rows=[{"timestamp":start+i*MS_HOUR,"sumOpenInterest":"100",
               "sumOpenInterestValue":"100000"} for i in range(720)]
        fake=FakeOIExchange(rows)
        collector=Stage1Collector(data_dir=tempfile.mkdtemp(),exchange=fake)
        got=collector.fetch_open_interest_history("BTC/USDT:USDT",start,start+30*MS_DAY)
        self.assertEqual(len(got),720)
        self.assertEqual(fake.calls,3)
        self.assertEqual(got[0]["symbol"],"BTCUSDT")
        self.assertEqual(got[-1]["timestamp"],start+719*MS_HOUR)


if __name__=="__main__":
    unittest.main()
