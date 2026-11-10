"""آزمون حفاظتی: موتور تاریخی یک‌ساعته نباید داده بگیرد یا چیزی منتشر کند."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import logic


class LegacyHourlyQuarantineTests(unittest.TestCase):
    @patch("logic.publish")
    @patch("logic.notify_tier_a")
    @patch("logic.MarketDataFetcher")
    def test_disabled_hourly_engine_exits_before_fetch_notify_or_publish(
        self, fetcher_cls, notify, publish
    ):
        logic.main()
        fetcher_cls.assert_not_called()
        notify.assert_not_called()
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
