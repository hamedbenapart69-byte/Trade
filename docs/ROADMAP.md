# CFSS Roadmap — V18.2

**Controlling source:** owner-accepted `UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER`  
**Status snapshot:** 2026-11-21  
**Production language:** C++ (current verified toolchain: C++20)  
**Delivery:** Telegram only  
**Execution:** manual trading only; automated orders are forbidden.

This roadmap supersedes the legacy orchestration/control-plane and V5 dashboard roadmap for the active Crypto Futures Signal System. Historical material remains available for audit but does not define the production path.

## Stage acceptance

| Stage | Scope | Current disposition | Evidence |
|---|---|---|---|
| 0 | Full architecture and design | Owner-accepted V18.2 is controlling | V18.2 master source |
| 1 | C++ end-to-end L1/L2/L3, C10, Telegram outbound/inbound | **PASS** | [Stage 1 SLRP](evidence/stage1-slrp-report.md) |
| 2 | LFS resilience | **PASS via v2**; PROXY / NOT_CALIBRATED | [Stage 2 SLRP](evidence/stage2-lfs-slrp-report.md) |
| 3 | NSS resilience | **PASS via v2**; PROXY / NOT_CALIBRATED | [Stage 3 SLRP](evidence/stage3-nss-slrp-report.md) |
| 4 | Liquidity zones and market phase | **PASS via v1**; rule-based proxy | [Stage 4 SLRP](evidence/stage4-liquidity-phase-slrp-report.md) |
| 5 | Independent LRT/NMT candidate engines | **PASS for candidate generation**; NOT_CALIBRATED and non-actionable | [Stage 5 SLRP](evidence/stage5-dual-engines-slrp-report.md) |
| 6 | Meta-cognition, calibration and net EV | **BLOCKED / NOT_CALIBRATED** | [Stage 6 SLRP](evidence/stage6-meta-cognition-slrp-report.md) |
| 7 | Consensus, Shadow risk and manual execution gate | **BLOCKED / FAIL-CLOSED** | [Stage 7 SLRP](evidence/stage7-risk-gate-slrp-report.md) |
| 8 | Plan A backtest and walk-forward | GATED: Stage 7 must PASS first | V18.2 stage rules |
| 9 | Plan B cross-sectional factor model | GATED: Stage 8 handoff and stage dependencies | V18.2 stage rules |
| 10 | Plan C robust ensemble | GATED: prior stage approvals | V18.2 stage rules |
| 11 | Plan H Daily Signal Factory | GATED: prior stage approvals | V18.2 stage rules |
| 12 | Paper/Shadow observation | GATED: required strategy and risk acceptance | V18.2 stage rules |
| 13 | Meta-allocator | GATED: minimum 180 days and 100 trades per path | V18.2 stage rules |
| 14 | Innovation fallback | Triggered only by registered SLRP failure conditions | V18.2 Innovation Protocol |
| 15 | Final decision | GATED: all required OOS and operational evidence | V18.2 stage rules |

## Active blockers

1. **Stage 6 calibration:** current cohorts do not have sufficient independent outcome evidence. Probability and EV remain `NOT_CALIBRATED` / `NOT_CALCULATED`.
2. **Cost provenance:** persistent Shadow outcomes must contain valid fee, slippage and funding values with source provenance. Missing costs remain `UNAVAILABLE`; zero-cost substitution is forbidden.
3. **Stage 7 risk basis:** no owner-approved frozen Shadow NAV and per-trade risk basis exists. The system must not infer portfolio percentages from R-multiples or user account data.
4. **Open Shadow positions:** a filled pending candidate without a valid mark-to-market and cost record keeps the risk snapshot `UNAVAILABLE`.
5. **Scheduled persistence/delivery:** a verified Stage 6 scheduled run failed at the Git persistence pathspec after compute; [PR #170](https://github.com/hamedbenapart69-byte/Trade/pull/170) contains the hotfix and has passing PR checks, but still requires owner-controlled merge and a successful subsequent scheduled run.

## Release rules

- A stage advances only after its acceptance criteria pass with real evidence.
- A test fixture proves code behavior, not live provider or Telegram operation.
- Every path/profile/generator keeps independent logic, ledgers, calibration and performance reporting.
- No threshold, risk control, data-quality rule or acceptance criterion is relaxed to create more signals.
- No v2/v3 rewrite without a measured prior-version failure and a specific diagnosis; maximum three versions.
- No candidate becomes actionable while calibration, EV, costs or risk evidence is unavailable.
- The user receives signals through Telegram only. No dashboard or external account connection is required.
- No merge to production, deployment or final release without explicit owner approval.

## Engineering branches in progress

- [PR #169 — Stage 7 Shadow risk snapshot v2](https://github.com/hamedbenapart69-byte/Trade/pull/169): implementation and live validation; not merged.
- [PR #170 — Stage 6 persistence hotfix](https://github.com/hamedbenapart69-byte/Trade/pull/170): scheduled-workflow pathspec correction; not merged.
- [PR #171 — V18.2 documentation alignment](https://github.com/hamedbenapart69-byte/Trade/pull/171): README and operational documentation; not merged.

A PR being open or its CI passing does not mean the change is active on `main`.
