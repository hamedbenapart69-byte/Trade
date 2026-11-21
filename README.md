# Crypto Futures Signal System (CFSS)

**Controlling specification:** owner-accepted `UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER`  
**Production implementation:** C++ (current verified build: C++20)  
**User delivery:** Telegram only  
**Trading boundary:** manual trading only; the system never connects to a user's exchange account or places orders.

This repository contains the implementation and evidence for CFSS. Older orchestration, Python/V5 scanner, browser dashboard, email and Railway material may remain in Git history or legacy paths; they are not the controlling production architecture.

## Current architecture

The active system is divided into three layers:

1. **L1 — Data:** GitHub Actions workers acquire public market data and preserve provider, timestamp, coverage and hash provenance. The user's device and exchange account are not part of the data pipeline.
2. **L2 — Compute:** C++ production binaries validate data, compute versioned research artifacts, maintain Shadow outcomes, apply fail-closed risk controls and produce daily per-symbol states.
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

## Verified stage status

The status below is grounded in the committed stage evidence, not inferred from the presence of source files.

| Stage | Scope | Current evidence status |
|---|---|---|
| 1 | C++ end-to-end L1/L2/L3, C10 and Telegram | **PASS** — two consecutive full runs, Telegram outbound and inbound, replay/deduplication evidence |
| 2 | LFS resilience | **PASS via v2** — PROXY / NOT_CALIBRATED; no actionable trades |
| 3 | NSS resilience | **PASS via v2** — PROXY / NOT_CALIBRATED; no actionable trades |
| 4 | Liquidity zones and market phase | **PASS via v1** — rule-based proxy; no trade generation |
| 5 | Independent LRT/NMT candidate engines | **PASS for candidate generation** — both engines remain non-actionable and NOT_CALIBRATED |
| 6 | Meta-cognition, calibration and net EV | **BLOCKED / NOT_CALIBRATED** — insufficient independent outcomes and incomplete persisted cost evidence |
| 7 | Consensus, Shadow risk and manual execution gate | **BLOCKED / FAIL-CLOSED** — risk-basis and persistent Shadow evidence are incomplete |
| 8–15 | Backtests, other paths, Shadow trading, allocator and final decision | **Not eligible to start** until the preceding stage gates pass |

The five persisted Stage 6 outcomes documented in the current evidence are hypothetical Shadow resolutions, not executed trades. They must not be presented as trading performance. The current Stage 7 gate must remain non-actionable while its risk basis, costs, position marks or upstream calibration are unavailable.

## Important current engineering work

- [PR #169 — Stage 7 Shadow risk snapshot v2](https://github.com/hamedbenapart69-byte/Trade/pull/169): implementation and live-validation work; not merged.
- [PR #170 — Stage 6 persistence pathspec hotfix](https://github.com/hamedbenapart69-byte/Trade/pull/170): fixes a verified scheduled-workflow failure; not merged.
- No production merge or release is implied by an open PR or a passing pull-request test.

## Evidence and operational entry points

- [Stage 1 SLRP evidence](docs/evidence/stage1-slrp-report.md)
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

Active workflow sources:
- [C++ Stage 1 live pipeline](.github/workflows/cpp-stage1-live.yml)
- [C++ Stage 6 scheduled pipeline](.github/workflows/cpp-stage6-meta-cognition-v1.yml)

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
