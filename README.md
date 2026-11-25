# Crypto Futures Signal System (CFSS)

**SOLE CONTROLLING AUTHORITY:** owner-accepted MASTER SOURCE V21.0 + V21.0 EXECUTION PROTOCOL ADDENDUM. V19.0, V18.2 and all earlier sources are superseded historical archives.  
**Production implementation:** C++ (current verified build: C++20)  
**User delivery:** Telegram only  
**Trading boundary:** manual trading only; the system never connects to a user's exchange account or places orders.

This repository contains the implementation and evidence for CFSS. Older orchestration, Python/V5 scanner, browser dashboard, email and Railway material may remain in Git history or legacy paths; they are not the controlling production architecture.

## Current architecture

The active system is divided into three layers:

1. **L1 — Data:** GitHub Actions workers acquire public market data and preserve provider, timestamp, coverage and hash provenance. The user's device and exchange account are not part of the data pipeline.
2. **L2 — Compute:** V21 Stage 1 currently validates data and emits fail-closed per-symbol C10 status only. Strategy engines, Shadow outcomes, calibration and risk promotion remain gated until their V21 stages pass.
3. **L3 — Delivery:** Telegram is the only user-facing delivery channel. Internal files, GitHub pages and engineering reports are not user dependencies.

The production path is designed for free-tier infrastructure and public APIs. It must not require paid services, exchange-account credentials, private trading keys or order-execution permissions.

## Non-negotiable operating rules

- C++ is the only production implementation language for the remaining system work. Python is legacy/auxiliary only.
- Public market data only. No private exchange account connection, account balance, trading API key, order placement, modification or cancellation.
- Telegram is the only user-facing channel. No active web dashboard or email fallback is part of the accepted architecture.
- Every stage must complete L1 Data, L2 Compute and L3 Delivery; a data-only result is incomplete.
- Every signal remains research-only until its independent statistical and risk gates pass.
- Missing or non-real inputs must remain explicitly labelled `PROXY` or `UNAVAILABLE`. Missing values are never silently filled with zero.
- `NOT_CALIBRATED`, `NO_QUALIFIED_SETUP`, `INSUFFICIENT_DATA` and `MARKET_DATA_DEGRADED` are valid outputs. Thresholds must not be weakened to force signals.
- The system reports risk states only. It does not control or protect a user's real exchange account.

## V21 stage status

| Stage | Scope | Current evidence status |
|---|---|---|
| 0 | V21 architecture and source acceptance | **PASS** — owner accepted V21.0 and Architecture Design V1 on 2026-11-23; source register updated on the V21 branch |
| 1 | V21 C++ L1/L2/L3 foundation and Telegram | **IN PROGRESS** — branch implementation and contract migration under test; no V21 live-run PASS yet |
| 2+ | Independent research hypotheses, calibration, risk and OOS validation | **NOT STARTED / GATED** — no strategy engine is approved or calibrated |

The previous V18.2 stage evidence remains historical evidence only. It does not establish acceptance under V21. LRT, NMT and VTM are rejected by V21 and must not be executed, renamed, or reused as production strategy engines.

## Legacy V18.2 evidence (historical only)

- V18.2 Stage 1 recorded two consecutive complete L1/L2/L3 runs with Telegram outbound/inbound and replay/deduplication. This is useful infrastructure evidence, but it is not a V21 Stage 1 acceptance.
- V18.2 Stage 2/3/4/5 records refer to LFS/NSS, liquidity-phase and LRT/NMT candidate research. They are not active V21 strategy approvals.
- V18.2 Stage 6 had only five hypothetical outcomes and remained NOT_CALIBRATED; Stage 7 remained BLOCKED / FAIL-CLOSED.
- All identified LRT/NMT/VTM execution workflows are hard-quarantined at job level with literal `if: false`; branch-name and commit-message conditions are not accepted as quarantine. CI enforces this invariant. See `docs/archive/superseded/README.md` and `docs/archive/superseded/V18.2_ARCHIVE_RECORD.md`.

PROXY, UNAVAILABLE, NOT_CALIBRATED and no-signal outputs must remain explicit. No strategy profitability or operational readiness is implied by this documentation.

## Evidence and operational entry points

- [V21 Stage 1 SLRP plan](docs/evidence/v21-stage1-slrp-plan.md)
- [Historical V18.2 Stage 1 SLRP evidence](docs/evidence/stage1-slrp-report.md)
- [Stage 2 LFS SLRP evidence](docs/evidence/stage2-lfs-slrp-report.md)
- [Stage 3 NSS SLRP evidence](docs/evidence/stage3-nss-slrp-report.md)
- [Stage 4 liquidity/phase SLRP evidence](docs/evidence/stage4-liquidity-phase-slrp-report.md)
- [Stage 5 dual-engine SLRP evidence](docs/evidence/stage5-dual-engines-slrp-report.md)
- [Stage 6 calibration and cost evidence](docs/evidence/stage6-meta-cognition-slrp-report.md)
- [Stage 7 risk-gate evidence](docs/evidence/stage7-risk-gate-slrp-report.md)
- [Legacy workflow quarantine evidence](docs/evidence/v18.2-legacy-workflow-quarantine.md)
- [Operations runbook](docs/OPERATIONS.md)
- [Stage roadmap and gates](docs/ROADMAP.md)
- [GitHub Actions](https://github.com/hamedbenapart69-byte/Trade/actions)

V21 workflow under validation:
- [C++ V21 Stage 1 live pipeline](.github/workflows/cpp-stage1-live.yml)

Rejected legacy workflows retained for audit but permanently non-runnable under V21: `alpha-discovery.yml`, `cpp-stage5-dual-engines-v1.yml`, `cpp-stage6-meta-cognition-v1.yml`, `cpp-stage6-pr-live-validation.yml`, `extract-vtm-result.yml`, and `stage1b-lrt15m.yml`.

## Build and test

The current verified build uses C++20 on the GitHub Actions `ubuntu-24.04` runner. The exact compiler and dependency versions are recorded in workflow evidence.

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure --no-tests=error
```

Schema and workflow validation are also required; a passing CTest run alone does not establish live provider access, Telegram delivery, statistical calibration or stage acceptance.

## Release discipline

- Work is developed on dedicated branches and reviewed through pull requests.
- Production workflow changes and final release require explicit owner approval.
- Never describe a stage as PASS without numeric acceptance evidence and real execution records.
- Never describe a proxy Shadow result as an executed trade.
- Never describe the system as profitable without independent out-of-sample evidence.
