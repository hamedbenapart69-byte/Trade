import json
import os, tempfile, unittest, time
from pathlib import Path
from datetime import datetime, timezone
from app.signals import Candle, CandleError, ema, rsi, atr, volume_ratio, v3_directional_baseline, provider_key_for_source, STABLES, WRAPPED, NON_CRYPTO_BASES, validate_candles, risk_calc, _score, save_scan, performance, PublicMarketData, DataError, _iso_ms, FuturesSignalEngine, INTERVALS, get_signal_status, reserve_traderspy_api_call, traderspy_daily_usage, evaluate_outcomes_with_provider, contract_sized_risk, _audit_checks_passed, _find_fvg, _find_order_block, classify_market_regime, _structure
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

class V5UniverseFilterTests(unittest.TestCase):
    def test_stable_wrapped_and_commodity_backed_assets_are_excluded(self):
        self.assertIn("USDT",STABLES)
        self.assertIn("WBTC",WRAPPED)
        self.assertEqual(NON_CRYPTO_BASES,{"PAXG","XAUT"})
        self.assertNotIn("BTC",NON_CRYPTO_BASES)
        self.assertNotIn("ETH",NON_CRYPTO_BASES)


class V5BaselineTests(unittest.TestCase):
    def test_long_requires_all_original_v3_baseline_conditions(self):
        self.assertEqual(v3_directional_baseline(34.9,1.21,101,100,99,"UP"),"LONG")
        self.assertEqual(v3_directional_baseline(30,1.3,101,100,99,"FLAT"),"LONG")
        self.assertIsNone(v3_directional_baseline(35,1.3,101,100,99,"UP"))
        self.assertIsNone(v3_directional_baseline(34,1.2,101,100,99,"UP"))
        self.assertIsNone(v3_directional_baseline(34,1.3,100,100,99,"UP"))
        self.assertIsNone(v3_directional_baseline(34,1.3,101,100,99,"DOWN"))

    def test_short_requires_all_original_v3_baseline_conditions(self):
        self.assertEqual(v3_directional_baseline(65.1,1.21,99,100,101,"DOWN"),"SHORT")
        self.assertEqual(v3_directional_baseline(70,1.3,99,100,101,"FLAT"),"SHORT")
        self.assertIsNone(v3_directional_baseline(65,1.3,99,100,101,"DOWN"))
        self.assertIsNone(v3_directional_baseline(70,1.2,99,100,101,"DOWN"))
        self.assertIsNone(v3_directional_baseline(70,1.3,100,100,101,"DOWN"))
        self.assertIsNone(v3_directional_baseline(70,1.3,99,100,101,"UP"))

    def test_missing_or_invalid_baseline_data_is_rejected(self):
        self.assertIsNone(v3_directional_baseline(None,1.5,101,100,99,"UP"))
        self.assertIsNone(v3_directional_baseline(30,None,101,100,99,"UP"))
        self.assertIsNone(v3_directional_baseline(30,0,101,100,99,"UP"))


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

    def test_contract_sizing_respects_tick_lot_and_risk_caps(self):
        contract={"symbol":"BTCUSDT","contract_type":"PERPETUAL","status":"TRADING","base_asset":"BTC",
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":0.1,
          "step_size":0.001,"min_qty":0.001,"min_notional":5.0}
        r=contract_sized_risk("LONG",100.04,98.54,contract)
        self.assertTrue(r["valid"])
        self.assertEqual(round(r["entry"]*10)%1,0)
        self.assertAlmostEqual(r["quantity_base"]/0.001,round(r["quantity_base"]/0.001))
        self.assertLessEqual(r["planned_loss_usd"],4.0)
        self.assertLessEqual(r["required_leverage"],5.0)
        self.assertGreaterEqual(r["reward_to_risk"],2.0)
        self.assertTrue(r["contract_spec_verified"])

    def test_rounded_levels_reject_long_setup_below_two_to_one_rr(self):
        contract={"symbol":"TESTUSDT","contract_type":"PERPETUAL","status":"TRADING","base_asset":"TEST",
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":1.0,
          "step_size":0.001,"min_qty":0.001,"min_notional":0.0,"max_leverage":5.0}
        r=contract_sized_risk("LONG",100.6,99.6,contract)
        self.assertFalse(r["valid"])
        self.assertEqual(r["reason"],"tick_rounded_reward_to_risk_below_2")
        self.assertAlmostEqual(r["reward_to_risk"],1.0)

    def test_rounded_levels_reject_short_setup_below_two_to_one_rr(self):
        contract={"symbol":"TESTUSDT","contract_type":"PERPETUAL","status":"TRADING","base_asset":"TEST",
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":1.0,
          "step_size":0.001,"min_qty":0.001,"min_notional":0.0,"max_leverage":5.0}
        r=contract_sized_risk("SHORT",100.4,101.4,contract)
        self.assertFalse(r["valid"])
        self.assertEqual(r["reason"],"tick_rounded_reward_to_risk_below_2")
        self.assertAlmostEqual(r["reward_to_risk"],1.0)

    def test_tick_rounding_cannot_push_stop_outside_allowed_range(self):
        contract={"symbol":"BTCUSDT","contract_type":"PERPETUAL","status":"TRADING","base_asset":"BTC",
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":1.0,
          "step_size":0.001,"min_qty":0.001,"min_notional":0.0,"max_leverage":5.0}
        r=contract_sized_risk("LONG",100.51,97.52,contract)
        self.assertFalse(r["valid"])
        self.assertEqual(r["reason"],"rounded_stop_distance_out_of_range")
        self.assertLessEqual(r["stop_pct"],3.0)
        self.assertGreater(r["rounded_stop_pct"],3.0)

    def test_contract_sizing_rejects_below_minimum_quantity(self):
        contract={"symbol":"DUSTUSDT","contract_type":"PERPETUAL","status":"TRADING","base_asset":"DUST",
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":0.0001,
          "step_size":1000.0,"min_qty":1000.0,"min_notional":5.0}
        r=contract_sized_risk("LONG",1.0,0.99,contract)
        self.assertFalse(r["valid"])
        self.assertEqual(r["reason"],"minimum_contract_quantity_not_met")

