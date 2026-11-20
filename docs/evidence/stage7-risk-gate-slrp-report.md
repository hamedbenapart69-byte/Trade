# STAGE 7 — CONSENSUS, RISK, MANUAL EXECUTION GATE (V18.2)
**Implementation:** risk-policy core v1 added; CI acceptance pending.
**Stage status:** BLOCKED — upstream paths and real risk inputs unavailable.
**Execution:** permanently forbidden by this system; manual review only.

## Scope
- Fail-closed risk gate: Golden Rule, candidate existence, actionability prohibition, REAL data, liquidity, calibration, positive net EV, explicit costs and valid risk snapshot.
- G7 daily loss >=5% or weekly loss >=10% blocks.
- Portfolio drawdown >20% blocks.
- G5: 3+ correlated open exposures blocks.
- No order endpoint, account connection, credentials or execution permission.

## Three layers
- L1: Portfolio risk snapshot is UNAVAILABLE. Public market data cannot prove account exposure, losses, or drawdown; no account connector is allowed.
- L2: deterministic C++ policy gate and tests.
- L3: Telegram-only intended. No delivery triggered without valid inputs.

## SLRP
- v1: policy core and deterministic unit tests; CI verifies C++ build, full CTest, JSON schema, static policy guards.
- Acceptance: engineering CI pending; live-input acceptance blocked.
- Diagnosis: D1 missing risk snapshot/calibration/EV; D2 user portfolio values cannot be inferred.
- v2/v3 NOT BUILT; no measured v1 failure (R11).
- Active: v1 policy core, operationally blocked.
- Escalation: no promotion until valid non-account-connected risk snapshot and Stage 6 calibrated evidence exist.
- Budget: maximum three versions, no threshold relaxation.

## Self-critique
1. Future data? Gate receives no time-series; upstream must be as-of.
2. Parameters tuned? None.
3. Costs? Mandatory explicit.
4. No-candidate reporting? Explicit block reason.
5. Weakest assumption? Risk inputs are unverified without account data; user-provided values would require validation.
