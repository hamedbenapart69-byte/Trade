"""Regression tests for atomic research artifacts and immutable signal identity."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import _atomic_write_json, load_research_state, save_research_state


class ResearchStateIntegrityTests(unittest.TestCase):
    def test_atomic_json_preserves_previous_file_on_serialization_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            _atomic_write_json(path, {"version": 1})
            with self.assertRaises(TypeError):
                _atomic_write_json(path, {"invalid": object()})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 1})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
            _atomic_write_json(path, {"version": 2})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_load_rejects_duplicate_signal_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            row = {"signal_id": "duplicate-1"}
            path.write_text(json.dumps({"schema_version": 1, "signals": [row, row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_signal_id_missing_or_duplicate"):
                load_research_state(path)

    def test_load_rejects_missing_signal_id_and_invalid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            path.write_text(json.dumps({"schema_version": 1, "signals": [{}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_signal_id_missing_or_duplicate"):
                load_research_state(path)
            path.write_text(json.dumps({"schema_version": 1, "signals": [None]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_record_invalid"):
                load_research_state(path)

    def test_load_rejects_unsupported_schema_and_oversized_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            path.write_text(json.dumps({"schema_version": 2, "signals": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_schema_invalid"):
                load_research_state(path)
            path.write_text(" " * (10_000_001), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "research_state_file_invalid"):
                load_research_state(path)

    def test_load_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "missing.json"
            link = root / "research_signals.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this runner")
            with self.assertRaisesRegex(ValueError, "research_state_file_invalid"):
                load_research_state(link)

    def test_save_validates_unique_ids_and_writes_atomic_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "research_signals.json"
            payload = {"schema_version": 1, "signals": [{"signal_id": "r-1"}]}
            save_research_state(path, payload)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["signal_count"], 1)
            self.assertEqual(saved["signals"][0]["signal_id"], "r-1")
            self.assertTrue(saved["updated_at_utc"])
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])
            duplicate = {"schema_version": 1, "signals": [{"signal_id": "r-1"}, {"signal_id": "r-1"}]}
            with self.assertRaisesRegex(ValueError, "research_state_signal_id_missing_or_duplicate"):
                save_research_state(path, duplicate)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