class FakeTraderSpyProvider:
    calls=0
    provider_name='Fake TraderSpy Provider'
    def __init__(self,now,stale=False):
        self.now=now;self.stale=stale
    def discover(self):
        return [{"id":"bitcoin","symbol":"BTC","name":"Bitcoin","volume":1000000,"market_cap_rank":1,"current_price":100.0,"market_cap":10000000}]
    def tracked_symbols(self):return {"BTCUSDT"}
    def contract_specs(self,symbols):
        return {"BTCUSDT":{"symbol":"BTCUSDT","pair":"BTCUSDT","contract_type":"PERPETUAL","status":"TRADING",
          "base_asset":"BTC","quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset",
          "tick_size":0.01,"step_size":0.001,"min_qty":0.001,"min_notional":5.0}}
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

class OutcomeProvider:
    calls=0
    provider_name='Test Outcome Provider'
    def __init__(self,now,mode="tp3"):self.now=now;self.mode=mode
    def candles(self,symbol,tf,limit):
        iv=INTERVALS[tf];last=(self.now//iv)*iv-iv;first=last-(219*iv);out=[]
        for i in range(220):
            ot=first+i*iv;op=100.0;hi=101.0;lo=99.0;cl=100.0
            if tf=="1h" and self.mode=="tp3":
                if i==217:hi=103.5;cl=103.2
                if i==218:hi=105.0;cl=104.0
                if i==219:hi=107.0;cl=106.0
            out.append(Candle(ot,op,hi,lo,cl,10,ot+iv-1,True))
        return out
    def close(self):pass

class V5OutcomeTests(unittest.TestCase):
    def test_paper_outcome_progresses_through_tp1_tp2_to_tp3(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=int(time.time()*1000)
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"outcomes.db")
        try:
            store.init_db();iv=INTERVALS["1h"];last=(now//iv)*iv-iv;first=last-219*iv;entry_ts=first+217*iv
            result={"scan_id":"tp-progression","scanned_at":"2026-11-06T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"Test Outcome Provider"},"actionable":[{"symbol":"BTCUSDT","direction":"LONG","decision":"BUY_NOW","entry":100.0,
                "stop_loss":98.5,"take_profit":103.0,"take_profit_2":104.5,"take_profit_3":106.0,
                "entry_observed_at_ms":entry_ts,"expires_at_ms":now+24*60*60_000,"confidence_v5":75,
                "data_grade":"B","primary_timeframe":"1h","stop_pct":1.5,
                "risk":{"planned_loss_usd":4.0,"reward_to_risk":2.0}}],
              "conditional":[]}
            save_scan(result)
            out=evaluate_outcomes_with_provider(OutcomeProvider(now))
            with store.db_connection() as db:row=db.execute("SELECT outcome,realized_r FROM signal_records WHERE scan_id='tp-progression'").fetchone()
            self.assertEqual(row["outcome"],"TP3");self.assertEqual(row["realized_r"],4.0)
            self.assertEqual(performance()["tp3_count"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

    def test_triggered_conditional_recalculates_venue_contract_risk(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=int(time.time()*1000)
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"conditional-trigger.db")
        try:
            store.init_db();iv=INTERVALS["15m"];last=(now//iv)*iv-iv;first=last-219*iv
            result={"scan_id":"conditional-trigger","scanned_at":datetime.fromtimestamp(now/1000,tz=timezone.utc).isoformat(),
              "strategy_version":"V5_STRICT_V3_BASELINE",
              "source_status":{"futures_ohlcv":"OKX public market-data API"},
              "actionable":[],"conditional":[{
                "symbol":"BTCUSDT","direction":"LONG","decision":"CONDITIONAL_BUY","entry":100.0,
                "stop_loss":99.0,"take_profit":102.0,"entry_observed_at_ms":first+200*iv,
                "expires_at_ms":now+24*60*60_000,"confidence_v5":65,"data_grade":"B",
                "primary_timeframe":"1h","stop_pct":1.0,
                "entry_quality":{"trigger_level":100.5,"confirmation_required":"15m close above trigger"},
                "risk":{"valid":True,"planned_loss_usd":4.0,"reward_to_risk":2.0}
              }]}
            save_scan(result)
            provider=ConditionalOutcomeProvider(now)
            out=evaluate_outcomes_with_provider(provider)
            with store.db_connection() as db:
                row=db.execute("SELECT outcome,data_json FROM signal_records WHERE scan_id='conditional-trigger'").fetchone()
            saved=json.loads(row["data_json"])
            self.assertEqual(out["newly_triggered"],1)
            self.assertEqual(row["outcome"],"OPEN")
            self.assertTrue(saved["risk"]["contract_spec_verified"])
            self.assertAlmostEqual(saved["stop_pct"],abs(saved["entry"]-saved["stop_loss"])/saved["entry"]*100)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

    def test_conditional_signal_expires_as_no_valid_entry(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=int(time.time()*1000)
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"watch.db")
        try:
            store.init_db()
            result={"scan_id":"no-entry","scanned_at":"2026-11-06T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"Fake TraderSpy Provider"},"actionable":[],"conditional":[{"symbol":"BTCUSDT","direction":"LONG","decision":"CONDITIONAL_BUY",
                "entry":100.0,"stop_loss":98.5,"take_profit":103.0,"entry_observed_at_ms":now-100_000,
                "expires_at_ms":now-1,"confidence_v5":65,"data_grade":"B","primary_timeframe":"1h",
                "entry_quality":{"trigger_level":200.0,"confirmation_required":"15m close above trigger"},
                "risk":{"planned_loss_usd":4.0,"reward_to_risk":2.0}}]}
            save_scan(result)
            out=evaluate_outcomes_with_provider(FakeTraderSpyProvider(now))
            with store.db_connection() as db:row=db.execute("SELECT outcome FROM signal_records WHERE scan_id='no-entry'").fetchone()
            self.assertEqual(row["outcome"],"NO_VALID_ENTRY")
            self.assertEqual(out["no_valid_entry"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

class ConditionalOutcomeProvider:
    provider_name="OKX public market-data API"
    def __init__(self,now):self.now=now
    def contract_specs(self,symbols):
        return {"BTCUSDT":{"symbol":"BTCUSDT","venue_symbol":"BTC-USDT-SWAP","contract_type":"PERPETUAL",
          "status":"TRADING","base_asset":"BTC","quote_asset":"USDT","margin_asset":"USDT",
          "quantity_unit":"base_asset","tick_size":0.1,"step_size":0.001,"min_qty":0.001,
          "min_notional":5.0,"max_leverage":5.0,"source":"OKX public instruments API"}}
    def candles(self,symbol,tf,limit):
        iv=INTERVALS[tf];last=(self.now//iv)*iv-iv;first=last-(219*iv);out=[]
        for i in range(220):
            ot=first+i*iv;close=101.0 if i>=205 else 100.0
            out.append(Candle(ot,close,close+0.2,close-0.2,close,10,ot+iv-1,True))
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

class V5FundingNormalizationTests(unittest.TestCase):
    def test_funding_rate_normalizes_different_intervals_to_8h(self):
        from app.signals import funding_rate_per_8h
        self.assertAlmostEqual(funding_rate_per_8h(0.0002, 4), (1.0002)**2-1)
        self.assertAlmostEqual(funding_rate_per_8h(0.0004, 16), (1.0004)**0.5-1)
        self.assertAlmostEqual(funding_rate_per_8h(-0.0002, 4), (1.0-0.0002)**2-1)

    def test_funding_normalization_rejects_invalid_interval_or_rate(self):
        from app.signals import funding_rate_per_8h, DataError
        for rate, interval in ((0.001, 0), (float("nan"), 8), (float("inf"), 8), (-1.0, 8)):
            with self.assertRaises(DataError):
                funding_rate_per_8h(rate, interval)


class V5ScoringAndStorageTests(unittest.TestCase):
    def test_prior_day_and_week_levels_use_4h_bar_coverage(self):
        candles=[]
        for i in range(220):
            ts=i*4*3_600_000
            candles.append(Candle(ts,100,101,99,100,100,ts+4*3_600_000-1,True))
        structure=_structure(candles,"LONG",2.0)
        kinds={x["type"] for x in structure["liquidity_levels"]}
        self.assertIn("PREVIOUS_DAY_HIGH",kinds)
        self.assertIn("PREVIOUS_DAY_LOW",kinds)
        self.assertIn("PREVIOUS_WEEK_HIGH",kinds)
        self.assertIn("PREVIOUS_WEEK_LOW",kinds)

    def test_market_regime_classifier_covers_v5_regimes(self):
        def candle(i,o,h,l,cl):
            ts=i*3_600_000
            return Candle(ts,o,h,l,cl,100,ts+3_599_999,True)
        base=[candle(i,100,101,99,100) for i in range(30)]
        self.assertEqual(classify_market_regime(base,25,"NORMAL","UP",1.0),"TRENDING")
        self.assertEqual(classify_market_regime(base,15,"NORMAL","FLAT",1.0),"RANGING")
        self.assertEqual(classify_market_regime(base,25,"HIGH","FLAT",1.0),"HIGH_VOLATILITY")
        self.assertEqual(classify_market_regime(base,15,"LOW","FLAT",1.0),"LOW_VOLATILITY")
        breakout=base[:-1]+[candle(29,100,103,100,102)]
        self.assertEqual(classify_market_regime(breakout,25,"NORMAL","UP",2.0),"BREAKOUT")
        unstable=base[:-1]+[candle(29,100,110,90,105)]
        self.assertEqual(classify_market_regime(unstable,25,"HIGH","UP",2.0),"UNSTABLE")

    def test_fvg_uses_three_candle_zone_and_records_mitigation(self):
        def candle(i,o,h,l,cl):
            ts=i*3_600_000
            return Candle(ts,o,h,l,cl,100,ts+3_599_999,True)
        candles=[candle(i,100,101,99,100) for i in range(8)]
        candles.extend([
            candle(8,100,101,99,100),
            candle(9,100,103,100,102),
            candle(10,103,104,102,103),
            candle(11,103,104,101.5,103),
        ])
        zone=_find_fvg(candles,"LONG")
        self.assertEqual(zone["direction"],"BULLISH")
        self.assertEqual(zone["lower"],101.0)
        self.assertEqual(zone["upper"],102.0)
        self.assertEqual(zone["status"],"PARTIALLY_MITIGATED")
        candles.append(candle(12,103,104,100.5,101))
        fully=_find_fvg(candles,"LONG")
        self.assertEqual(fully["status"],"MITIGATED")

    def test_order_block_requires_displacement_and_records_zone_state(self):
        def candle(i,o,h,l,cl):
            ts=i*3_600_000
            return Candle(ts,o,h,l,cl,100,ts+3_599_999,True)
        candles=[candle(i,100,101,99,100) for i in range(12)]
        candles[5]=candle(5,100,102,99,101)
        candles[8]=candle(8,102,103,100,101)
        candles[9]=candle(9,102,103,102.5,102.8)
        candles[10]=candle(10,102,106,101.5,106)
        candles[11]=candle(11,104,104.5,102.5,103)
        block=_find_order_block(candles,"LONG",2.0)
        self.assertEqual(block["type"],"BULLISH")
        self.assertEqual(block["lower"],100.0)
        self.assertEqual(block["upper"],103.0)
        self.assertEqual(block["status"],"PARTIALLY_MITIGATED")
        self.assertEqual(block["originating_candle_time_ms"],8*3_600_000)
        self.assertGreaterEqual(block["displacement_atr"],0.5)

    def test_smart_money_points_require_fresh_trader_and_position_snapshots(self):
        now=1_800_000_000_000
        smart={"positions":[{"symbol":"BTCUSDT","side":"LONG","traderId":"trader-1"}],
          "traders":[{"traderId":"trader-1","smartScore":90}],
          "positions_observed_at_ms":now-60_000,"traders_observed_at_ms":now-60_000}
        self.assertEqual(FuturesSignalEngine._smart_score("BTCUSDT","LONG",None,smart,now),1)
        smart["traders_observed_at_ms"]=now-20*60_000
        self.assertEqual(FuturesSignalEngine._smart_score("BTCUSDT","LONG",None,smart,now),0)

    def test_zero_funding_value_does_not_fail_boolean_audit(self):
        self.assertTrue(_audit_checks_passed({"baseline":True,"funding_rate_8h_equivalent":0.0,"risk":True}))
        self.assertFalse(_audit_checks_passed({"baseline":True,"funding_rate_8h_equivalent":0.0,"risk":False}))

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

    def test_status_exposes_only_provider_key_presence_not_secret(self):
        old=os.environ.get("TRADERSPY_API_KEY");old_db=os.environ.get("CONTROL_DB_PATH");old_provider=os.environ.get("V5_DATA_PROVIDER")
        tmp=tempfile.TemporaryDirectory();os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"status.db")
        try:
            os.environ["V5_DATA_PROVIDER"]="traderspy"
            os.environ["TRADERSPY_API_KEY"]="tspy_private_test_value"
            status=get_signal_status()
            self.assertTrue(status["api_key_configured"])
            self.assertFalse(status["live_rest_access_verified"])
            self.assertNotIn("tspy_private_test_value",str(status))
            self.assertFalse(status["exchange_account_connection"])
            self.assertFalse(status["order_execution_enabled"])
        finally:
            if old is None:os.environ.pop("TRADERSPY_API_KEY",None)
            else:os.environ["TRADERSPY_API_KEY"]=old
            if old_db is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old_db
            if old_provider is None:os.environ.pop("V5_DATA_PROVIDER",None)
            else:os.environ["V5_DATA_PROVIDER"]=old_provider
            tmp.cleanup()

    def test_persistent_daily_provider_budget_guard(self):
        old=os.environ.get("CONTROL_DB_PATH");tmp=tempfile.TemporaryDirectory()
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"budget.db")
        try:
            self.assertEqual(reserve_traderspy_api_call(1),1)
            self.assertEqual(traderspy_daily_usage(),1)
            with self.assertRaises(DataError):reserve_traderspy_api_call(1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

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
            self.assertEqual(performance()["published_signals"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()


class V5ProviderSourceRoutingTests(unittest.TestCase):
    def test_only_known_public_provider_sources_are_routable(self):
        self.assertEqual(provider_key_for_source("OKX public market-data API"),"okx")
        self.assertEqual(provider_key_for_source("Toobit public USDT-M linear perpetual market data"),"toobit")
        self.assertEqual(provider_key_for_source("TraderSpy read-only market-data API"),"traderspy")
        self.assertIsNone(provider_key_for_source("unknown or missing provider"))


class V5ProviderAttributionTests(unittest.TestCase):
    def test_performance_attributes_each_signal_to_its_originating_provider(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH")
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"multi-provider.db")
        try:
            store.init_db()
            save_scan({"scan_id":"legacy-toobit-signal","scanned_at":"2026-11-06T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"Toobit public USDT-M linear perpetual market data"},
              "actionable":[{"symbol":"BTCUSDT","direction":"LONG","decision":"BUY_NOW","entry":100.0,
                "stop_loss":98.5,"take_profit":103.0,"entry_observed_at_ms":1000,"confidence_v5":75,
                "data_grade":"B","risk":{"planned_loss_usd":4.0}}],"conditional":[]})
            save_scan({"scan_id":"latest-okx-empty","scanned_at":"2026-11-07T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"OKX public market-data API"},"actionable":[],"conditional":[]})
            report=performance()
            self.assertIn("Toobit public USDT-M linear perpetual market data",report["outcome_source"])
            self.assertNotIn("OKX public market-data API",report["outcome_source"])
            self.assertEqual(report["outcome_providers"],["Toobit public USDT-M linear perpetual market data"])
            self.assertEqual(report["by_provider"]["Toobit public USDT-M linear perpetual market data"]["published"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

    def test_performance_does_not_mix_legacy_strategy_signals_into_active_v5(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH")
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"strategy-version.db")
        try:
            store.init_db()
            save_scan({"scan_id":"legacy-relaxed-signal","scanned_at":"2026-11-06T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"Toobit public USDT-M linear perpetual market data"},
              "actionable":[{"symbol":"BTCUSDT","direction":"SHORT","decision":"SELL_NOW","entry":100.0,
                "stop_loss":101.5,"take_profit":97.0,"entry_observed_at_ms":1000,"confidence_v5":75,
                "data_grade":"B","risk":{"planned_loss_usd":4.0}}],"conditional":[]})
            save_scan({"scan_id":"strict-v5-current","scanned_at":"2026-11-07T00:00:00+00:00",
              "strategy_version":"V5_STRICT_V3_BASELINE",
              "source_status":{"futures_ohlcv":"OKX public market-data API"},"actionable":[],"conditional":[]})
            report=performance()
            self.assertEqual(report["strategy_version"],"V5_STRICT_V3_BASELINE")
            self.assertEqual(report["published_signals"],0)
            self.assertEqual(report["historical_published_signals"],1)
            self.assertEqual(report["legacy_signals"],1)
            self.assertEqual(report["legacy_open_count"],1)
            self.assertEqual(report["outcome_source"],"OKX public market-data API OHLCV; no exchange fills are observed")
            self.assertEqual(report["by_strategy"]["LEGACY_UNVERSIONED"]["published"],1)
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

    def test_performance_uses_actual_latest_futures_provider(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH")
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"provider.db")
        try:
            store.init_db()
            result={"scan_id":"provider-attribution","scanned_at":"2026-11-07T00:00:00+00:00",
              "source_status":{"futures_ohlcv":"OKX public market-data API"},"actionable":[],"conditional":[]}
            save_scan(result)
            report=performance()
            self.assertIn("OKX public market-data API",report["outcome_source"])
            self.assertNotIn("TraderSpy",report["outcome_source"])
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

class WideUniverseProvider:
    calls=0
    def __init__(self,now):self.now=now
    def discover(self):
        return [{"id":f"asset-{i}","symbol":f"COIN{i}","name":f"Coin {i}","volume":1000000-i,
          "market_cap_rank":i+1,"current_price":10.0,"market_cap":10000000-i} for i in range(120)]
    def tracked_symbols(self):return {f"COIN{i}USDT" for i in range(120)}
    def contract_specs(self,symbols):
        return {x:{"symbol":x,"contract_type":"PERPETUAL","status":"TRADING","base_asset":x[:-4],
          "quote_asset":"USDT","margin_asset":"USDT","quantity_unit":"base_asset","tick_size":0.01,
          "step_size":0.001,"min_qty":0.001,"min_notional":5.0} for x in symbols}
    def prices(self,symbols):
        return {x:{"symbol":x,"price":10.0,"updatedAt":self.now} for x in symbols}
    def derivatives(self,symbols):
        return {x:{"symbol":x,"updatedAt":self.now,"openInterest":{"valueUsd":1000000}}
          for x in symbols}
    def smart_money(self):return {}
    def candles(self,symbol,tf,limit):return []
    def close(self):pass

class V5ExpandedUniverseTests(unittest.TestCase):
    def test_extended_scan_checks_up_to_one_hundred_eligible_assets(self):
        tmp=tempfile.TemporaryDirectory();old=os.environ.get("CONTROL_DB_PATH");now=int(time.time()*1000)
        os.environ["CONTROL_DB_PATH"]=str(Path(tmp.name)/"universe.db")
        try:
            store.init_db()
            engine=FuturesSignalEngine(provider=WideUniverseProvider(now),clock=lambda:now)
            engine.evaluate=lambda coin,symbol,*args:{"symbol":symbol,"decision":"REJECT","confidence_v5":0,"data_grade":"B"}
            result=engine.scan(extended=True)
            self.assertEqual(result["eligible_assets"],120)
            self.assertEqual(result["selected_assets"],100)
            self.assertEqual(result["screened_assets"],100)
            self.assertFalse(result["extended_partial"])
        finally:
            if old is None:os.environ.pop("CONTROL_DB_PATH",None)
            else:os.environ["CONTROL_DB_PATH"]=old
            tmp.cleanup()

if __name__=="__main__":unittest.main()
