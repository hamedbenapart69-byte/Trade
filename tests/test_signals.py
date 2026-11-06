import os, tempfile, unittest
from pathlib import Path
from app.signals import Candle, CandleError, ema, rsi, atr, volume_ratio, validate_candles, risk_calc, _score, save_scan, performance
from app import store

class V5IndicatorTests(unittest.TestCase):
    def test_ema_rsi_atr(self):
        self.assertAlmostEqual(ema([100.0]*30,20)[-1],100.0)
        self.assertGreater(rsi([float(i) for i in range(40)],14)[-1],99.0)
        cs=[Candle(i*60000,100+i,102+i,99+i,101+i,10,(i+1)*60000-1) for i in range(40)]
        self.assertGreater(atr(cs,14)[-1],0)

    def test_volume_ratio_uses_previous_twenty(self):
        cs=[Candle(i*60000,100,101,99,100,10,(i+1)*60000-1) for i in range(21)]
        cs[-1]=Candle(cs[-1].open_time,100,101,99,100,20,cs[-1].close_time)
        self.assertAlmostEqual(volume_ratio(cs),2.0)

    def test_candle_gap_and_bad_ohlc_rejected(self):
        cs=[Candle(i*60000,100,101,99,100,10,(i+1)*60000-1) for i in range(5)]
        validate_candles(cs,60000,now=310000,min_count=5)
        gap=cs[:2]+[Candle(180000,100,101,99,100,10,239999)]+cs[3:]
        with self.assertRaises(CandleError): validate_candles(gap,60000,now=310000,min_count=5)
        bad=cs[:];bad[2]=Candle(120000,100,98,99,100,10,179999)
        with self.assertRaises(CandleError): validate_candles(bad,60000,now=310000,min_count=5)

class V5RiskTests(unittest.TestCase):
    def test_four_dollar_risk_and_five_x_cap(self):
        r=risk_calc("LONG",100,1,0.001,0.001)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["stop_loss"],98.5)
        self.assertAlmostEqual(r["take_profit"],103.0)
        self.assertLessEqual(r["planned_loss_usd"],4.0)
        self.assertLessEqual(r["required_leverage"],5.0)
        self.assertGreaterEqual(r["reward_to_risk"],2.0)

    def test_wide_stop_and_minimum_quantity_rejected(self):
        self.assertEqual(risk_calc("SHORT",100,3,None,None)["reason"],"stop_distance_out_of_range")
        self.assertEqual(risk_calc("LONG",100000,10,1,1)["reason"],"quantity_below_contract_minimum")

class V5ScoringAndStorageTests(unittest.TestCase):
    def test_missing_advanced_sources_get_zero_points(self):
        tech={"close":101,"ema20":100,"ema50":99,"volume_ratio":2,"macd_aligned":True,"rsi":25,"price_change":1}
        trends={"1d":"BULLISH","4h":"UP"}
        structure={"classification":"BULLISH","bos":True}
        score,parts=_score("LONG",tech,trends,structure,None,None,-0.0001,True,True)
        self.assertLessEqual(score,100)
        self.assertEqual(parts["smart_money_onchain"],0)
        self.assertEqual(parts["independent_confirmation"],0)
        self.assertEqual(sum(parts.values()),score)

    def test_scan_records_persist(self):
        tmp=tempfile.TemporaryDirectory()
        old=os.environ.get("CONTROL_DB_PATH")
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"signals.db")
        try:
            store.init_db()
            result={"scan_id":"test-scan-v5","scanned_at":"2026-11-06T00:00:00+00:00",
              "actionable":[{"symbol":"BTCUSDT","direction":"LONG","decision":"BUY_NOW","entry":100.0,
                "stop_loss":98.5,"take_profit":103.0,"entry_observed_at_ms":1000,"confidence_v5":75,
                "data_grade":"B","risk":{"planned_loss_usd":4.0}}],
              "conditional":[]}
            saved=save_scan(result)
            self.assertEqual(saved["published_records_saved"],1)
            self.assertEqual(performance()["published_actionable"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

if __name__=="__main__":unittest.main()
