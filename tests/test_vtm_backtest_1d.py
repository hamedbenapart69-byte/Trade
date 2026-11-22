from __future__ import annotations
import unittest
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import run_vtm_backtest_1d as vtm

class VTMTests(unittest.TestCase):
    def test_frozen_parameters(self):
        self.assertEqual(vtm.MULTIPLIERS,(1.8,2.0,2.2))
        self.assertEqual(vtm.MAX_HOLD,10)
        self.assertEqual(vtm.TARGET_VOL,0.10)
    def test_universe_requires_30_complete_prior_days(self):
        d=vtm.date(2023,1,31)
        rows={d-vtm.timedelta(days=i):(1,2,0.5,1.5,11_000_000) for i in range(1,31)}
        rows[d]=(1,2,0.5,1.5,0)
        u,c=vtm.make_universe({"TESTUSDT":rows})
        self.assertIn("TESTUSDT",u[d])
        del rows[d-vtm.timedelta(days=7)]
        u,_=vtm.make_universe({"TESTUSDT":rows})
        self.assertNotIn("TESTUSDT",u[d])
    def test_stats_no_trade_is_explicit(self):
        x=vtm.stats([(vtm.date(2023,1,1),0.0)],[])
        self.assertIsNone(x["win_rate"])
        self.assertEqual(x["total_trades"],0)

if __name__=="__main__":unittest.main()
