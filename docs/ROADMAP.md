# CFSS Roadmap — V21.1

**CONTROLLING SOURCE SET:** MASTER SOURCE V21.0 + V21.0 Execution Protocol Addendum + V21.1 Binding Data Federation & Nine-Asset Universe Addendum. M1 and Master Owner Mission are governing owner directives. V19.0 and V18.2 are superseded historical archives.  
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

## V21.1 data-federation and universe constraints

- Exactly nine production assets: BTC plus eight tradable assets; candidate selection must be evidence-based, not assumed from a hardcoded list.
- Thirteen selection criteria are mandatory: independent market-wide liquidity; stable spot volume; compatible derivatives instrument; historical OHLCV depth; funding/OI coverage; listing age and delisting history; survivorship bias; volatility/regime representation; correlation/redundancy; provider diversity; instrument identity reliability; data quality/operational reachability; statistical sample sufficiency.
- At least two independent, fresh, license-eligible providers must overlap on the required market-wide fields. HTTP 200 is insufficient evidence of contractual eligibility; inability to open a provider website from the owner's device is not itself grounds for rejection.
- Candidate universe artifacts are provisional until the 13-criterion evidence screen and explicit owner approval are complete. No automatic production freeze is permitted.
- Current C++ candidate smoke is engineering evidence only. It does not constitute production Stage 1 acceptance while provider quorum, spot-volume evidence, delisting evidence and owner-approved freeze are incomplete.

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
2. **Provider independence:** the latest live federation probe has one qualified market-wide provider only. CoinRanking and CoinMarketCap authenticated keys are not configured; CoinGecko is disabled under published provider terms. Binance Vision historical archives are reachable for research, but this does not substitute for a second independent market-wide provider.
4. **V21 Stage 1:** the C++ build/unit tests and candidate L1 smoke have passed on the feature branch, with candidate L2 states fail-closed as MARKET_DATA_DEGRADED and zero actionable signals. This is not a production PASS: the nine-asset set is not frozen, provider quorum is incomplete, and Telegram live inbound has not been revalidated in the current Stage 1 run.
5. **Universe screen:** spot-volume history and complete delisting history are unavailable in the current L1 artifact; market-wide per-asset liquidity cannot be cross-verified with only one qualified provider. The evidence screen must remain PROVISIONAL_NOT_FROZEN.
6. **Momentum + Cash research:** spot proxy and USD-M futures research are separate from production paths. A single pre-registered strategy cannot produce a valid PBO estimate; Brier is not applicable without probability forecasts. Any backtest remains exploratory until cost semantics are owner-approved and OOS gates are satisfied.
7. **Cost semantics:** 0.04% commission and 0.02% slippage one-way versus round-trip interpretation remains open. Conservative per-side sensitivity may be shown as ASSUMED, but cannot be treated as owner-approved gate evidence.

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
- Rejected LRT/NMT/VTM workflows and their legacy LFS/NSS/liquidity-phase precursor/report jobs are permanently disabled at job level. CI fails if any denylisted workflow is missing a literal job-level `if: false`.
- The controls in this branch are proposals until the owner merges this PR; main remains unchanged by this branch.
