# STAGE 6 — META-COGNITION, CALIBRATION AND NET EV
## V18.2 C++20 implementation and evidence report

**Stage status: BLOCKED — D1 (outcome data unavailable)**  
**Engineering implementation:** v1 compiled and executed  
**C++ tests:** 10/10 PASS  
**Schema validation:** PASS  
**Telegram delivery:** HTTP 200, message_id 56  
**Calibration:** NOT_CALIBRATED  
**Net EV:** NOT_CALCULATED  
**Actionability:** false

This is not a strategy-performance PASS. The code path and reporting pipeline passed engineering checks, but the required independent closed-outcome evidence does not exist yet.

## 1. Objective

For every LRT/NMT candidate, attach:
- A measurable directional hypothesis.
- A specific falsification condition.
- Calibrated probability only when independent OOS calibration is supported.
- Net EV only when probability, average win/loss and all applicable costs are valid.
- A hard NO_TRADE decision when calibrated net EV is non-positive.

A raw score is not a probability. Missing outcome evidence must remain NOT_CALIBRATED / NOT_CALCULATED.

## 2. Three-layer implementation

### L1 — Outcome data and provenance
- Added contracts/outcome-ledger.v1.schema.json.
- Ledger rows require signal ID, path, regime, close timestamp, raw score, win/loss R and fee/slippage/funding costs in R units.
- Missing numeric cost fields are rejected; they are never defaulted to zero.
- Calibration filters outcomes to closed_at_ms < decision_time_ms.
- Stage 5 report, Stage 4 liquidity report and L1 hash must match exactly.
- Current immutable ledger status: EMPTY; outcomes: 0.

### L2 — C++20 compute
- cpp/include/cfss/meta_calibration.hpp
- cpp/apps/meta_cognition_probe/main.cpp
- cpp/tests/meta_calibration_v1_test.cpp

Implemented:
- Chronological 60/20/20 train/validation/OOS split.
- Platt and isotonic candidate calibrators.
- Calibrator selection on validation Brier only.
- Final assessment on untouched chronological OOS.
- Brier, log loss, Wilson win-rate interval and Brier interval reporting.
- Path/regime isolation.
- Duplicate and malformed outcome rejection.
- Point-in-time cutoff to prevent future closed outcomes entering calibration.
- Net EV with fee, slippage and funding costs.
- NO_TRADE when calibrated net EV <= 0.
- EV remains NOT_CALCULATED if required calibration/outcome inputs are absent.

The current implementation uses a conservative minimum of 250 path/regime outcomes for the 60/20/20 split, with at least 100 train, 30 validation and 50 OOS observations, and requires both outcome classes in every partition. This is an implementation guard, not a profitability claim.

### L3 — Telegram-only delivery
- Added cpp/apps/meta_cognition_telegram_report/main.cpp.
- Idempotent report reservation and delivery receipt.
- Persisted Stage 6 report and receipt on the signals branch.
- No web dashboard or user-side provider interaction was added.

## 3. Numeric acceptance and evidence

| Criterion | Required / policy | Observed | Result |
|---|---:|---:|---|
| C++20 configure/build | Successful | Successful | PASS |
| Full CTest | All tests pass | 10/10 | PASS |
| Chronological split | 60/20/20 | Implemented and unit-tested | PASS (engineering) |
| Minimum sample guard | 250 total; 100/30/50 partitions | 0 real outcomes | BLOCKED |
| Both classes per split | Win and loss present in train/validation/OOS | No observations | BLOCKED |
| Validation-only calibrator selection | No OOS selection | Unit-tested by implementation | PASS (engineering) |
| Future outcome exclusion | closed_at_ms < decision_time_ms | Future-row unit test passes | PASS |
| OOS Brier improvement | Calibrated OOS Brier must improve over raw-score baseline | No real OOS data | BLOCKED |
| Costs | Fee + slippage + funding all explicit | Unit-tested; no real ledger rows | BLOCKED (real evidence) |
| Net EV | Formula only with valid calibrated inputs | NOT_CALCULATED | Correct fail-closed result |
| Telegram | Real delivery receipt | HTTP 200, message_id 56 | PASS |
| Actionability | Always false | false | PASS |

## 4. Real run evidence

