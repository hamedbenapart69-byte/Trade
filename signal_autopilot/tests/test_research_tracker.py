"""آزمون‌های Outcome Tracker؛ داده‌های این فایل فقط fixture تست‌اند."""
import sys, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import tempfile
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modules.research_tracker as research_tracker_module
from modules.research_tracker import INTERVAL_MS, PRODUCTION_MODE_THRESHOLD as TRACKER_PRODUCTION_THRESHOLD, RESEARCH_MODE_THRESHOLD as TRACKER_RESEARCH_THRESHOLD, _pnl_pct, update_one, update_outcomes, fetch_public_ohlcv
from modules.lrt15m_engine import PRODUCTION_MODE_THRESHOLD, RESEARCH_MODE_THRESHOLD

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
    def test_public_fetcher_returns_empty_for_not_yet_closed_entry_candle(self):
        class EmptyExchange:
            markets = {
                "BTC/USDT:USDT": {
                    "active": True, "swap": True, "linear": True,
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "symbol": "BTC/USDT:USDT",
                }
            }

            def load_markets(self):
                return self.markets

            def fetch_ohlcv(self, *args, **kwargs):
                return []

            def close(self):
                return None

        since = CANDLE_OPEN + INTERVAL_MS
        now_ms = since + 60_000
        exchange = EmptyExchange()
        with patch.object(research_tracker_module, "PROVIDERS", ("okx",)), \
             patch.object(research_tracker_module.ccxt, "okx", return_value=exchange):
            rows, source = fetch_public_ohlcv("BTCUSDT", since, now_ms, 200)
        self.assertEqual(rows, [])
        self.assertEqual(source, "PUBLIC_OHLCV_NO_CLOSED_CANDLES")

    def test_empty_provider_does_not_hide_failure_of_other_providers(self):
        class EmptyExchange:
            markets = {
                "BTC/USDT:USDT": {
                    "active": True, "swap": True, "linear": True,
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "symbol": "BTC/USDT:USDT",
                }
            }

            def load_markets(self):
                return self.markets

            def fetch_ohlcv(self, *args, **kwargs):
                return []

            def close(self):
                return None

        since = CANDLE_OPEN + INTERVAL_MS
        now_ms = since + 2 * INTERVAL_MS
        with (
            patch.object(research_tracker_module, "PROVIDERS", ("okx", "bybit")),
            patch.object(research_tracker_module.ccxt, "okx", return_value=EmptyExchange()),
            patch.object(research_tracker_module.ccxt, "bybit", side_effect=RuntimeError("network down")),
        ):
            with self.assertRaisesRegex(RuntimeError, "PUBLIC_OHLCV_UNAVAILABLE"):
                fetch_public_ohlcv("BTCUSDT", since, now_ms, 200)

    def test_research_outcome_history_cannot_shrink_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signals_path = root / "signals.json"
            outcomes_path = root / "outcomes.json"
            signals_path.write_text(json.dumps({"signals": []}), encoding="utf-8")
            outcomes_path.write_text(json.dumps({"outcomes": [{"signal_id": "historical-1"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "RESEARCH_SIGNAL_HISTORY_REGRESSION"):
                update_outcomes(
                    signals_path, outcomes_path,
                    now=NOW, fetcher=lambda *args: ([], "UNUSED"),
                )

    def test_research_outcome_rejects_duplicate_source_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signals_path = root / "signals.json"
            outcomes_path = root / "outcomes.json"
            row = signal()
            signals_path.write_text(json.dumps({"signals": [row, row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DUPLICATE_RESEARCH_SIGNAL_ID"):
                update_outcomes(signals_path, outcomes_path, now=NOW)

    def test_research_outcome_requires_timezone_aware_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            signals_path = root / "signals.json"
            outcomes_path = root / "outcomes.json"
            signals_path.write_text(json.dumps({"signals": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "TRACKER_NOW_TIMEZONE_REQUIRED"):
                update_outcomes(signals_path, outcomes_path, now=datetime(2026, 11, 13, 20, 0))

    def test_public_fetcher_rejects_nonfinite_and_malformed_ohlcv(self):
        class FakeExchange:
            markets = {
                "BTC/USDT:USDT": {
                    "active": True, "swap": True, "linear": True,
                    "base": "BTC", "quote": "USDT", "settle": "USDT",
                    "symbol": "BTC/USDT:USDT",
                }
            }

            def __init__(self, raw):
                self.raw = raw

            def load_markets(self):
                return self.markets

            def fetch_ohlcv(self, *args, **kwargs):
                return [self.raw]

            def close(self):
                return None

        since = CANDLE_OPEN + INTERVAL_MS
        now_ms = since + 2 * INTERVAL_MS
        invalid_rows = [
            [since, 100.0, float("nan"), 99.0, 100.0, 1.0],
            [since, 100.0, 99.0, 98.0, 101.0, 1.0],
            [since, 100.0, 102.0, 99.0, 101.0, -1.0],
            [since + 1, 100.0, 102.0, 99.0, 101.0, 1.0],
        ]
        for raw in invalid_rows:
            with self.subTest(raw=raw):
                exchange = FakeExchange(raw)
                with patch.object(research_tracker_module, "PROVIDERS", ("okx",)), \
                     patch.object(research_tracker_module.ccxt, "okx", return_value=exchange):
                    with self.assertRaisesRegex(RuntimeError, "INVALID_"):
                        fetch_public_ohlcv("BTCUSDT", since, now_ms, 200)

    def test_public_fetcher_fallback_chain_includes_binance(self):
        self.assertEqual(
            research_tracker_module.PROVIDERS,
            ("okx", "bybit", "binanceusdm", "kucoinfutures", "mexc", "bitget"),
        )

    def test_tracker_thresholds_match_engine_contract(self):
        self.assertEqual(TRACKER_PRODUCTION_THRESHOLD, PRODUCTION_MODE_THRESHOLD)
        self.assertEqual(TRACKER_RESEARCH_THRESHOLD, RESEARCH_MODE_THRESHOLD)
        self.assertEqual(TRACKER_PRODUCTION_THRESHOLD, 80)
        self.assertEqual(TRACKER_RESEARCH_THRESHOLD, 60)

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

    def test_gap_at_entry_keeps_signal_pending_without_fabricating_a_fill(self):
        def gap_fetcher(*args):
            raise RuntimeError("PUBLIC_OHLCV_UNAVAILABLE|okx:CANDLE_GAP_DETECTED")
        r=update_one(signal(),None,gap_fetcher,NOW)
        self.assertEqual(r["status"],"ENTRY_PENDING_DATA")
        self.assertIsNone(r["entry_actual"])
        self.assertEqual(r["entry_fill_status"],"PENDING")
        self.assertIn("CANDLE_GAP_DETECTED",r["last_error"])

    def test_later_candle_without_expected_entry_candle_stays_pending(self):
        later_open=CANDLE_OPEN+2*INTERVAL_MS
        rows=[candle(later_open,101,101.2,100.5,100.8)]
        r=update_one(signal(),None,fetcher_for(rows),NOW)
        self.assertEqual(r["status"],"ENTRY_PENDING_DATA")
        self.assertIsNone(r["entry_actual"])
        self.assertEqual(r["last_error"],"EXPECTED_ENTRY_CANDLE_MISSING_GAP_DETECTED")

    def test_all_providers_unavailable(self):
        def fail(*args): raise RuntimeError("providers unavailable")
        r=update_one(signal(),None,fail,NOW)
        self.assertEqual(r["status"],"DATA_UNAVAILABLE")
        self.assertIsNone(r["entry_actual"])
        self.assertEqual(r["fee_pct"],"UNAVAILABLE")

    def test_raw_pnl_buy_and_sell(self):
        self.assertAlmostEqual(_pnl_pct("SELL",100,98),2)
        self.assertAlmostEqual(_pnl_pct("BUY",100,102),2)

    def test_gap_through_stop_after_entry_uses_open(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        rows=[candle(ts,101,101.2,100.5,100.8),
              candle(ts+INTERVAL_MS,103,104,102.5,103.5)]
        r=update_one(signal(),None,fetcher_for(rows),NOW)
        self.assertEqual(r["status"],"SL_HIT")
        self.assertEqual(r["exit_price"],103)

    def test_target_already_passed_at_entry_is_not_a_win(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        r=update_one(signal(),None,fetcher_for([candle(ts,95,95.5,94.5,95.2)]),NOW)
        self.assertEqual(r["status"],"ENTRY_INVALIDATED_GAP")
        self.assertEqual(r["entry_fill_status"],"NOT_FILLED")
        self.assertEqual(r["entry_invalidation_reason"],"TARGET_ALREADY_PASSED_BEFORE_ENTRY")
        self.assertIsNone(r["pnl_pct_raw"])
        self.assertIsNone(r["rr_actual"])

    def test_old_tp_at_entry_gap_is_reclassified_as_missed_entry(self):
        ts=CANDLE_OPEN+INTERVAL_MS
        old={
            "signal_id":"signal-001","status":"TP_HIT","entry_actual":95.0,
            "entry_time_utc":"2026-11-13T19:15:00+00:00",
            "entry_candle_ohlc":{"open_time":ts,"open":95.0,"high":95.5,"low":94.5,"close":95.2},
            "exit_candle_ohlc":{"open_time":ts,"open":95.0,"high":95.5,"low":94.5,"close":95.2},
            "exit_price":95.0,"pnl_pct_raw":0.0,"history":[{"status":"TP_HIT"}],
        }
        r=update_one(signal(),old,fetcher_for([candle(ts,95,95.5,94.5,95.2)]),NOW)
        self.assertEqual(r["status"],"ENTRY_INVALIDATED_GAP")
        self.assertEqual(r["invalidated_prior_outcome"]["status"],"TP_HIT")
        self.assertEqual(r["entry_fill_status"],"NOT_FILLED")

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
