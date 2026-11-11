# Research Tool Adoption Assessment — purgedcv

**Date:** 2026-11-10  
**Decision:** RESEARCH HARNESS CANDIDATE; NOT A PRODUCTION DEPENDENCY  
**Repository candidate:** https://github.com/eslazarev/purged-cross-validation  
**Inspected release metadata:** 0.1.12  
**License declared by upstream pyproject:** MIT  
**Maturity declared upstream:** Alpha  
**Python requirement:** >=3.11  
**Declared core dependencies:** NumPy >=1.24, pandas >=2.0, scikit-learn >=1.3, SciPy >=1.10

## 1. Why it is relevant

The package exposes time-aware WalkForwardSplit, PurgedKFold, CombinatorialPurgedCV, CombinatoriallySymmetricCV, purge/embargo primitives, path reconstruction, PSR, DSR, and PBO. These are relevant to unresolved validation risks: overlapping event horizons, selection bias, multiple testing, and the need to distinguish robust candidates from overfit ones.

Upstream API/source inspected:
- https://github.com/eslazarev/purged-cross-validation
- https://raw.githubusercontent.com/eslazarev/purged-cross-validation/main/pyproject.toml
- https://raw.githubusercontent.com/eslazarev/purged-cross-validation/main/src/purgedcv/_pbo.py
- https://raw.githubusercontent.com/eslazarev/purged-cross-validation/main/src/purgedcv/_purge.py
- https://raw.githubusercontent.com/eslazarev/purged-cross-validation/main/src/purgedcv/_metrics.py

## 2. Why it must NOT be added to the live runtime yet

The current signal_autopilot/research/mvp_validation.py is a deterministic rule-based walk-forward harness. It produces a list of completed trade records. It does not yet produce the required shared-time-axis matrix of per-period returns for multiple candidate configurations.

probability_of_backtest_overfitting() explicitly requires:
- A 2-D return matrix shaped (n_configs, n_obs).
- At least two independent candidate configurations.
- A shared observation timeline.
- Even n_splits and sufficient observations.
- Prediction/evaluation times supplied together when purge/embargo is required.

A single strategy's irregular sequence of trade outcomes is not a valid substitute for a synchronized per-period portfolio return matrix. Trades can overlap, differ in holding duration, and create unequal capital exposure. Feeding raw trade-level returns into PBO would distort the time axis and could produce a meaningless result.

Likewise, DSR requires a defensible number of trials and the variance of Sharpe estimates across those trials. The current repository does not yet expose a complete, immutable experiment registry that can establish those inputs. Guessing n_trials or var_sharpe is prohibited.

The package's walk-forward splitter is not a replacement for the existing chronological evaluation. Purge and embargo behavior must be configured from the actual prediction and outcome horizons. A generic 48h/7d value must not be copied without matching it to the labels and holding periods under test.

## 3. Correct adoption plan

### Phase A — Build the required evidence contract first

For every strategy candidate and evaluation timestamp, persist:
- candidate_id and immutable strategy version/hash;
- symbol, market, timeframe, and decision timestamp;
- prediction timestamp and evaluation/label end timestamp;
- portfolio allocation and position state;
- per-period gross return;
- fee, spread, slippage, funding, and other cost components;
- per-period net return;
- missing-data and execution-quality labels;
- trial registry record including all attempted candidates, parameter sets, and selection decisions.

Return series must be aligned to a common calendar and frequency. Missing periods must be handled by a documented policy, not silently filled with zero. Portfolio construction, overlapping positions, capital allocation, and cross-symbol correlation must be modeled explicitly.

### Phase B — Integrate in research-only environment

Create a separate research dependency file, not the live signal requirements. Pin the package version and transitive dependency ranges after compatibility testing under the repository's Python 3.12 workflow.

Run:
1. Purge/embargo unit tests with hand-computable event horizons.
2. Leakage tests proving that overlapping label windows are excluded.
3. Walk-forward splitter tests against the existing chronological split policy.
4. PBO tests using at least two deliberately distinct candidate return streams.
5. DSR tests with known trial counts and measured Sharpe dispersion.
6. Degenerate/short-sample tests that must return an explicit unavailable/error state rather than a fabricated score.
7. Reproducibility tests that preserve data, candidate, and trial hashes.

### Phase C — Independent verification

Compare package outputs against a small, independently implemented reference calculation on synthetic deterministic data. Validate assumptions, boundary behavior, tie handling, missing values, and time units.

Do not accept a metric merely because the library returns a number. Validate that its input matrix represents the strategy-selection process actually performed.

## 4. Decision

- **Use case:** research-only validation and audit tooling.
- **Production dependency:** REJECTED for now.
- **Reason:** current data contract does not provide valid synchronized candidate return matrices or a complete trial registry.
- **Next prerequisite:** design and test the candidate-period return matrix and immutable trial registry.
- **Promotion rule:** only after independent parity tests, CI success, and evidence that PBO/DSR inputs faithfully represent all candidate trials.

## 5. Important statistical boundary

PBO and DSR are not universal proof of strategy quality. They depend on the candidate search process, return construction, sample definition, dependence structure, and estimator assumptions. They supplement—not replace—chronological walk-forward testing, realistic costs, regime analysis, calibration, and paper/shadow evaluation.

A low PBO or high DSR calculated from an incomplete or misaligned experiment registry is not evidence of a genuine edge.

## 6. SLRP

**Objective:** establish whether purgedcv can improve validation reliability without contaminating production signal logic.

**Acceptance criteria:**
- Production requirements remain unchanged.
- Research adapter refuses to calculate PBO with fewer than two candidates.
- Trial count and candidate hashes are sourced from the immutable registry.
- Per-period net return series are aligned and finite.
- Prediction/evaluation horizons are explicit and tested.
- Purge/embargo removes known overlapping labels in deterministic tests.
- PBO/DSR match independent reference calculations within documented numerical tolerance.
- CI passes on Python 3.12.
- No production promotion before the above criteria pass.

**v1:** no integration; source/API and data-contract assessment only.  
**Diagnosis:** current backtest output is trade-level and lacks the shared period matrix and complete trial registry.  
**v2:** build a research-only return-matrix adapter after the data contract exists. Not authorized by this assessment until v1 prerequisites are met.  
**v3:** not designed; R11 requires an actual v2 failure before a third version is considered.  
**Active:** RESEARCH CANDIDATE / NOT INTEGRATED.  
**Escalation:** if reliable event-level inputs cannot be collected, mark PBO/DSR UNAVAILABLE rather than approximate them from irregular trade rows.  
**Budget:** maximum three versions.

## 7. Repository-specific observation

The current validation workflow at .github/workflows/mvp-validation.yml installs signal_autopilot/requirements.txt, fetches the isolated market-data branch's Parquet archive, and runs run_mvp_validation.py. The live strategy requirements currently include CCXT, HTTPX, PyArrow, python-telegram-bot, and Matplotlib; they do not include pandas, NumPy, scikit-learn, or SciPy explicitly.

The correct next move is to build the return/trial evidence contract and run the research dependency separately. Do not expand the production dependency graph merely to obtain additional metrics.
