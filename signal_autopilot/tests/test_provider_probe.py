import json
import unittest
from scripts.probe_public_providers import PROBES, probe_one, validate_payload

class ProviderProbeTests(unittest.TestCase):
 def test_probe_catalog_contains_server_side_sources(self):
  self.assertGreaterEqual(len(PROBES),8)
  self.assertTrue(all("url" in p and "category" in p for p in PROBES))
 def test_bybit_schema_validation(self):
  p={"retCode":0,"result":{"list":[["1","2","3","1","2","4"]]}}
  self.assertEqual(validate_payload("bybit_linear_ohlcv",json.dumps(p).encode(),"json"),(True,"schema_valid"))
 def test_binance_schema_validation(self):
  self.assertTrue(validate_payload("binance_usdm_ohlcv",b'[[1,"1","2","1","2","3"]]',"json")[0])
 def test_coinboss_requires_success_and_timestamp(self):
  self.assertTrue(validate_payload("coinboss_cross_exchange_oi",b'{"success":true,"asof":123}',"json")[0])
  self.assertFalse(validate_payload("coinboss_cross_exchange_oi",b'{"success":true}',"json")[0])
 def test_rss_schema_validation(self):
  self.assertTrue(validate_payload("coindesk_rss",b'<rss><channel><item><title>Market</title></item></channel></rss>',"xml")[0])
 def test_probe_reports_schema_valid_response(self):
  class FakeResponse:
   status=200
   def __enter__(self): return self
   def __exit__(self,*args): return False
   def getcode(self): return 200
   def read(self): return b'{"code":"0","data":[{"last":"1"}]}'
  result=probe_one(PROBES[0],opener=lambda request,timeout:FakeResponse())
  self.assertEqual(result["status"],"RUNTIME_PASS")
  self.assertEqual(result["http_status"],200)
 def test_probe_classifies_runner_403(self):
  import urllib.error
  def fail(request,timeout): raise urllib.error.HTTPError(request.full_url,403,"Forbidden",{},None)
  result=probe_one(PROBES[0],opener=fail)
  self.assertEqual(result["status"],"BLOCKED_FROM_RUNNER")
  self.assertEqual(result["reason"],"http_403")

if __name__=="__main__": unittest.main()
