# CFSS Roadmap — V21.0

**SOLE CONTROLLING AUTHORITY:** owner-accepted MASTER SOURCE V21.0 + V21.0 Execution Protocol Addendum. V19.0 and V18.2 are superseded historical archives.  
**Status snapshot:** 2026-11-23  
**Production language:** C++  
**Delivery:** Telegram only  
**Execution:** manual only; private exchange accounts, trading keys and automated orders are forbidden.

This roadmap records the V21 reset. V18.2 implementation records remain historical and are not inherited as V21 stage acceptance.

## V21 stage acceptance

| Stage | Scope | Current disposition | Evidence |
|---|---|---|---|
| 0 | Architecture and source authority | **PASS — OWNER ACCEPTED** | Architecture Design V1; Source Register update on V21 branch |
| 1 | C++ L1/L2/L3 foundation, contracts, safe no-signal reporting and Telegram | **IN PROGRESS** | [V21 Stage 1 SLRP](evidence/v21-stage1-slrp-plan.md); CI/live evidence pending |
| 2 | Provider independence, data freshness and fallback equivalence | NOT STARTED | Gated by Stage 1 |
| 3 | Market-regime classification and independent short-squeeze safety | NOT STARTED | Gated by Stage 2 |
| 4 | Independent research hypotheses and falsification | NOT STARTED | Gated by Stage 3 |
| 5 | Walk-forward and OOS validation | NOT STARTED | Gated by Stage 4 |
| 6 | Calibration, costs and net expectancy | NOT STARTED | Gated by Stage 5 |
| 7 | Risk gate and signal lifecycle | NOT STARTED | Gated by Stage 6 |
| 8 | Shadow operation and operational reliability | NOT STARTED | Gated by Stage 7 |
| 9 | Final evidence-based decision | NOT STARTED | Gated by Stage 8 |

A stage may PASS only when its numerical criteria and L1/L2/L3 requirements are independently evidenced. A passing compile or fixture test does not prove live data, Telegram delivery, or trading edge.

## V21 hard constraints

- LRT, NMT and VTM are REJECTED. No cosmetic rename, parameter adjustment, timeframe change, indicator substitution or simple ensemble may recycle them.
- Production code is C++; Python is limited to permitted research and auxiliary validation.
- Public market data only; no exchange-account connection, private trading key, or order execution.
- Telegram is the sole user-facing delivery channel.
- No paid service or paid trial.
- Every stage completes L1 Data, L2 Compute and L3 Delivery.
- REAL / PROXY / UNAVAILABLE / DEGRADED provenance must be explicit.
- V21 statistical gates are fixed: OOS Win Rate >50%, PF >1.40, PBO <0.40, DSR_Z >1.00, with no look-ahead, leakage, survivorship bias or invalid execution assumptions.
- Commission 0.04% and slippage 0.02% must be interpreted explicitly as one-way or round-trip before any backtest; until then, dependent validation is BLOCKED.
- Signal confirmation is executed at the next candle Open in simulation by default, with costs.
- No strategy is actionable while confidence is NOT_CALIBRATED or net EV is unavailable/non-positive.
- Scalp remains disabled or shadow-only until measured end-to-end latency, data freshness and operational reliability pass its dedicated gate.
- No next stage without explicit owner approval.

## Current V21 blockers

1. **Rejected legacy workflows:** this branch applies job-level `if: false` to all identified LRT/NMT/VTM execution paths and adds a CI regression guard. These controls become effective on the default branch only after this PR is reviewed and merged.
2. **Provider independence:** the current production collector has an implemented OKX futures adapter; Bybit/Binance were previously observed unavailable from the runner, and other adapters are not equivalence-tested. No fallback is assumed.
4. **V21 Stage 1:** V18.2 evidence is historical. V21 manifest/contract migration and new live acceptance runs remain pending.
5. **Cost semantics:** one-way versus round-trip interpretation is open and blocks strategy backtesting.

## Historical V18.2 records

The following references are preserved for audit only and do not imply V21 acceptance:

- V18.2 Stage 1 evidence: evidence/stage1-slrp-report.md
- V18.2 Stage 2 LFS evidence: evidence/stage2-lfs-slrp-report.md
- V18.2 Stage 3 NSS evidence: evidence/stage3-nss-slrp-report.md
- V18.2 Stage 4 liquidity/phase evidence: evidence/stage4-liquidity-phase-slrp-report.md
- V18.2 Stage 5 dual-engine evidence: evidence/stage5-dual-engines-slrp-report.md
- V18.2 Stage 6 calibration evidence: evidence/stage6-meta-cognition-slrp-report.md
- V18.2 Stage 7 risk-gate evidence: evidence/stage7-risk-gate-slrp-report.md

A legacy PR being open or its CI passing does not make it part of the V21 production architecture. No legacy workflow is presumed safe to run merely because it remains in Git history or on main.


## Source archive and workflow governance

- V21.0 is the sole controlling specification. V19.0 is preserved verbatim under `docs/archive/superseded/`; its former constitution path is an archive pointer.
- V18.2 is recorded as superseded with its owner-provided SHA-256 in `docs/archive/superseded/V18.2_ARCHIVE_RECORD.md`. The exact source bytes were not present in the repository at the start of this PR; the archive record does not claim a byte-identical repository copy.
- Rejected LRT/NMT/VTM workflow jobs are permanently disabled at job level. CI fails if any listed rejected workflow is missing a literal job-level `if: false`.
- The controls in this branch are proposals until the owner merges this PR; main remains unchanged by this branch.
