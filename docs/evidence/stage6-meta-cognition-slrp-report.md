# STAGE 6 — META-COGNITION / CALIBRATION SLRP

**Canonical source:** V18.2  
**Current version:** v2 implementation pending CI and live verification  
**Release status:** NOT_CALIBRATED / NO_SIGNAL_PROMOTION

## Acceptance criteria

- Calibration is isolated by path, regime, data class, profile and score-model version.
- Minimum 250 eligible closed outcomes per calibration cohort.
- Chronological 60/20/20 train/validation/OOS split.
- OOS Brier improvement and clustered effective sample size requirements remain unchanged.
- Net EV is calculated only when fee, slippage and funding costs are all numeric and provenance-backed.
- Uncalibrated or non-positive EV never becomes actionable.
- Proxy costs and proxy outcomes remain explicitly labelled PROXY.
- No exchange account, user balance, trading key or order execution is used.

## v1 — FAIL (D1 + D3), evidence

GitHub Actions run `44726308730` executed the integrated C++ Stage 6 + Stage 7 workflow successfully and delivered Telegram message `75`.

Observed evidence:
- 60 eligible instruments were processed from the verified universe.
- The closed outcome ledger contained 5 outcomes.
- Required calibration minimum is 250; therefore no cohort can be calibrated.
- All 5 outcomes had `cost_status=UNAVAILABLE` and null fee, slippage and funding R values.
- The live Meta-Cognition output did not refresh historical calibration when the current symbol had no candidate. This is a code-path defect: calibration was called only inside the `candidate_status == CANDIDATE` branch.
- Stage 7 correctly remained fail-closed: risk snapshot UNAVAILABLE, candidate count 0, actionable count 0, trade execution disabled.

### Diagnosis

- **D1 — Data:** 5 eligible outcomes versus 250 required. No threshold relaxation is permitted.
- **D3 — Implementation:** calibration refresh was incorrectly conditional on a current candidate, so historical outcomes were not surfaced for no-setup symbols.
- **D3 — Implementation / cost provenance:** the shadow outcome tracker left all cost fields null even when public funding history was present. Consequently EV remained NOT_CALCULATED.

## v2 — Continuous calibration + conservative proxy cost model

**Changed assumption:** calibration is a continuous path/regime monitoring process, not an operation that runs only when a new candidate appears. Candidate promotion remains a separate, stricter branch.

Implemented changes:
1. Refresh calibration whenever a valid score and regime exist, including `NO_QUALIFIED_SETUP` symbols.
2. Never promote a no-setup symbol, even if its historical calibration is positive.
3. Backfill historical shadow outcomes when the current public funding history covers the complete holding interval.
4. Record a transparent proxy cost model:
   - Fee: 0.04% per side.
   - Slippage: 0.10% per side, conservative PROXY.
   - Funding: actual timestamped OKX public funding history, direction-adjusted.
   - All three costs are converted to R using the original entry-to-stop risk distance.
5. If funding coverage is incomplete, costs remain UNAVAILABLE; zero cost is never assumed.
6. Preserve `HYPOTHESIS_PROXY`, `NOT_EXECUTED` and `data_class=PROXY`.
7. Preserve the 250-outcome minimum and 60/20/20 split. No acceptance threshold is relaxed.

New provenance fields include cost model ID, fee/slippage assumptions, funding source, source run/scan IDs and source L1 hash.

**v2 validation:** pending C++ build, CTest, schema validation and a new live Stage 6 run.

## v3

Not built. R11 prohibits v3 unless v2 records a real FAIL with specific evidence.

## Active version and handoff

- Active engineering candidate: v2.
- Calibration status remains NOT_CALIBRATED until a path/regime cohort has at least 250 eligible outcomes and passes all OOS criteria.
- No BUY/SELL promotion, no exchange account access and no order execution.
- Stage 7 remains fail-closed until calibrated EV and an internal shadow-risk snapshot are both available.
