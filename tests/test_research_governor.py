import unittest

from app.research_governor import PlanValidationError, evaluate_plan, evaluate_stage


def stage(**overrides):
    value = {
        "stage_id": "stage-0",
        "acceptance_criteria": [
            {"metric": "coverage_pct", "operator": ">=", "target": 99.0},
            {"metric": "required_tests_passed", "operator": ">=", "target": 1},
        ],
        "acceptance_results": [
            {"metric": "coverage_pct", "actual": 99.5},
            {"metric": "required_tests_passed", "actual": 13},
        ],
        "criteria_frozen": True,
        "layers": {"L1_DATA": True, "L2_COMPUTE": True, "L3_DELIVERY": True},
        "hard_gates_passed": True,
        "stage_evidence": ["artifact://stage-0/report.json"],
        "versions": [{"version": "v1", "status": "NOT_RUN"}],
        "next_task": {"task_id": "stage-1-design-review", "type": "documentation"},
    }
    value.update(overrides)
    return value


class ResearchGovernorTests(unittest.TestCase):
    def test_unregistered_or_unfrozen_acceptance_is_rejected(self):
        with self.assertRaisesRegex(PlanValidationError, "criteria_must_be_frozen"):
            evaluate_stage(stage(criteria_frozen=False), unattended_authorized=True)

    def test_v1_is_first_action(self):
        result = evaluate_stage(stage(), unattended_authorized=True)
        self.assertEqual(result["decision"], "RUN_V1")
        self.assertFalse(result["side_effects_performed"])

    def test_no_unattended_authorization_means_human_gate(self):
        result = evaluate_stage(stage(), unattended_authorized=False)
        self.assertEqual(result["decision"], "HUMAN_APPROVAL_REQUIRED")

    def test_v2_requires_real_v1_failure_and_reason(self):
        invalid = stage(versions=[
            {"version": "v1", "status": "PASS", "evidence": ["report"]},
            {"version": "v2", "status": "NOT_RUN", "why_v1_failed": ""},
        ])
        with self.assertRaisesRegex(PlanValidationError, "no_version_may_follow_a_PASS"):
            evaluate_stage(invalid, unattended_authorized=True)

    def test_v2_is_offered_only_after_diagnosed_v1_failure(self):
        result = evaluate_stage(stage(versions=[
            {"version": "v1", "status": "FAIL", "diagnosis": "D3", "evidence": ["ci://run/1"]},
            {"version": "v2", "status": "NOT_RUN", "why_v1_failed": "parser rejected the documented timestamp format"},
        ]), unattended_authorized=True)
        self.assertEqual(result["decision"], "RUN_V2")
        self.assertEqual(result["version"], "v2")

    def test_three_failures_escalate_instead_of_looping(self):
        result = evaluate_stage(stage(versions=[
            {"version": "v1", "status": "FAIL", "diagnosis": "D1", "evidence": ["e1"]},
            {"version": "v2", "status": "FAIL", "diagnosis": "D3", "evidence": ["e2"], "why_v1_failed": "v1 source was stale"},
            {"version": "v3", "status": "FAIL", "diagnosis": "D5", "evidence": ["e3"], "why_v2_failed": "v2 overfit to one regime"},
        ]), unattended_authorized=True)
        self.assertEqual(result["decision"], "INNOVATION_PROTOCOL")

    def test_pass_without_all_three_layers_is_blocked(self):
        result = evaluate_stage(stage(
            layers={"L1_DATA": True, "L2_COMPUTE": True, "L3_DELIVERY": False},
            versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
        ), unattended_authorized=True)
        self.assertEqual(result["decision"], "BLOCKED")

    def test_pass_claim_with_failed_numeric_acceptance_is_blocked(self):
        result = evaluate_stage(stage(
            acceptance_results=[
                {"metric": "coverage_pct", "actual": 98.0},
                {"metric": "required_tests_passed", "actual": 13},
            ],
            versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
        ), unattended_authorized=True)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assertIn("coverage_pct", result["reason"])

    def test_pass_cannot_auto_continue_to_merge_or_deploy(self):
        for task_type in ("merge", "production_deploy", "threshold_change"):
            with self.subTest(task_type=task_type):
                result = evaluate_stage(stage(
                    versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
                    next_task={"task_id": "sensitive", "type": task_type},
                ), unattended_authorized=True)
                self.assertEqual(result["decision"], "HUMAN_APPROVAL_REQUIRED")

    def test_trading_account_and_order_actions_are_prohibited(self):
        for task_type in ("trading_account_access", "trading_credential_use", "order_execution"):
            with self.subTest(task_type=task_type):
                result = evaluate_stage(stage(
                    versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
                    next_task={"task_id": "forbidden", "type": task_type},
                ), unattended_authorized=True)
                self.assertEqual(result["decision"], "PROHIBITED")

    def test_pass_auto_continues_only_to_pre_registered_reversible_task(self):
        result = evaluate_stage(stage(
            versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
        ), unattended_authorized=True)
        self.assertEqual(result["decision"], "AUTO_CONTINUE")
        self.assertEqual(result["next_task_id"], "stage-1-design-review")

    def test_missing_next_task_id_blocks(self):
        result = evaluate_stage(stage(
            versions=[{"version": "v1", "status": "PASS", "evidence": ["report"]}],
            next_task={"type": "research"},
        ), unattended_authorized=True)
        self.assertEqual(result["decision"], "BLOCKED")

    def test_plan_requires_explicit_owner_authorization(self):
        plan = {
            "schema_version": 1,
            "owner_authorization": {"unattended_reversible_progression": False},
            "current_stage": stage(),
        }
        result = evaluate_plan(plan)
        self.assertEqual(result["decision"], "HUMAN_APPROVAL_REQUIRED")

    def test_v2_reason_must_be_specific(self):
        invalid = stage(versions=[
            {"version": "v1", "status": "FAIL", "diagnosis": "D3", "evidence": ["e1"]},
            {"version": "v2", "status": "NOT_RUN", "why_v1_failed": "  "},
        ])
        with self.assertRaisesRegex(PlanValidationError, "why_v1_failed"):
            evaluate_stage(invalid, unattended_authorized=True)


if __name__ == "__main__":
    unittest.main()
