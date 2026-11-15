"""Fail-closed decision logic for unattended, reversible research progression.

This module does not execute commands, edit files, merge pull requests, deploy,
or contact external services. It evaluates a pre-registered stage/trial record
and returns the single permitted next action.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping

DIAGNOSIS_CODES = {"D1", "D2", "D3", "D4", "D5", "D6"}
VERSION_STATES = {"NOT_RUN", "RUNNING", "PASS", "FAIL"}
REVERSIBLE_TASK_TYPES = {"research", "reversible_code", "tests", "documentation"}
APPROVAL_TASK_TYPES = {
    "threshold_change", "gate_change", "risk_limit_change", "merge",
    "production_deploy", "secret_change", "destructive_change",
    "live_delivery_change", "scope_change", "strategy_scope_change",
    "market_scope_change", "production_config_change",
}
PROHIBITED_TASK_TYPES = {
    "trading_account_access", "trading_credential_use", "order_execution"
}


class PlanValidationError(ValueError):
    """Raised when a plan is malformed or violates the version contract."""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _evidence_ok(version: Mapping[str, Any]) -> bool:
    evidence = version.get("evidence")
    return isinstance(evidence, list) and bool(evidence) and all(_nonempty(x) for x in evidence)


def validate_stage(stage: Mapping[str, Any]) -> None:
    """Validate pre-registered acceptance, layer and SLRP version contracts."""
    if not _nonempty(stage.get("stage_id")):
        raise PlanValidationError("stage_id_required")
    criteria = stage.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise PlanValidationError("numeric_acceptance_criteria_must_be_registered")
    seen_metrics: set[str] = set()
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise PlanValidationError("acceptance_criteria_must_be_structured_numeric_rules")
        metric = criterion.get("metric")
        operator = criterion.get("operator")
        target = criterion.get("target")
        if not _nonempty(metric) or metric in seen_metrics:
            raise PlanValidationError("acceptance_metric_must_be_nonempty_and_unique")
        if operator not in {">=", ">", "<=", "<", "==", "!="}:
            raise PlanValidationError(f"unsupported_acceptance_operator:{metric}")
        if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(float(target)):
            raise PlanValidationError(f"acceptance_target_must_be_finite_number:{metric}")
        seen_metrics.add(metric)
    if stage.get("criteria_frozen") is not True:
        raise PlanValidationError("acceptance_criteria_must_be_frozen_before_trial")
    versions = stage.get("versions")
    if not isinstance(versions, list) or not 1 <= len(versions) <= 3:
        raise PlanValidationError("one_to_three_registered_versions_required")
    for index, version in enumerate(versions):
        expected = f"v{index + 1}"
        if not isinstance(version, dict) or version.get("version") != expected:
            raise PlanValidationError("versions_must_be_sequential_v1_v2_v3")
        status = version.get("status")
        if status not in VERSION_STATES:
            raise PlanValidationError(f"invalid_version_status:{expected}")
        if index > 0:
            previous = versions[index - 1]
            if previous.get("status") != "FAIL":
                raise PlanValidationError(f"{expected}_requires_previous_version_FAIL")
            if previous.get("diagnosis") not in DIAGNOSIS_CODES:
                raise PlanValidationError(f"{expected}_requires_previous_diagnosis")
            if not _evidence_ok(previous):
                raise PlanValidationError(f"{expected}_requires_previous_failure_evidence")
            reason_key = f"why_{previous['version']}_failed"
            if not _nonempty(version.get(reason_key)):
                raise PlanValidationError(f"{expected}_requires_{reason_key}")
        if status == "FAIL":
            if version.get("diagnosis") not in DIAGNOSIS_CODES:
                raise PlanValidationError(f"{expected}_FAIL_requires_D1_to_D6_diagnosis")
            if not _evidence_ok(version):
                raise PlanValidationError(f"{expected}_FAIL_requires_evidence")
        if status == "PASS" and not _evidence_ok(version):
            raise PlanValidationError(f"{expected}_PASS_requires_evidence")
        if index < len(versions) - 1 and status == "PASS":
            raise PlanValidationError("no_version_may_follow_a_PASS")


def _base_decision(action: str, reason: str, stage_id: str, version: str | None = None) -> dict[str, Any]:
    return {
        "decision": action,
        "reason": reason,
        "stage_id": stage_id,
        "version": version,
        "side_effects_performed": False,
    }


def evaluate_stage(stage: Mapping[str, Any], *, unattended_authorized: bool) -> dict[str, Any]:
    """Return one safe next action for a stage without performing that action."""
    validate_stage(stage)
    stage_id = str(stage["stage_id"])
    versions = stage["versions"]
    layers = stage.get("layers", {})
    layers_pass = isinstance(layers, dict) and all(
        layers.get(key) is True for key in ("L1_DATA", "L2_COMPUTE", "L3_DELIVERY")
    )
    gates_pass = stage.get("hard_gates_passed") is True
    evidence = stage.get("stage_evidence")
    stage_evidence_ok = isinstance(evidence, list) and bool(evidence) and all(_nonempty(x) for x in evidence)
    results = stage.get("acceptance_results")
    result_map = {}
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and _nonempty(item.get("metric")):
                result_map[item["metric"]] = item.get("actual")

    if stage.get("approval_required") is True:
        return _base_decision("HUMAN_APPROVAL_REQUIRED", "stage_explicitly_requires_approval", stage_id)
    if not unattended_authorized:
        return _base_decision("HUMAN_APPROVAL_REQUIRED", "unattended_progression_not_authorized", stage_id)

    latest = versions[-1]
    latest_version = str(latest["version"])
    status = latest["status"]

    if status == "RUNNING":
        return _base_decision("WAIT_FOR_CURRENT_TRIAL", "trial_is_already_running", stage_id, latest_version)

    if status == "PASS":
        missing = []
        if not layers_pass:
            missing.append("L1_L2_L3_evidence")
        if not gates_pass:
            missing.append("hard_gates")
        if not stage_evidence_ok:
            missing.append("stage_evidence")
        criteria_failed = []
        for criterion in stage["acceptance_criteria"]:
            metric = criterion["metric"]
            actual = result_map.get(metric)
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(float(actual)):
                missing.append("acceptance_result:" + metric)
                continue
            target = criterion["target"]
            operator = criterion["operator"]
            passed = {
                ">=": actual >= target,
                ">": actual > target,
                "<=": actual <= target,
                "<": actual < target,
                "==": actual == target,
                "!=": actual != target,
            }[operator]
            if not passed:
                criteria_failed.append(metric)
        if missing:
            return _base_decision("BLOCKED", "stage_PASS_claim_missing:" + ",".join(missing), stage_id, latest_version)
        if criteria_failed:
            return _base_decision("BLOCKED", "stage_PASS_claim_but_numeric_acceptance_failed:" + ",".join(criteria_failed), stage_id, latest_version)
        next_task = stage.get("next_task")
        if not isinstance(next_task, dict):
            return _base_decision("STAGE_PASS_NO_NEXT_TASK", "stage_passed_no_registered_next_task", stage_id, latest_version)
        task_type = next_task.get("type")
        if task_type in PROHIBITED_TASK_TYPES:
            return _base_decision("PROHIBITED", "manual_trading_only_boundary", stage_id, latest_version)
        if task_type in APPROVAL_TASK_TYPES or next_task.get("approval_required") is True:
            return _base_decision("HUMAN_APPROVAL_REQUIRED", "next_task_is_approval_gated", stage_id, latest_version)
        if task_type not in REVERSIBLE_TASK_TYPES:
            return _base_decision("BLOCKED", "next_task_type_not_allowlisted", stage_id, latest_version)
        if not _nonempty(next_task.get("task_id")):
            return _base_decision("BLOCKED", "next_task_id_missing", stage_id, latest_version)
        result = _base_decision(
            "AUTO_CONTINUE",
            "stage_PASS_and_next_task_is_pre_registered_reversible_work",
            stage_id,
            latest_version,
        )
        result.update({"next_task_id": next_task["task_id"], "next_task_type": task_type})
        return result

    if status == "FAIL":
        if len(versions) >= 3:
            return _base_decision("INNOVATION_PROTOCOL", "three_registered_versions_failed", stage_id, latest_version)
        next_version = f"v{len(versions) + 1}"
        return _base_decision("PREPARE_NEXT_VERSION", "previous_version_FAILED_with_diagnosis_and_evidence", stage_id, next_version)

    if status == "NOT_RUN":
        if latest_version == "v1":
            return _base_decision("RUN_V1", "first_registered_trial_ready", stage_id, "v1")
        return _base_decision("RUN_" + latest_version.upper(), "previous_version_FAILED_with_diagnosis_and_specific_reason", stage_id, latest_version)

    return _base_decision("BLOCKED", "unrecognized_stage_state", stage_id, latest_version)


def evaluate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate a single current stage from a versioned orchestration plan."""
    if plan.get("schema_version") != 1:
        raise PlanValidationError("unsupported_schema_version")
    authorization = plan.get("owner_authorization")
    if not isinstance(authorization, dict):
        raise PlanValidationError("owner_authorization_required")
    authorized = authorization.get("unattended_reversible_progression") is True
    current = plan.get("current_stage")
    if not isinstance(current, dict):
        raise PlanValidationError("current_stage_required")
    return evaluate_stage(current, unattended_authorized=authorized)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Path to a pre-registered JSON research plan")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        decision = evaluate_plan(plan)
    except (OSError, json.JSONDecodeError, PlanValidationError) as exc:
        print(json.dumps({
            "decision": "BLOCKED",
            "reason": str(exc),
            "side_effects_performed": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(decision, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
