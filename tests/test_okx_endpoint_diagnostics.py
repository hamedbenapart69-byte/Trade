import unittest
from unittest.mock import patch

from scripts.test_okx_endpoints import (
    classify_endpoint_count,
    classify_oi_coverage,
    test_oi_hourly_history,
)


class OKXEndpointDiagnosticsTests(unittest.TestCase):
    def test_endpoint_gate_boundaries(self):
        self.assertEqual(classify_endpoint_count(15), "ALL_PASS")
        self.assertEqual(classify_endpoint_count(14), "HIGH_PASS")
        self.assertEqual(classify_endpoint_count(13), "HIGH_PASS")
        self.assertEqual(classify_endpoint_count(12), "PARTIAL_PASS")
        self.assertEqual(classify_endpoint_count(8), "PARTIAL_PASS")
        self.assertEqual(classify_endpoint_count(7), "MOSTLY_FAIL")
        self.assertEqual(classify_endpoint_count(0), "MOSTLY_FAIL")

    def test_oi_coverage_boundaries(self):
        self.assertEqual(classify_oi_coverage(2160, 2160), "FULL")
        self.assertEqual(classify_oi_coverage(720, 720), "PARTIAL")
        self.assertEqual(classify_oi_coverage(719, 719), "INSUFFICIENT")
        self.assertEqual(classify_oi_coverage(2160, 2159), "PARTIAL")

    def test_hourly_oi_pagination_uses_last_record_as_before_cursor(self):
        first = [[str(ts), "1000", "10"] for ts in (ts * 3_600_000 for ts in range(300, 200, -1))]
        second = [[str(ts), "1000", "10"] for ts in (ts * 3_600_000 for ts in range(200, 100, -1))]
        with patch(
            "scripts.test_okx_endpoints._get_json",
            side_effect=[
                (200, {"code": "0", "msg": "", "data": first}, None),
                (200, {"code": "0", "msg": "", "data": second}, None),
            ],
        ) as mocked:
            with patch("scripts.test_okx_endpoints.time.sleep"):
                result = test_oi_hourly_history(
                    "BTC", target_hours=150, limit=100, max_requests=25
                )
        self.assertEqual(mocked.call_count, 2)
        second_params = mocked.call_args_list[1].args[1]
        self.assertEqual(second_params["before"], first[-1][0])
        self.assertEqual(result["record_count"], 200)
        self.assertEqual(result["coverage_hours"], 200)
        self.assertEqual(result["coverage_status"], "FULL")
        self.assertLessEqual(result["requests_made"], 25)


if __name__ == "__main__":
    unittest.main()
