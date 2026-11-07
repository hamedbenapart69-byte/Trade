import unittest
from scripts.prepare_pages import build_payload

def source():
    return {
        "status":"SCAN_COMPLETED","scan_id":"unit-test","scanned_at":"2026-11-07T10:00:00+00:00",
        "universe_requested":30,"eligible_assets":40,"selected_assets":30,"screened_assets":30,
        "coverage":{"total_candidates":30,"screened":30,"insufficient_data":0,"rejected":30,"wait":0},
        "source_status":{"discovery":"CoinGecko public API","futures_ohlcv":"OKX public market-data API",
          "account_connection":False,"exchange_api_credentials":False,"order_execution":False},
        "validation_context":{"fixture_data":False,"account_connection":False,"order_execution":False},
        "actionable":[{
          "symbol":"BTC-USDT-SWAP","decision":"BUY_NOW","direction":"LONG","entry":100.0,"stop_loss":98.5,
          "take_profit":103.0,"stop_pct":1.5,"confidence_v5":75,"data_grade":"B","self_audit_passed":True,
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

    def test_drops_actionable_signal_if_a_v5_risk_gate_fails(self):
        raw=source()
        raw["actionable"][0]["risk"]["planned_loss_usd"]=4.01
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])
        self.assertEqual(payload["publication_gate"]["actionable_candidates_received"],1)
        self.assertEqual(payload["publication_gate"]["actionable_candidates_published"],0)

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

    def test_non_finite_prices_are_never_published(self):
        raw=source()
        raw["actionable"][0]["entry"]=float("nan")
        payload=build_payload(raw)
        self.assertEqual(payload["actionable"],[])

    def test_conditional_requires_measurable_trigger_and_full_risk_checks(self):
        raw=source()
        raw["actionable"]=[]
        raw["conditional"]=[{
          "symbol":"BTC-USDT-SWAP","decision":"CONDITIONAL_BUY","direction":"LONG",
          "confidence_v5":65,"data_grade":"B","self_audit_passed":True,"stop_pct":1.5,
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

if __name__=="__main__":
    unittest.main()
