import unittest
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from scripts.prepare_pages import build_payload, REQUIRED_AUDIT_CHECKS
from scripts.v5_live_scan import classify_scan

def source():
    return {
        "status":"SCAN_COMPLETED","scan_id":"unit-test","scanned_at":"2026-11-07T10:00:00+00:00",
        "universe_requested":100,"scan_mode":"EXPANDED_TOP_100","primary_shortlist_target":30,
        "primary_shortlist_selected":30,"expanded_discovery_target":70,"expanded_discovery_selected":10,
        "extended_partial":False,"eligible_assets":40,"selected_assets":40,"screened_assets":40,
        "coverage":{"total_candidates":30,"screened":30,"insufficient_data":0,"rejected":30,"wait":0},
        "source_status":{"discovery":"CoinGecko public API","futures_ohlcv":"OKX public market-data API",
          "underlying_market_data":"CoinGecko public spot price cross-checked against OKX index price",
          "account_connection":False,"exchange_api_credentials":False,"order_execution":False},
        "validation_context":{"fixture_data":False,"account_connection":False,"order_execution":False},
        "actionable":[{
          "symbol":"BTC-USDT-SWAP","strategy_family":"V3_STRICT_BASELINE","decision":"BUY_NOW","direction":"LONG","entry":100.0,"stop_loss":98.5,
          "entry_observed_at_ms":int(datetime.now(timezone.utc).timestamp()*1000)-30_000,
          "take_profit":103.0,"stop_pct":1.5,"confidence_v5":75,"data_grade":"B","self_audit_passed":True,
          "self_audit":{**{key:True for key in REQUIRED_AUDIT_CHECKS},"v3_baseline_passed":True,"v3_funding_threshold_passed":True,"strategy_family":"V3_STRICT_BASELINE"},
          "entry_quality":{"entry_ok":True,"chase":False},
          "risk":{"valid":True,"contract_spec_verified":True,"planned_loss_usd":4.0,
            "required_leverage":1.33,"reward_to_risk":2.0}
        }],
        "conditional":[],"performance":{"mode":"paper_signal_tracking_not_executed_trades"},
        "limitations":[]
    }

