# STAGE 6 — META-COGNITION / CALIBRATION / EV

**Canonical source:** V18.2  
**Active candidate:** v2 (engineering changes committed; validation pending)  
**Overall status:** BLOCKED / NOT_CALIBRATED / NO_SIGNAL_PROMOTION  
**Production release:** NOT APPROVED

## 1. Objective

For each independent path, regime, data class, profile and score-model version:
- Preserve the registered hypothesis and falsification condition.
- Convert raw scores into probabilities only after independent chronological calibration.
- Calculate net EV only when calibrated probability, outcome definitions and every material cost component are valid and provenance-backed.
- Keep no-setup states non-actionable, even when historical cohort metrics are positive.

## 2. Acceptance criteria

### Statistical and calibration controls
- Cohorts are isolated by path, regime, data class, profile and score-model version.
- V18.2 does not prescribe a fixed minimum calibration count or a 60/20/20 calibration split. The current 250-row floor, 100/30/50 split floors and 60/20/20 partition are provisional engineering guards only. They are not canonical requirements and cannot independently establish PASS.
- The v2 implementation estimates a cohort-specific required OOS effective sample size from validation-only maximum-of-one-way-cluster-SE uncertainty proxy. Provisional assumptions: minimum Brier improvement target 0.01, two-sided alpha 0.05 and power 0.80. The estimate is an engineering approximation and remains labelled PROVISIONAL.
- The provisional formula is `N_OOS_eff = ceil(((z_0.975 + z_0.80) * s_validation / 0.01)^2)`, where `s_validation` is the maximum-of-one-way-cluster-SE standard-deviation proxy estimated on validation data only.
- OOS effective sample size must meet the calculated requirement. The 95% cluster uncertainty interval using the maximum of separate one-way cluster SEs for paired OOS Brier improvement must have a lower bound strictly above zero.
- Both outcome classes must be present in each chronological split. Report raw count, effective sample size, cluster counts, confidence intervals, period and symbol/day distributions.
- OOS data must not be used to select the calibrator or tune parameters. The selected Platt/Isotonic method is chosen using validation only.

### Costs and EV
- V18.2 reference fee: 0.04% where applicable, explicitly an assumption, not a universal venue fee.
- Current fee model: 0.04% per side, `ASSUMED`, with owner-decision reference.
- Current slippage model: 0.10% per side, `PROXY`, fixed-rate assumption and not measured order-book impact.
- Funding: timestamped public funding history, direction-adjusted. Incomplete funding coverage leaves total costs `UNAVAILABLE`.
- Every `PROXY` cost row must contain numeric fee/slippage/funding R values and complete model/source provenance. Any missing or mislabelled provenance blocks the ledger.
- `UNAVAILABLE` rows retain null cost values. `REAL` cost status is rejected until a real-cost implementation and provenance contract exist.
- EV is `NOT_CALCULATED` when probability or any material cost is unavailable. Calibrated net EV at or below zero is `NO_TRADE`; positive EV remains research-only.

### Safety and release
- Outcomes remain `HYPOTHESIS_PROXY` and `NOT_EXECUTED`.
- No exchange account, user balance, private trading key, order placement or order execution.
- No signal promotion from `NO_QUALIFIED_SETUP`.
- Stage 7 remains fail-closed until its independent shadow-risk inputs and Stage 6 requirements pass.

## 3. Three-layer contract

- **L1 DATA:** immutable closed-outcome ledger, source run/scan/L1 hashes, resolution bars, funding observations, data class and coverage.
- **L2 COMPUTE:** cohort filtering, chronological calibration, validation-only model selection, clustered OOS Brier comparison, power estimate and provenance-gated EV.
- **L3 DELIVERY:** Telegram-only user-facing status. Engineering artifacts remain internal; no browser dashboard is a user dependency.

## 4. v1 — FAIL (D1 + D3), observed evidence

GitHub Actions run `44726308730` completed the integrated Stage 6 + Stage 7 workflow and delivered Telegram message `75`.

