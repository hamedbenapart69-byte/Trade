import unittest
from datetime import datetime, timezone
from scripts.provider_neutral_probe import _shape_hint, _timestamp_hint, build_probes

class ProviderProbeTests(unittest.TestCase):
    def test_shape_hint_for_object(self):
        self.assertEqual(_shape_hint({"b": 2, "a": 1}), "object:a,b")

    def test_shape_hint_for_array(self):
        self.assertEqual(_shape_hint([{"symbol": "BTC", "price": 1}]), "array[1]:object:price,symbol")

    def test_timestamp_hint_nested(self):
        self.assertEqual(_timestamp_hint({"data": {"timestamp": 123}}), "123")

    def test_build_probes_are_read_only_and_bounded(self):
        probes = build_probes(datetime(2026, 11, 16, 17, 0, tzinfo=timezone.utc))
        self.assertEqual(len(probes), 18)
        self.assertTrue(all(url.startswith("https://") for _, _, url, _ in probes))
        self.assertTrue(all("api_key=" not in url for _, _, url, _ in probes))
        self.assertTrue(all("order" not in url.lower() for _, _, url, _ in probes))

if __name__ == "__main__":
    unittest.main()
