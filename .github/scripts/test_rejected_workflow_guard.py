"""Regression tests for permanent V21 LRT/NMT/VTM workflow quarantine."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).with_name("rejected_workflow_guard.py")
SPEC = importlib.util.spec_from_file_location("rejected_workflow_guard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class RejectedWorkflowGuardTests(unittest.TestCase):
    def test_all_rejected_workflows_are_job_level_disabled(self):
        self.assertEqual(MODULE.check(), [])

    def test_step_level_if_does_not_count_as_job_quarantine(self):
        source = """jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: no-op
        if: false
        run: echo disabled
"""
        self.assertEqual(MODULE.job_level_conditions(source), {"run": None})


if __name__ == "__main__":
    unittest.main(verbosity=2)