class PagesPayloadTests(unittest.TestCase):
    def test_publishes_only_fully_validated_actionable_signals(self):
        payload=build_payload(source())
        self.assertEqual(payload["status"],"SCAN_COMPLETED")
        self.assertEqual(len(payload["actionable"]),1)
        self.assertTrue(payload["publication_gate"]["source_verified"])

    def test_adaptive_strategy_can_pass_publication_without_v3_baseline(self):
        raw=source()
        item=raw["actionable"][0]
        item["strategy_family"]="TREND_PULLBACK"
        item["self_audit"]["strategy_family"]="TREND_PULLBACK"
        item["self_audit"]["v3_baseline_passed"]=False
        item["self_audit"]["v3_funding_threshold_passed"]=False
        payload=build_payload(raw)
        self.assertEqual(len(payload["actionable"]),1)
        self.assertEqual(payload["actionable"][0]["strategy_family"],"TREND_PULLBACK")

    def test_drops_actionable_signal_if_a_v5_risk_gate_fails(self):
        raw=source()
        raw["actionable"][0]["risk"]["planned_loss_usd"]=4.01
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])
        self.assertEqual(payload["publication_gate"]["actionable_candidates_received"],1)
        self.assertEqual(payload["publication_gate"]["actionable_candidates_published"],0)

    def test_stale_entry_observation_is_not_published(self):
        raw=source()
        raw["actionable"][0]["entry_observed_at_ms"]=int(datetime.now(timezone.utc).timestamp()*1000)-16*60_000
        self.assertEqual(build_payload(raw)["actionable"],[])
        raw=source()
        raw["actionable"]=[]
        raw["conditional"]=[{
          "symbol":"BTC-USDT-SWAP","strategy_family":"V3_STRICT_BASELINE","decision":"CONDITIONAL_BUY","direction":"LONG",
          "entry_observed_at_ms":int(datetime.now(timezone.utc).timestamp()*1000)-16*60_000,
          "confidence_v5":65,"data_grade":"B","self_audit_passed":True,
          "self_audit":{**{key:True for key in REQUIRED_AUDIT_CHECKS},"v3_baseline_passed":True,"v3_funding_threshold_passed":True,"strategy_family":"V3_STRICT_BASELINE"},"stop_pct":1.5,
          "entry_quality":{"confirmation_required":"15m close above trigger","trigger_level":101.0},
          "risk":{"valid":True,"contract_spec_verified":True,"planned_loss_usd":4.0,
            "required_leverage":1.33,"reward_to_risk":2.0}
        }]
        self.assertEqual(build_payload(raw)["conditional"],[])

    def test_drops_all_signals_when_fixture_or_account_data_is_used(self):
        raw=source()
        raw["validation_context"]["fixture_data"]=True
        payload=build_payload(raw)
        self.assertEqual(payload["status"],"INSUFFICIENT_DATA")
        self.assertEqual(payload["actionable"],[])
        self.assertFalse(payload["publication_gate"]["source_verified"])

    def test_drops_actionable_when_self_audit_or_entry_confirmation_fails(self):
        raw=source()
        raw["actionable"][0]["self_audit_passed"]=False
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])
        raw=source()
        raw["actionable"][0]["entry_quality"]["entry_ok"]=False
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])

    def test_baseline_and_venue_audit_must_be_explicitly_true(self):
        raw=source()
        raw["actionable"][0]["self_audit"]["v3_baseline_passed"]=False
        self.assertEqual(build_payload(raw)["actionable"],[])
        raw=source()
        raw["actionable"][0]["self_audit"]["venue_leverage_limit_verified"]=False
        self.assertEqual(build_payload(raw)["actionable"],[])

    def test_non_finite_prices_are_never_published(self):
        raw=source()
        raw["actionable"][0]["entry"]=float("nan")
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])

    def test_conditional_requires_measurable_trigger_and_full_risk_checks(self):
        raw=source()
        raw["actionable"]=[]
        raw["conditional"]=[{
          "symbol":"BTC-USDT-SWAP","strategy_family":"V3_STRICT_BASELINE","decision":"CONDITIONAL_BUY","direction":"LONG",
          "entry_observed_at_ms":int(datetime.now(timezone.utc).timestamp()*1000)-30_000,
          "confidence_v5":65,"data_grade":"B","self_audit_passed":True,"self_audit":{**{key:True for key in REQUIRED_AUDIT_CHECKS},"v3_baseline_passed":True,"v3_funding_threshold_passed":True,"strategy_family":"V3_STRICT_BASELINE"},"stop_pct":1.5,
          "entry_quality":{"confirmation_required":"15m close above trigger","trigger_level":101.0},
          "risk":{"valid":True,"contract_spec_verified":True,"planned_loss_usd":4.0,
            "required_leverage":1.33,"reward_to_risk":2.0}
        }]
        payload=build_payload(raw)
        self.assertEqual(len(payload["conditional"]),1)
        raw["conditional"][0]["risk"]["planned_loss_usd"]=4.1
        payload=build_payload(raw)
        self.assertEqual(payload["conditional"],[])

    def test_actionable_publication_is_deduplicated_and_capped_at_ten(self):
        raw=source()
        base=raw["actionable"][0]
        raw["actionable"]=[]
        for i in range(12):
            item=json.loads(json.dumps(base))
            item["symbol"]=f"COIN{i}-USDT-SWAP"
            item["confidence_v5"]=80-i
            raw["actionable"].append(item)
        duplicate=json.loads(json.dumps(raw["actionable"][0]))
        raw["actionable"].append(duplicate)
        payload=build_payload(raw)
        self.assertEqual(len(payload["actionable"]),10)
        keys={(x["symbol"],x["direction"]) for x in payload["actionable"]}
        self.assertEqual(len(keys),10)

    def test_static_dashboard_javascript_parses(self):
        node=shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable")
        html=Path("web/index.html").read_text(encoding="utf-8")
        scripts=re.findall(r"<script>([\s\S]*?)</script>",html)
        self.assertEqual(len(scripts),1)
        with tempfile.NamedTemporaryFile("w",suffix=".js",encoding="utf-8") as f:
            f.write(scripts[0])
            f.flush()
            subprocess.run([node,"--check",f.name],check=True,capture_output=True,text=True)

    def test_partial_scan_with_some_valid_assets_is_not_data_unavailable(self):
        self.assertEqual(classify_scan({
          "screened_assets":15,
          "coverage":{"total_candidates":30,"screened":15,"insufficient_data":15}
        }),"SCAN_COMPLETED")

    def test_all_insufficient_assets_are_data_unavailable(self):
        self.assertEqual(classify_scan({
          "screened_assets":0,
          "coverage":{"total_candidates":30,"screened":0,"insufficient_data":30}
        }),"DATA_UNAVAILABLE")

    def test_payload_exposes_primary_and_expanded_market_coverage(self):
        payload=build_payload(source())
        self.assertEqual(payload["scan_mode"],"EXPANDED_TOP_100")
        self.assertEqual(payload["primary_shortlist_selected"],30)
        self.assertEqual(payload["expanded_discovery_selected"],10)
        self.assertIn("CoinGecko public spot",payload["source_status"]["underlying_market_data"])

if __name__=="__main__":
    unittest.main()