Observed from the signals branch runtime artifacts:
- Source run: `okx-cpp-1795173574873`.
- Meta-Cognition decision timestamp: `1795172400000`.
- Closed outcome ledger: 5 rows.
- BTC/USDT:USDT and ETH/USDT:USDT both reported `NO_QUALIFIED_SETUP`, `NOT_CALIBRATED`, `NOT_CALCULATED`.
- All 5 historical outcomes had `cost_status=UNAVAILABLE` and null fee/slippage/funding values.
- The v1 calibration refresh was conditional on a current candidate, so historical cohort calibration was not surfaced for no-setup symbols.
- Stage 7 reported `risk_snapshot_status=UNAVAILABLE`, zero actionable candidates and `trade_execution_allowed=false`.

### Specific diagnosis
- **D1 — Data:** only 5 closed outcomes existed. Effective independent sample size and uncertainty were not sufficient to establish calibration.
- **D3 — Implementation:** calibration refresh was incorrectly inside the current-candidate branch.
- **D3 — Cost/provenance:** cost fields remained null even when public funding history was available in the source pipeline; total costs therefore remained unavailable and EV could not be calculated.

## 5. v2 — Continuous calibration + auditable shadow costs

**Changed assumption:** calibration monitoring is continuous for a valid score/regime and available ledger; candidate promotion is a separate, stricter path.

Committed changes:
1. Extract continuous calibration evaluation and refresh it even when the current state is `NO_QUALIFIED_SETUP`.
2. Keep a no-setup symbol non-actionable regardless of historical cohort calibration.
3. Keep the 250-row and chronological split thresholds explicitly provisional; remove their false attribution to V18.2.
4. Estimate the required OOS effective sample size from validation-only cluster uncertainty; require the OOS effective sample to meet it.
5. Add a paired OOS Brier-improvement confidence interval and require its 95% lower bound to be greater than zero.
6. Expose the provisional target effect, alpha, power, method, validation uncertainty and required OOS effective sample in the Meta-Cognition output.
7. Distinguish fee `ASSUMED` from slippage `PROXY`; record the fee decision reference, slippage method/status, funding source, source run/scan/L1 hash and source snapshot as-of timestamp.
8. Enforce cost provenance both in the shadow ledger runtime and again in the Meta-Cognition parser before EV computation.
9. Add negative tests for missing hashes/methods/assumption references, stale cost snapshot time, mislabelled fee, missing numeric cost components and unsupported `REAL` cost status.
10. Preserve null cost values when total cost coverage is unavailable.

**Validation status (latest head 3c6cbb46a1f51d4dd4d7622d0d6970afd7ed598e):** C++ build, CTest, schema validation and the Stage 6 PR live-validation workflow completed successfully in GitHub Actions run 44754721823. This verifies execution and artifact contracts, not statistical calibration or release readiness.

Live evidence from run 44754721823:
- OKX reported 546 total instruments, 531 live USDT-suffix swaps, 337 linear-or-unspecified contracts, 194 excluded non-crypto instruments and 60 eligible instruments. The run selected 60, below the approximate 100-symbol target; the eligibility filter was not relaxed.
- All 60 selected instruments had 15m resolution data available. OHLCV, funding and OI histories were collected from the public OKX source/cache; per-instrument coverage varied with listing history. Example BTC/ETH: 17,532 hourly candles, 90 funding observations and 720 OI observations. Newer instruments had shorter OHLCV histories.
- Shadow tracker: 1 registered candidate, 0 resolved in this run, 2 pending candidates, 5 total ledger outcomes. Five prior outcomes were backfilled with cost `PROXY`; zero remained `UNAVAILABLE`. This is cost coverage, not real measured execution cost.
- Meta-Cognition generated successfully with 5 outcomes. Confidence remained `NOT_CALIBRATED`; no probability calibration or net EV promotion was established. Current no-setup states remained non-actionable. SUI and TRUMP appeared as NMT candidates but remained uncalibrated.
- Stage 7 produced 2 candidate rows, both blocked; `risk_snapshot_status=UNAVAILABLE`, `actionable=0`.
- Telegram report preparation was schema/runtime checked only. No Telegram message was sent by this PR validation, and no persistent signals branch was written.