- GitHub Actions workflow: C++ Stage 6 Meta-Cognition Calibration and EV
- Run ID: 44312716879
- Run conclusion: success
- Head commit: af139487a4bb9d27ebdd5da5bae2eded5bb4499c
- L1 run ID: okx-cpp-1795005637653
- Scan ID: scan-246d8795472a954f053704771015ad588ead9e78334f612fdf566c3c48af25c7
- Decision timestamp: 1795003200000
- CTest: 100% tests passed, 0 tests failed out of 10
- Meta-cognition schema: valid
- Outcome ledger schema: valid
- Telegram: DELIVERED, HTTP 200, message_id 56

### Live sample

| Symbol | LRT status | LRT confidence | LRT EV | NMT status | NMT confidence | NMT EV |
|---|---|---|---|---|---|---|
| BTC/USDT:USDT | NO_QUALIFIED_SETUP | NOT_CALIBRATED | NOT_CALCULATED | NO_QUALIFIED_SETUP | NOT_CALIBRATED | NOT_CALCULATED |
| ETH/USDT:USDT | NO_QUALIFIED_SETUP | NOT_CALIBRATED | NOT_CALCULATED | NOT_CALIBRATED | NOT_CALCULATED | NOT_CALCULATED |

Both symbols had no Stage 5 qualified candidate. The outcome ledger contained zero closed outcomes. No calibration or EV figure was fabricated.

## 5. Diagnosis

**D1 — Data**

- Failed criterion: independent closed outcomes required for path/regime calibration.
- Required by v1 implementation guard: at least 250 outcomes in a matching path/regime cohort, including the required train/validation/OOS partitions.
- Observed: 0.
- Period: current persisted Stage 5 outcome history at this run.
- Dataset: cpp_runtime/outcome_ledger.v1.json, SHA-256 recorded in the Stage 6 report.
- Result: calibration and EV remain disabled.
- This is not D3 implementation failure: the compute path, schema validation, tests and Telegram delivery succeeded.

## 6. SLRP

    STAGE 6 — META-COGNITION, CALIBRATION AND NET EV
    ├── Acceptance: hypothesis + falsification; chronological calibration; OOS Brier improvement; explicit costs; net EV; transparent Telegram report
    ├── v1 → BLOCKED → D1: 0 real closed outcomes; no independent OOS calibration sample
    ├── v2 → NOT_BUILT → no measured v1 implementation FAIL (R11)
    ├── v3 → NOT_BUILT → v2 not required
    ├── Active: v1 engineering implementation; confidence NOT_CALIBRATED; EV NOT_CALCULATED
    └── Handoff: remain in Stage 6; collect valid closed outcomes before calibration promotion

### Eight SLRP elements

1. **Objective:** calibrated confidence, falsification and net EV governance.
2. **Acceptance:** 60/20/20 chronological split; minimum 250 observations under the current conservative implementation guard; both classes in each split; validation-only model selection; untouched OOS Brier improvement; all costs explicit.
3. **v1:** Platt vs isotonic, path/regime isolation and strict as-of cutoff.
4. **Diagnosis:** D1, no real closed-outcome ledger.
5. **v2:** not built; only after a real v1 FAIL and diagnosis.
6. **v3:** not built; only after a real v2 FAIL and diagnosis.
7. **Escalation:** keep probability and EV disabled until valid outcome data exists; if v1 later fails on measured evidence, diagnose D1–D6 before a challenger.
8. **Budget:** maximum three versions; no parameter-only rewrite; no threshold relaxation.

## 7. Five-question self-critique

1. **Future data used?** No. Calibration excludes outcomes closed at or after the current decision timestamp; a future-row unit test passes.
2. **Parameters tuned on test?** No. Calibrator selection is validation-only; OOS is not used for selection.
3. **Costs included?** The EV implementation requires fee, slippage and funding in R units. Real cost evidence is absent, so EV is not calculated.
4. **No-signal reporting?** Yes. BTC and ETH both report NO_QUALIFIED_SETUP, NOT_CALIBRATED and NOT_CALCULATED.
5. **Weakest assumption?** Stage 5 scores and market regime remain proxy inputs, and there is no closed-outcome sample to demonstrate probability reliability.

## 8. Decision

Stage 6 has passed its current C++ engineering, schema and Telegram delivery checks. It has **not** passed statistical acceptance. The correct status is BLOCKED / INSUFFICIENT_EVIDENCE, not PASS.

Do not advance to Stage 7 yet. The next valid Stage 6 action is to accumulate real, immutable closed outcomes from eligible candidates, resolve each with a pre-registered outcome rule, record all costs, and rerun the same frozen calibration pipeline. No synthetic test fixture may enter the production outcome ledger.
