# Unattended Research & Development Progression Addendum V1.0

**Date:** 2026-11-15  
**Repository:** `hamedbenapart69-byte/Trade`  
**Base authority:** V12.0 Master System Integration & Operational Governance  
**Related proposal:** V13.0 (not approved by this addendum)  
**Status:** User-authorized operating-model amendment; implementation and activation remain subject to review and CI.

## 1. Purpose

The owner has explicitly authorized the project to continue approved, reversible research and engineering work without requiring a new conversational approval after every stage. The goal is to reduce idle time while preserving the existing evidence, safety, statistical and release gates.

This addendum changes only the **human-approval cadence for reversible research and development progression**. It does not approve V13.0 as a whole, declare any stage passed, authorize deployment, or change any quantitative acceptance criterion.

## 2. Narrow governance amendment

The following V12.0 requirements are amended only within the scope below:

- V12.0 §21.5: the user need not separately approve continuation after every stage that has independently achieved PASS, provided the next task is already within the approved roadmap and is reversible.
- V12.0 §29: the existing Stage 0–15 order remains authoritative. The owner’s approval authorizes unattended continuation inside that order; it does not waive Stage 0 acceptance, stage evidence, or any release gate.

All other V12.0 requirements remain in force. Where a requirement is stricter than this addendum, the stricter requirement wins unless this addendum explicitly names that exact approval-cadence rule.

## 3. Authorized unattended scope

The orchestrator may, without a new conversational approval:

1. Inspect repository state, registered tasks, CI results, artifacts and evidence.
2. Run allowlisted tests, deterministic diagnostics, data-quality checks, reproducible backtests and registered walk-forward experiments.
3. Conduct research and write proposed code or documentation on isolated, non-production branches, but only when a verified, zero-cost, authorized coding-agent runtime is actually connected.
4. Create bounded v1/v2/v3 trials under the SLRP rules.
5. Record failures, diagnosis codes, evidence, commit SHAs and reproducibility metadata.
6. Continue to the next pre-authorized reversible task only after the current task has a genuine PASS.
7. Open draft pull requests for review when the diff and CI evidence are complete.
8. Stop, quarantine or roll back an isolated research change when a deterministic safety or integrity check fails.

The orchestrator must never represent a scheduled scan, successful CI run, mock test, proxy measurement or completed workflow as proof of trading edge.

## 4. Actions that remain approval-gated

The following always require explicit owner approval, regardless of stage PASS:

- Changing acceptance thresholds, score weights, hard gates, risk limits, or the constitution.
- Reclassifying PROXY or UNAVAILABLE data as REAL.
- Changing the approved roadmap, adding a new production strategy, or changing the declared market/profile scope.
- Merging into `main`, `production-v1`, or another protected/production branch.
- Production deployment, DNS/domain changes, publishing a new live dashboard, or changing live delivery behavior.
- Adding, exposing, rotating, or changing secrets and credentials.
- Enabling an external agent, browser automation, webhook destination, or third-party service that has not passed the zero-cost, security and Iran-access checks.
- Destructive repository, data, database, branch, artifact or infrastructure operations.
- Any exchange-account connection, private trading credential, account/position retrieval, or order action. These remain prohibited, not merely approval-gated.

## 5. Autonomous stage state machine

Every stage and every registered trial must use an explicit state:

- `NOT_STARTED`
- `READY`
- `RUNNING`
- `PASS`
- `FAIL`
- `BLOCKED`
- `ESCALATED`
- `HONEST_STOP`

A state transition must be append-only in the evidence ledger and include timestamp, actor/runtime, source commit, configuration version, dataset version, run ID, outcome, and evidence references.

### 5.1. Automatic continuation

A stage may advance automatically only when all of the following are true:

