import os, tempfile, unittest
from pathlib import Path
from app.signals import Candle, CandleError, ema, rsi, atr, volume_ratio, validate_candles, risk_calc, _score, save_scan, performance, PublicMarketData, DataError, _iso_ms, FuturesSignalEngine, INTERVALS
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
        gap=cs[:2]+[Candle(180000,100,101,99,100,10,239999),Candle(240000,100,101,99,100,10,299999),Candle(300000,100,101,99,100,10,359999)]
        with self.assertRaises(CandleError): validate_candles(gap,60000,now=310000,min_count=5)
        bad=cs[:];bad[2]=Candle(120000,100,98,99,100,10,179999)
        with self.assertRaises(CandleError): validate_candles(bad,60000,now=310000,min_count=5)

    def test_nonfinal_out_of_order_and_wrong_close_time_rejected(self):
        cs=[Candle(i*60000,100,101,99,100,10,(i+1)*60000-1) for i in range(5)]
        open_last=cs[:-1]+[Candle(cs[-1].open_time,100,101,99,100,10,cs[-1].close_time,False)]
        with self.assertRaises(CandleError):validate_candles(open_last,60000,now=310000,min_count=5)
        with self.assertRaises(CandleError):validate_candles(cs[1:]+cs[:1],60000,now=310000,min_count=5)
        wrong=cs[:];wrong[2]=Candle(120000,100,101,99,100,10,180000)
        with self.assertRaises(CandleError):validate_candles(wrong,60000,now=310000,min_count=5)

class V5RiskTests(unittest.TestCase):
    def test_four_dollar_risk_and_five_x_cap(self):
        r=risk_calc("LONG",100,98.5)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["stop_loss"],98.5)
        self.assertAlmostEqual(r["take_profit"],103.0)
        self.assertAlmostEqual(r["planned_loss_usd"],4.0)
        self.assertLessEqual(r["required_leverage"],5.0)
        self.assertGreaterEqual(r["reward_to_risk"],2.0)
        self.assertIsNone(r["quantity_contracts_reference"])
        self.assertGreater(r["quantity_base"],0)

    def test_wide_stop_rejected(self):
        self.assertEqual(risk_calc("SHORT",100,104.5)["reason"],"stop_distance_out_of_range")

class FakeTraderSpyProvider:
    calls=0
    def __init__(self,now,stale=False):
        self.now=now;self.stale=stale
    def discover(self):
        return [{"id":"bitcoin","symbol":"BTC","name":"Bitcoin","volume":1000000,"market_cap_rank":1,"current_price":100.0,"market_cap":10000000}]
    def tracked_symbols(self):return {"BTCUSDT"}
    def prices(self,symbols):
        return {"BTCUSDT":{"symbol":"BTCUSDT","price":100.0,"updatedAt":self.now}}
    def derivatives(self,symbols):
        stamp=self.now-20*60_000 if self.stale else self.now
        return {"BTCUSDT":{"symbol":"BTCUSDT","updatedAt":stamp,"markPrice":100.0,"indexPrice":100.0,
          "funding":{"rate":0.0001,"intervalHours":8},"openInterest":{"valueUsd":1000000,"change4hPct":1.0,"change24hPct":2.0,"priceChange24hPct":1.0},
          "positioning":{"globalLongShortRatio":1.0,"topTraderLongShortRatio":1.0,"takerBuySellRatio":1.0},"source":"fixture"}}
    def smart_money(self):
        return {"traders":[],"positions":[],"signals":[],"traders_observed_at_ms":self.now,"positions_observed_at_ms":self.now,"signals_observed_at_ms":self.now}
    def candles(self,symbol,tf,limit):
        iv=INTERVALS[tf];last=(self.now//iv)*iv-iv;first=last-(219*iv);out=[]
        for i in range(220):
            ot=first+i*iv;close=80+i*.1
            out.append(Candle(ot,close-.05,close+.2,close-.2,close,10,ot+iv-1,True))
        return out
    def close(self):pass

class V5PipelineTests(unittest.TestCase):
    def test_end_to_end_fixture_rejects_non_qualifying_market_without_fake_signal(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=1793967960000
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"pipeline.db")
        try:
            store.init_db()
            engine=FuturesSignalEngine(provider=FakeTraderSpyProvider(now),clock=lambda:now)
            result=engine.scan(limit=30)
            self.assertEqual(result["screened_assets"],1)
            self.assertTrue(result["partial_scan"])
            self.assertEqual(result["other_candidates"][0]["decision"],"REJECT")
            self.assertEqual(result["actionable"],[])
            self.assertFalse(result["source_status"]["account_connection"])
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

    def test_stale_live_futures_snapshot_becomes_insufficient_data(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=1793967960000
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"stale.db")
        try:
            store.init_db()
            engine=FuturesSignalEngine(provider=FakeTraderSpyProvider(now,stale=True),clock=lambda:now)
            result=engine.scan(limit=30)
            self.assertEqual(result["screened_assets"],0)
            self.assertEqual(result["coverage"]["insufficient_data"],1)
            self.assertEqual(result["other_candidates"][0]["decision"],"INSUFFICIENT_DATA")
            self.assertEqual(result["actionable"],[])
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

class V5ScoringAndStorageTests(unittest.TestCase):
    def test_missing_advanced_sources_get_zero_points(self):
        tech={"close":101,"ema20":100,"ema50":99,"volume_ratio":2,"macd_aligned":True,"rsi":25,"price_change":1,
          "adx":25,"bb_position":"lower_half","obv_aligned":True,"mfi_aligned":True}
        trends={"1d":"BULLISH","4h":"UP","1h":"UP"}
        structure={"classification":"BULLISH","bos":True,"choch":False,"fvg_aligned":True,"order_block_aligned":True,"liquidity_sweep_aligned":False}
        score,parts=_score("LONG",tech,trends,structure,2,3,4,1.5,1.1,-0.0001,5,True,0,False)
        self.assertLessEqual(score,100)
        self.assertEqual(parts["smart_money_onchain"],0)
        self.assertEqual(parts["independent_confirmation"],0)
        self.assertEqual(sum(parts.values()),score)
        self.assertLessEqual(score,100)

    def test_traderspy_key_is_required_and_timestamps_are_normalized(self):
        p=PublicMarketData(api_key="")
        with self.assertRaises(DataError):p._ts_get("/market/symbols")
        p.close()
        self.assertEqual(_iso_ms(1793967960281),1793967960281)
        self.assertGreater(_iso_ms("2026-11-06T12:00:00Z"),0)

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
