# ADR-005 — Self-Healing Reliability and Controlled Migration

**Status:** PROPOSED  
**Scope:** Operational recovery, provider health, observability and Python-to-C++ migration

## Context
Self-healing must restore service safely. It must not weaken trading criteria, invent data, change strategy thresholds or turn an operational outage into a market signal.

## Decision

### Reliability ownership
A reliability subsystem may monitor and recover operational components:
- provider endpoint health and request latency;
- acquisition completeness and stale data;
- contract/schema rejection;
- L2 compute failure and artifact publication;
- Telegram API outage, retry backlog and ambiguous delivery;
- scheduler delay, repeated failures and resource limits.

It must not alter:
- LFS/NSS formulas or thresholds;
- strategy hypotheses, path gates or risk limits;
- C10 status requirements;
- minimum liquidity, correlation or statistical acceptance criteria.

### Failure classification
Every failure is classified and logged as one of:
- D1 Data: missing, stale, malformed, incomplete or conflicting data;
- D2 Assumption: unsupported provider equivalence or invalid model premise;
- D3 Implementation: code, contract, build or runtime defect;
- D4 Threshold/Calibration: threshold or calibration failure supported by evidence;
- D5 Regime: model/path is outside its declared regime;
- D6 Expectations: requested outcome is not supported by the approved acceptance criteria.

An operational failure must not be relabeled as a strategy rejection, and a strategy rejection must not be treated as a provider outage.

### Recovery
- Bounded retries with exponential backoff and jitter where appropriate.
- Circuit breakers for repeated provider or Telegram failures.
- Fallback only when exact instrument identity and data semantics are equivalent.
- Preserve per-field provenance and quality labels across fallback.
- Missing values remain null/UNAVAILABLE; no zero-fill or synthetic replacement.
- Recovery must never relax strategy or risk gates.
- Repeated failure escalates to a visible degraded state and a retained evidence record.

### Controlled Python-to-C++ migration
For every module:
1. Inventory module, callers, dependencies, side effects and ownership.
2. Freeze the input/output contract and golden fixtures.
3. Document current behavior and known failure modes.
4. Implement the C++ replacement behind the same versioned contract.
5. Run unit, contract, integration, regression, causality, differential, golden, property, reliability and sanitizer tests as applicable.
6. Compare outputs and explain every material difference.
7. Run shadow/differential mode before switching ownership.
8. Preserve rollback to the prior module until acceptance passes.
9. Retire old code only after evidence-backed PASS and explicit approval.

Compilation alone is never migration PASS.

## Current implementation
- C++ L3 uses bounded retries and explicit ambiguous delivery states.
- Python L1 remains the approved temporary acquisition/export exception.
- Full provider circuit breakers, cross-provider exact-equivalence fallback and automated health recovery remain pending.
- No legacy Python module or branch has been deleted.

## Acceptance
- Injected failures are classified correctly and recovered within documented bounds.
- Fallback cannot cross contract identity or data-type boundaries.
- Recovery cannot change trading thresholds, gates or risk settings.
- Each migrated module has differential evidence, rollback proof and owner approval before retirement.

## Prohibitions
- No silent fallback to spot for futures data.
- No stale or missing data treated as current or numeric zero.
- No automated threshold relaxation.
- No destructive migration without verified replacement and rollback.