1. Its numeric acceptance criteria were registered before the trial.
2. Required L1 Data, L2 Compute and L3 Delivery evidence exists for that stage.
3. All mandatory tests completed; skipped tests are not PASS.
4. Data provenance, freshness, point-in-time validity and cost assumptions are recorded.
5. No hard gate, safety check, or security check failed.
6. The SLRP report is complete and machine-readable.
7. The result is `PASS`, not merely CI green, runtime success, or a promising partial result.
8. The next task is already within the owner-authorized reversible scope.

If any condition is absent, the stage is `BLOCKED` or `INSUFFICIENT_EVIDENCE`; it must not advance.

### 5.2. SLRP version discipline

- v1 is the default first trial.
- v2 may be created only after a real v1 FAIL, with a specific D1–D6 diagnosis and evidence explaining why v1 failed.
- v3 may be created only after a real v2 FAIL, with a specific diagnosis and evidence.
- Maximum three versions per registered stage/trial.
- No speculative v2/v3, no parameter-only disguise of a new hypothesis, and no relaxing criteria.
- If all permitted versions fail, invoke the Innovation Protocol or Honest Stop. Do not loop indefinitely.

Diagnosis codes remain:
- D1 — Data
- D2 — Assumption
- D3 — Implementation
- D4 — Threshold / Calibration
- D5 — Regime
- D6 — Expectations

### 5.3. Stage PASS is not strategy PASS

A software test pass, successful workflow, data coverage improvement, or two consecutive runtime passes cannot establish profitability or statistical edge.

Strategy acceptance remains based on independent out-of-sample evidence, realistic costs, uncertainty, calibration, multiple-testing controls and the applicable pre-existing Gate. Daily/Scalp profiles, LRT/NMT engines, Plans A/B/C/H and individual generators retain separate ledgers and performance reports.

## 6. Two distinct automation loops

The system must distinguish:

### Loop A — Market and evidence operations

This includes scheduled market-data collection, provider fallback, feature computation, signal-state evaluation, outcome tracking, validation jobs, artifact publication and health monitoring.

GitHub Actions may run deterministic jobs on a schedule. A cron expression is a target schedule, not proof of exact start time or delivery latency. Missed runs and stale data must be visible.

### Loop B — Research and engineering progression

This includes task selection, hypothesis registration, code changes, test-driven diagnosis, bounded repair, review and stage progression.

GitHub Actions is a job runner, not an AI software engineer. It may execute registered commands and enforce state transitions, but it must not be described as autonomously authoring or improving code unless a separate coding-agent runtime is connected and verified.

**Current integration rule:** no zero-cost AI coding-agent runtime with authorized write access to this repository has been verified in this revision. Therefore unattended deterministic checks and evidence progression may be automated, but autonomous AI code authorship remains `UNVERIFIED / NOT_CONNECTED` until the runtime, license/free-tier limits, repository permissions, Iran reachability, audit trail and cost are demonstrated. No paid API or trial-credit dependency may be introduced.

## 7. Agent admission gate

Before any coding agent can receive repository write access, verify and record:

1. Official pricing and free-tier terms, including usage ceilings and expiry.
2. Usability from the owner's actual environment, including Iran/VPN restrictions.
3. Exact repository and branch permissions; no production-branch write permission.
4. Secret isolation; no exchange or trading credentials.
5. Tool allowlist and network-egress policy.
6. Human-readable diff, immutable run log and reproducible tests.
7. Maximum runtime, retry budget and per-task resource ceiling.
8. Safe interruption and rollback behavior.
9. No hidden paid fallback, billing activation or trial-credit reliance.

Failure of any admission check means the agent remains disabled. Do not silently substitute a paid model, paid API, external service or unverified free trial.

## 8. Repository and change controls

- Work only on isolated feature/research branches.
- Never force-push or rewrite protected history.
- Keep each change small, reviewable and attributable to one registered task.
- Use least-privilege GitHub permissions; default to read-only.
- Use `persist-credentials: false` unless a narrowly scoped write is required and justified.
- Never expose tokens in logs, artifacts, diffs or test output.
- Run relevant tests plus repository-wide CI where feasible.
- Store evidence as versioned artifacts with retention and provenance.
- Open a draft PR for owner review; do not merge or deploy.
- A failed or uncertain run must not be retried blindly if the external side effect is unknown.

