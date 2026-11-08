import unittest
from types import SimpleNamespace
from app.adaptive import adaptive_setup
from app.signals import _conditional_trigger_hit


def bars(count, high=105.0, low=95.0, close=100.0, interval=3_600_000):
    out=[]
    for i in range(count):
        c=close
        out.append(SimpleNamespace(open_time=i*interval, open=c-0.1, high=high, low=low,
          close=c, volume=100.0, close_time=(i+1)*interval-1))
    return out


class AdaptiveSetupTests(unittest.TestCase):
    def setUp(self):
        self.h1=bars(40)
        self.m15=bars(40,high=103.2,low=101.8,close=102.8,interval=900_000)
        self.tech={
          "close":103.0,"ema20":102.0,"ema50":101.0,"rsi":55.0,"volume_ratio":1.0,
          "adx":22.0,"macd_histogram":0.8,"macd_histogram_previous":0.5,
          "obv_change_10":120.0,"mfi":60.0,"atr14":2.0,"bb_position":"upper_half"
        }
        self.trends={"1d":"BULLISH","4h":"UP","1h":"UP"}
        self.long={"classification":"BULLISH","liquidity_sweep_aligned":False,
          "fvg_aligned":False,"order_block_aligned":False}
        self.short={"classification":"BEARISH","liquidity_sweep_aligned":False,
          "fvg_aligned":False,"order_block_aligned":False}

    def test_trend_pullback_is_found_without_v3_oversold_gate(self):
        result=adaptive_setup(self.h1,self.m15,self.tech,self.trends,"TRENDING",
          self.long,self.short,102.0,0.5,0.0001)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"],"LONG")
        self.assertEqual(result["strategy_family"],"TREND_PULLBACK")
        self.assertGreaterEqual(result["strategy_score"],52)

    def test_opposed_higher_timeframes_do_not_create_trend_signal(self):
        result=adaptive_setup(self.h1,self.m15,self.tech,
          {"1d":"BEARISH","4h":"DOWN","1h":"DOWN"},"TRENDING",
          self.long,self.short,102.0,0.5,0.0001)
        self.assertIsNone(result)

    def test_short_trend_pullback_uses_short_momentum_and_flow(self):
        tech={**self.tech,"close":97.0,"ema20":98.0,"ema50":99.0,"rsi":45.0,
          "macd_histogram":-0.8,"macd_histogram_previous":-0.5,
          "obv_change_10":-120.0,"mfi":40.0,"bb_position":"lower_half"}
        result=adaptive_setup(self.h1,self.m15,tech,
          {"1d":"BEARISH","4h":"DOWN","1h":"DOWN"},"TRENDING",
          self.long,self.short,98.0,0.5,0.0001)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"],"SHORT")
        self.assertEqual(result["strategy_family"],"TREND_PULLBACK")

    def test_oversold_aligned_short_stays_conditional_until_reset_and_retest(self):
        tech={**self.tech,"close":97.0,"ema20":98.0,"ema50":99.0,"rsi":30.0,
          "macd_histogram":-0.8,"macd_histogram_previous":-0.5,
          "obv_change_10":-120.0,"mfi":40.0,"atr14":0.7}
        result=adaptive_setup(self.h1,self.m15,tech,
          {"1d":"BEARISH","4h":"DOWN","1h":"DOWN"},"TRENDING",
          self.long,self.short,98.0,0.5,0.0001)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"],"SHORT")
        self.assertEqual(result["strategy_family"],"TREND_PULLBACK")
        self.assertFalse(result["pattern_confirmed"])
        self.assertEqual(result["trigger_mode"],"retest_rejection")
        self.assertIn("RSI to recover",result["confirmation_required"])
        self.assertEqual(result["trigger_level"],98.0)

    def test_confirmed_breakout_is_not_mislabeled_as_a_retest(self):
        h1=list(self.h1)
        h1[-1]=SimpleNamespace(open_time=h1[-1].open_time,open=105.0,high=107.0,low=104.8,
          close=106.0,volume=180.0,close_time=h1[-1].close_time)
        m15=bars(40,high=107.0,low=106.1,close=106.5,interval=900_000)
        tech={**self.tech,"close":106.0,"ema20":105.0,"ema50":104.0,"rsi":62.0,
          "volume_ratio":1.8,"adx":27.0,"macd_histogram":1.0,"macd_histogram_previous":0.6,
          "obv_change_10":200.0,"mfi":65.0}
        result=adaptive_setup(h1,m15,tech,self.trends,"BREAKOUT",
          self.long,self.short,106.0,0.5,0.0001)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"],"LONG")
        self.assertEqual(result["strategy_family"],"BREAKOUT_CONFIRMATION")
        self.assertTrue(result["pattern_confirmed"])

    def test_conditional_short_retest_requires_wick_to_level_and_close_back_below(self):
        self.assertTrue(_conditional_trigger_hit("SHORT",SimpleNamespace(high=101.2,low=99.8,close=99.9),100.0,"retest_rejection"))
        self.assertFalse(_conditional_trigger_hit("SHORT",SimpleNamespace(high=99.9,low=99.1,close=99.4),100.0,"retest_rejection"))
        self.assertFalse(_conditional_trigger_hit("SHORT",SimpleNamespace(high=101.2,low=100.1,close=100.4),100.0,"retest_rejection"))

    def test_conditional_long_retest_requires_wick_to_level_and_close_back_above(self):
        self.assertTrue(_conditional_trigger_hit("LONG",SimpleNamespace(high=101.2,low=99.8,close=100.1),100.0,"retest_rejection"))
        self.assertFalse(_conditional_trigger_hit("LONG",SimpleNamespace(high=99.9,low=99.1,close=99.4),100.0,"retest_rejection"))
        self.assertFalse(_conditional_trigger_hit("LONG",SimpleNamespace(high=101.2,low=100.1,close=100.4),100.0,"retest_rejection"))

    def test_no_pattern_returns_none_instead_of_forced_direction(self):
        tech={**self.tech,"rsi":50.0,"adx":10.0,"volume_ratio":0.4,
          "macd_histogram":0.0,"macd_histogram_previous":0.0,
          "obv_change_10":0.0,"mfi":50.0}
        result=adaptive_setup(self.h1,self.m15,tech,
          {"1d":"NEUTRAL","4h":"FLAT","1h":"FLAT"},"LOW_VOLATILITY",
          self.long,self.short,102.0,0.5,0.0)
        self.assertIsNone(result)


if __name__=="__main__":
    unittest.main()
