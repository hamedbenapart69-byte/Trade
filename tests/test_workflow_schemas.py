import unittest
from app.workflow_schemas import validate_workflow_input

class WorkflowSchemaTests(unittest.TestCase):
 def test_research_scan_accepts_valid_spot_request(self):
  self.assertIsNone(validate_workflow_input("research.scan",{"symbol":"BTCUSDT","market":"spot","timeframe":"4h"}))
 def test_research_scan_rejects_unsupported_timeframe_and_unknown_fields(self):
  self.assertEqual(validate_workflow_input("research.scan",{"symbol":"BTCUSDT","market":"futures","timeframe":"2m"}),"unsupported_timeframe")
  self.assertEqual(validate_workflow_input("research.scan",{"symbol":"BTCUSDT","market":"spot","timeframe":"4h","shell":"bad"}),"unknown_fields:shell")
 def test_unknown_workflow_fails_closed(self):
  self.assertEqual(validate_workflow_input("arbitrary.workflow",{}),"workflow_schema_not_registered")
if __name__=="__main__": unittest.main()
