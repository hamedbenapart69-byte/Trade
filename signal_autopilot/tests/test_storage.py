"""Storage schema migration tests for explicit EV calibration status."""
import csv
import io
import unittest

from modules.storage import FIELDS, migrate_history_csv


class HistoryCsvMigrationTests(unittest.TestCase):
    def test_adds_ev_status_column_without_losing_existing_rows(self):
        old_fields = [
            "generated_at_utc", "symbol", "status", "side", "tier", "provider",
            "engine", "reason", "confidence", "ev_net", "idempotency_key",
        ]
        old = io.StringIO(newline="")
        writer = csv.DictWriter(old, fieldnames=old_fields)
        writer.writeheader()
        writer.writerow({
            "generated_at_utc": "2026-11-10T17:00:00+00:00",
            "symbol": "BTC/USDT:USDT",
            "status": "BUY_NOW",
            "side": "BUY",
            "provider": "okx",
            "engine": "EMA20_EMA50_ATR14_MVP",
            "confidence": "NOT_CALIBRATED",
            "ev_net": "",
            "idempotency_key": "stable-key-1",
        })

        migrated = migrate_history_csv(old.getvalue())
        reader = csv.DictReader(io.StringIO(migrated))
        rows = list(reader)

        self.assertEqual(reader.fieldnames, FIELDS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "BTC/USDT:USDT")
        self.assertEqual(rows[0]["idempotency_key"], "stable-key-1")
        self.assertEqual(rows[0]["ev_status"], "")

    def test_migration_is_idempotent_for_current_schema(self):
        current = io.StringIO(newline="")
        writer = csv.DictWriter(current, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({"symbol": "ETH/USDT:USDT", "ev_status": "NOT_CALIBRATED"})
        value = current.getvalue()
        self.assertEqual(migrate_history_csv(value), value)


if __name__ == "__main__":
    unittest.main()