The workflow result is therefore **engineering execution PASS / statistical acceptance BLOCKED / production release NOT APPROVED**. Five outcomes cannot establish the required chronological calibration, OOS Brier improvement or validation-derived sample power. The L1 target shortfall and single-provider live collection remain open data/provider coverage issues.

## 6. v3

Not built. R11 prohibits v3 unless v2 first records a real FAIL with specific evidence and a D1–D6 diagnosis.

## 7. Escalation

- If v2 build, tests or schema validation fail: diagnose the exact compiler/test/schema evidence first.
- If live data or cost provenance is incomplete: keep the affected records `UNAVAILABLE`; do not substitute zero or fabricated values.
- If the validation-derived OOS sample requirement is not met: continue collecting eligible independent outcomes; do not relax the target effect, alpha, power or OOS confidence gate.
- If v2 fails after its actual runtime test: record the specific D-code, then consider v3 under R1–R11.
- If v1/v2/v3 fail or the applicable gate remains blocked, use the V18.2 Innovation Protocol; no silent threshold changes.

## 8. Budget

Maximum three versions: v1, v2, v3. No parameter-only rewrite, no test-set tuning, no retroactive criteria relaxation. Current active candidate is v2; v3 is not authorized until a real v2 FAIL.

## 9. Real runtime samples (v1 baseline, not v2 validation)

| Symbol | Path | Direction | Raw score | Resolution | Gross result | Cost status | Execution |
|---|---|---:|---:|---|---:|---|---|
| BTC/USDT:USDT | PLAN_A_NMT | SHORT | 0.4899 | TARGET | +0.8197R | UNAVAILABLE | NOT_EXECUTED |
| PUMP/USDT:USDT | PLAN_A_NMT | SHORT | 0.5244 | STOP | -1.0000R | UNAVAILABLE | NOT_EXECUTED |

These are historical shadow hypotheses, not executed trades or evidence of profitability. Their costs were unavailable; neither row can support net EV.

## 10. Five-question self-critique

1. **Future data used?** The calibrator filters out outcomes with `closed_at_ms >= as_of_ms`, and a future-row unit test exists. **OPEN:** the previously observed difference between the decision timestamp and later universe-fetch timestamp still needs an explicit event-time/processing-time contract before release.
2. **Parameters tuned on test?** The intended flow selects the calibration method on validation and evaluates it on chronological OOS. The latest implementation still requires completed CI and a reproducible live evidence run.
3. **Costs included?** Cost logic and provenance gates are implemented in the candidate branch, but the latest live ledger still has unavailable costs. **FAIL for release.**
4. **No-signal reporting?** Yes in the observed v1 runtime: BTC and ETH reported `NO_QUALIFIED_SETUP`; the no-setup state is explicitly kept non-actionable in v2.
5. **Weakest assumption?** The raw LFS/NSS inputs remain PROXY; the 0.01 Brier target, alpha 0.05 and power 0.80 are provisional engineering assumptions; slippage is a fixed PROXY, not measured impact.

## 11. Active version and handoff

- **Active:** v2 engineering candidate.
- **Stage 6:** BLOCKED pending adequate independent cohort outcomes, valid chronological train/validation/OOS splits, power/OOS assessment and supported cluster-uncertainty methodology. Latest-head build, CTest, schemas and one live PR run are complete.
- **Stage 7:** remains BLOCKED / fail-closed while its internal shadow-risk snapshot is unavailable.
- **Next action:** continue collecting independently resolved, cost-provenance-backed shadow outcomes through the production scheduled pipeline; verify the exact cohort, effective sample sizes, cluster counts, OOS confidence interval and Brier improvement before any calibration claim. Investigate provider fallback and the 60/100 eligible-universe shortfall without relaxing liquidity or contract-equivalence rules.
- **Merge / production release:** not approved.
