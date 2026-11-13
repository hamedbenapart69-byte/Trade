"""آزمون‌های Outcome Tracker؛ داده‌های این فایل فقط fixture تست‌اند."""
import sys, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.research_tracker import INTERVAL_MS, _pnl_pct, update_one

NOW = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
CANDLE_OPEN = int(datetime(2026, 11, 13, 19, 0, tzinfo=timezone.utc).timestamp() * 1000)

def signal(direction="SELL"):
    return {
        "signal_id":"signal-001","symbol":"BTCUSDT","direction":direction,
        "collection_status":"PENDING_OUTCOME_LABEL","created_at_utc":"2026-11-13T19:00:00+00:00",
        "candle_open_time":CANDLE_OPEN,"entry_reference":100.0,
        "stop_reference":102.0 if direction=="SELL" else 98.0,
        "target_reference":96.0 if direction=="SELL" else 104.0,
    }

def candle(ts, op, hi, lo, close):
    return {"open_time":ts,"open":op,"high":hi,"low":lo,"close":close,"volume":1.0}

def fetcher_for(rows, source="OKX_PUBLIC_OHLCV"):
    def fetcher(symbol, since, now_ms, limit):
        assert symbol=="BTCUSDT" and since==CANDLE_OPEN+INTERVAL_MS
        return rows, source
    return fetcher

class ResearchTrackerTests(unittest.TestCase):
    def test_entry_uses_next_candle_open(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,101,101.5,100.5,101.2)]),NOW)
        self.assertEqual(r["entry_reference"],100)
        self.assertEqual(r["entry_actual"],101)
        self.assertEqual(r["entry_contract"],"FIRST_15M_OPEN_STRICTLY_AFTER_SIGNAL_TIMESTAMP")
        self.assertEqual(r["status"],"ACTIVE")

    def test_tp_hit_sell(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,101,101.2,95.5,97)]),NOW)
        self.assertEqual(r["status"],"TP_HIT")
        self.assertEqual(r["exit_price"],96)
        self.assertGreater(r["pnl_pct_raw"],0)

    def test_sl_hit_sell(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,101,102.5,100.5,102.2)]),NOW)
        self.assertEqual(r["status"],"SL_HIT")
        self.assertEqual(r["exit_price"],102)
        self.assertLess(r["pnl_pct_raw"],0)

    def test_both_touched_is_ambiguous(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,101,102.5,95.5,100)]),NOW)
        self.assertEqual(r["status"],"AMBIGUOUS_BOTH_TOUCHED")
        self.assertIsNone(r["exit_price"])
        self.assertIsNone(r["pnl_pct_raw"])

    def test_next_candle_not_closed(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        early=datetime.fromtimestamp((ts+60_000)/1000,timezone.utc)
        r=update_one(signal(),None,fetcher_for([]),early)
        self.assertEqual(r["status"],"ENTRY_PENDING_DATA")

    def test_all_providers_unavailable(self):
        def fail(*args): raise RuntimeError("providers unavailable")
        r=update_one(signal(),None,fail,NOW)
        self.assertEqual(r["status"],"DATA_UNAVAILABLE")
        self.assertIsNone(r["entry_actual"])
        self.assertEqual(r["fee_pct"],"UNAVAILABLE")

    def test_raw_pnl_buy_and_sell(self):
        self.assertAlmostEqual(_pnl_pct("SELL",100,98),2)
        self.assertAlmostEqual(_pnl_pct("BUY",100,102),2)

    def test_gap_through_stop_uses_open(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,103,104,102.5,103.5)]),NOW)
        self.assertEqual(r["status"],"SL_HIT")
        self.assertEqual(r["exit_price"],103)

    def test_wrong_signal_id_rejected(self):
        with self.assertRaisesRegex(ValueError,"signal_id_mismatch"):
            update_one(signal(),{"signal_id":"other","status":"ACTIVE"},fetcher_for([]),NOW)

    def test_terminal_outcome_is_immutable(self):
        old={"signal_id":"signal-001","status":"TP_HIT","entry_actual":101,"history":[{"status":"TP_HIT"}]}
        r=update_one(signal(),old,fetcher_for([]),NOW)
        self.assertEqual(r["status"],"TP_HIT")
        self.assertEqual(len(r["history"]),1)

    def test_rr_recomputed_from_actual_entry(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,101,101.2,100.5,100.8)]),NOW)
        self.assertAlmostEqual(r["rr_actual"],5.0)


    def test_invalidates_entry_that_predates_signal_creation(self):
        s=signal()
        s["created_at_utc"]="2026-11-13T19:20:00+00:00"
        next_open=CANDLE_OPEN+2*INTERVAL_MS
        old={
            "signal_id":"signal-001","status":"TP_HIT","entry_actual":100.0,
            "entry_time_utc":"2026-11-13T19:15:00+00:00","exit_price":96.0,
            "exit_time_utc":"2026-11-13T19:30:00+00:00","pnl_pct_raw":4.0,
            "history":[{"status":"TP_HIT"}],
        }
        def later_fetcher(symbol,since,now_ms,limit):
            self.assertEqual(since,next_open)
            return [candle(next_open,101.0,101.2,100.5,100.8)],"OKX_PUBLIC_OHLCV"
        r=update_one(s,old,later_fetcher,NOW)
        self.assertEqual(r["invalidated_prior_entry"]["reason"],"ENTRY_PRECEDES_SIGNAL_TIMESTAMP")
        self.assertEqual(r["entry_time_utc"],"2026-11-13T19:30:00+00:00")
        self.assertEqual(r["entry_actual"],101.0)
        self.assertEqual(r["status"],"ACTIVE")
        self.assertTrue(any(x.get("reason")=="INVALIDATED_LOOKAHEAD_ENTRY" for x in r["history"]))

    def test_expiry_after_48_hours(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        rows=[candle(ts+i*INTERVAL_MS,101,101.5,100.5,101.1) for i in range(191)]
        late=NOW+timedelta(hours=49)
        r=update_one(signal(),None,fetcher_for(rows),late)
        self.assertEqual(r["status"],"EXPIRED")
        self.assertIsNotNone(r["pnl_pct_raw"])

if __name__=="__main__": unittest.main(verbosity=2)
