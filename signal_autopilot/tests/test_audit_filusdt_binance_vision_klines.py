from __future__ import annotations

import importlib.util
import io
import sys
import unittest
import zipfile
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_filusdt_binance_vision_klines.py"
SPEC = importlib.util.spec_from_file_location("audit_filusdt_binance_vision_klines", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BinanceVisionAuditTests(unittest.TestCase):
    def test_checksum_parser(self):
        digest = "a" * 64
        self.assertEqual(MODULE._parse_checksum(f"{digest}  file.zip".encode()), digest)

    def test_decimal_rejects_nan_and_infinity(self):
        self.assertIsNone(MODULE._decimal("NaN"))
        self.assertIsNone(MODULE._decimal("Infinity"))
        self.assertEqual(str(MODULE._decimal("1.2300")), "1.2300")

    def test_archive_parser_requires_single_csv_and_valid_checksum(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("FILUSDT-15m.csv", "1000,1,2,0.5,1.5,10,1999,15,7,4,6,0\\n")
        rows = payload.getvalue()
        self.assertTrue(rows.startswith(b"PK"))


if __name__ == "__main__":
    unittest.main()
