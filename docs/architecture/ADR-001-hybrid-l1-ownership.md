# ADR-001: Temporary Python L1 Ownership with Authoritative C++ L2/L3

- **Status:** APPROVED BY PROJECT OWNER
- **Effective date:** 2026-11-17
- **Scope:** Stage 1 Hybrid implementation
- **Authority:** This decision amends only the conflicting L1 ownership clauses in V18.2. All unrelated V18.2 requirements remain in force.

## Context

V18.2 §§43.1–43.2 assign production data acquisition and the remaining implementation to C++. The repository already contains Python public-market-data acquisition and historical collection components. Rewriting those components before a verified replacement would add migration risk and delay the Stage 1 vertical slice.

## Decision

A temporary Hybrid boundary is approved:

1. **Python L1:** public market-data acquisition, provider acquisition fallback, and export of raw observations plus provenance into the versioned L1 contract.
2. **C++ L2:** independent contract/schema and data-quality validation, admission, normalization, feature/strategy computation, C10 state selection, risk/gates, and immutable signal/artifact production.
3. **C++ L3:** Telegram message construction, outbound delivery, inbound updates, idempotency, receipts, retry/recovery, and delivery audit.

Python is not permitted to calculate production signals, choose C10 states, evaluate strategy gates, apply risk rules, or decide release eligibility.

## Explicit precedence

For Stage 1, this ADR supersedes only the V18.2 wording that requires Python to be absent from production L1 acquisition. It does not supersede:
- C++ ownership of all production compute and delivery;
- zero-cost and GitHub Actions constraints;
- Telegram-only user delivery;
- no exchange account credentials or order execution;
- all C10 states, statistical gates, SLRP, Innovation Protocol, and data-integrity rules;
- the requirement for two consecutive complete three-layer Stage 1 runs.

Long-term migration of production-critical L1 responsibilities to C++ remains the target. Python L1 is a temporary exception, not a permanent entitlement. Removing or replacing it requires verified C++ parity, shadow/differential evidence, rollback readiness, and explicit retirement approval.

## Contract boundary

Python emits a versioned JSON contract. It preserves nulls, exact instrument identity, timestamps, candle completion, source/provider provenance, coverage, availability, and errors. C++ validates the contract independently and fails closed on incompatible schema or invalid data.

## Safety

A proxy, missing, stale, partial, or uncalibrated input cannot be upgraded into an actionable signal by Python. An actionable signal requires all relevant C++ gates, calibrated confidence, and positive net EV.

## Implementation status

This ADR records an approved architecture decision. It does not assert that Stage 1 is implemented or passed. Implementation evidence is maintained separately in the Stage 1 report and run ledger.
