import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from logic import hash_market_input
from modules.storage import build_health

ROOT = Path(__file__).resolve().parents[1]


class InputHashTests(unittest.TestCase):
    def test_hash_is_deterministic_across_dictionary_key_order(self):
        left = {"provider": "okx", "symbols": [{"symbol": "BTC/USDT", "last": 100.0}]}
        right = {"symbols": [{"last": 100.0, "symbol": "BTC/USDT"}], "provider": "okx"}
        self.assertEqual(hash_market_input(left), hash_market_input(right))
        self.assertRegex(hash_market_input(left), r"^[0-9a-f]{64}$")

    def test_hash_changes_when_raw_market_input_changes(self):
        first = {"provider": "okx", "symbols": [{"symbol": "BTC/USDT", "last": 100.0}]}
        second = {"provider": "okx", "symbols": [{"symbol": "BTC/USDT", "last": 101.0}]}
        self.assertNotEqual(hash_market_input(first), hash_market_input(second))


class HealthSnapshotTests(unittest.TestCase):
    def test_health_contains_hash_coverage_and_manual_only_contract(self):
        digest = "a" * 64
        health = build_health({
            "generated_at_utc": "2026-11-10T10:00:00+00:00",
            "pipeline_status": "DEGRADED",
            "provider": "okx",
            "engine": "EMA20_EMA50_ATR14_MVP",
            "input_hash": digest,
            "quality": {
                "symbols_requested": 100,
                "symbols_processed": 42,
                "symbols_unscanned": 58,
                "coverage_pct": 42.0,
                "coverage_status": "PARTIAL",
            },
            "data_errors": {"bybit": "TimeoutError"},
        })
        self.assertEqual(health["input_hash_status"], "OK")
        self.assertEqual(health["input_hash"], digest)
        self.assertEqual(health["symbols_processed"], 42)
        self.assertEqual(health["coverage_status"], "PARTIAL")
        self.assertEqual(health["data_errors"], {"bybit": "TimeoutError"})
        self.assertIs(health["manual_trade_only"], True)

    def test_missing_hash_is_explicitly_unavailable(self):
        health = build_health({
            "generated_at_utc": "2026-11-10T10:00:00+00:00",
            "quality": {},
        })
        self.assertEqual(health["input_hash_status"], "UNAVAILABLE")
        self.assertIsNone(health["input_hash"])

    def test_isolated_branch_publisher_writes_health_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "branch"
            output.mkdir()
            source_json = root / "signals.json"
            source_csv = root / "history.csv"
            source_health = root / "health.json"
            payload = {
                "generated_at_utc": "2026-11-10T10:00:00+00:00",
                "pipeline_status": "DEGRADED",
                "signals": [{"symbol": "BTC/USDT:USDT", "status": "MARKET_DATA_DEGRADED"}],
            }
            health = {
                "generated_at_utc": payload["generated_at_utc"],
                "input_hash": "b" * 64,
                "input_hash_status": "OK",
                "manual_trade_only": True,
            }
            source_json.write_text(json.dumps(payload), encoding="utf-8")
            source_health.write_text(json.dumps(health), encoding="utf-8")
            source_csv.write_text(
                "generated_at_utc,symbol,status,side,tier,provider,engine,reason,confidence,ev_net,idempotency_key\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "publish_signals_branch.py"),
                    "--source-json", str(source_json),
                    "--source-csv", str(source_csv),
                    "--source-health", str(source_health),
                    "--output-dir", str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            published = json.loads((output / "health.json").read_text(encoding="utf-8"))
            self.assertEqual(published, health)


if __name__ == "__main__":
    unittest.main()