## 9. Signal-quality objective

The optimization target is **independently validated, cost-adjusted net expectancy and robust risk-adjusted performance**, not maximum win rate or signal count.

Every actionable signal must preserve:
- A falsifiable numeric hypothesis.
- A specific invalidation/falsification condition.
- Correct point-in-time feature availability.
- REAL / PROXY / UNAVAILABLE labels.
- Calibrated probability or `NOT_CALIBRATED`.
- Net EV after applicable fees, spread, slippage, funding and material execution effects, or `NOT_CALCULATED` when inputs are insufficient.
- Signal expiry and freshness checks.
- Strategy/profile attribution and immutable outcome linkage.

A high win rate with negative net expectancy, weak sample size, leakage, uncalibrated probabilities or failed OOS gates is not a successful strategy. No win rate or profit outcome is guaranteed.

## 10. Required orchestration observability

At minimum, each orchestration cycle must record:

- `orchestration_run_id`
- `started_at` / `finished_at`
- `repository_commit` and working branch
- `task_id`, `stage_id`, `trial_id`, `version`
- `decision` and reason code
- `test_summary`
- `evidence_manifest`
- `cost_and_quota_status`
- `agent_runtime_status`
- `next_action` or explicit stop reason

The dashboard must distinguish market-scan health, research progress, engineering CI, strategy validation, calibration and delivery health. One green indicator must never mask a failure in another dimension.

## 11. Current known repository baseline

At the time of this addendum's inspection:

- Repository: `hamedbenapart69-byte/Trade`.
- Default branch: `main`.
- Inspected main commit: `53ab11e996f6679d203d1e23840c113f88b4ca55`.
- The repository contains an existing FastAPI control-plane foundation with approval-gated runs, SQLite persistence, durable outbox, explicit allowlists and a one-shot worker.
- The repository README and roadmap explicitly state that a production-hosted autonomous AI platform, external model, browser automation and full external workflow have not been verified.
- The open-PR queue is nontrivial; new orchestration work must not duplicate or conflict with existing Stage 1B, dashboard, notifier, data and validation PRs.
- The `autonomous-crypto-engine` branch exists but is not evidence of a verified autonomous coding runtime.
- V12.0 §21.5 currently requires user approval before the next stage; this addendum is the narrow owner-authorized exception for reversible progression.
- The Master Source V10.0 file was not available for direct inspection in the reviewed source set. Clause-level reconciliation against V10.0 remains blocked until that exact source is available.

These are point-in-time observations and must be refreshed before implementation or release decisions.

## 12. Activation and acceptance

This addendum becomes operational only after:

1. The owner-authorized scope is represented in the repository as a reviewed change.
2. CI passes for the implementation.
3. The orchestrator is tested against PASS, FAIL, BLOCKED, missing-evidence, invalid-version-order, exhausted-budget and approval-required cases.
4. A dry-run proves that no protected branch, production deployment, secret or trading endpoint can be modified.
5. The evidence ledger records the exact commit and workflow run.

Until those conditions are met:

`UNATTENDED_RESEARCH_AUTHORIZATION = GRANTED`  
`ORCHESTRATOR_IMPLEMENTATION = NOT_VERIFIED`  
`AUTONOMOUS_CODE_AUTHORING = UNVERIFIED_NOT_CONNECTED`  
`PRODUCTION_MERGE_OR_DEPLOY = REQUIRES_EXPLICIT_APPROVAL`  
`TRADING_ACCOUNT_ACCESS = PROHIBITED`

---

**Controlling principle:** Work may continue without waiting for a conversational prompt, but it may never continue by pretending a failed, incomplete, stale, proxy-only or statistically weak result has passed.
