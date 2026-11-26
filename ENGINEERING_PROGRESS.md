# ENGINEERING_PROGRESS (V21 CFSS) — updated 2026-11-26

Authoritative: T1 (MASTER SOURCE V21.0) + V21 Execution Protocol Addendum only (owner "V21 ONLY" directive; main PR #184 archived V19/V18.2 as superseded).
Branch: `v21/fix-stage1-gate` (never merged; PR #183 was CLOSED unmerged on 2026-11-25T23:13Z by someone other than this session).
Stage 1 status: **NOT ACCEPTED (FAIL)**. Stage 2+ not started.

## Verified (evidence = GitHub Actions logs, read via REST GET)
- C++20 build + CTest 15/15 pass on PR run 45715851939 (HEAD e1c7838); L1/L2 schema validation pass (3 symbols on PR runs; PR events skip Telegram, persistence and the acceptance gate by design).
- The `printf '%s\\n'` newline defect from the earlier audit is already fixed on main (commit 9c53587); current source has `printf '%s\n'`. No change needed (verified by grep).
- Latest main acceptance run #385 (45655836360, c7253f1): Telegram outbound DELIVERED (message_id=101), persistence to `signals` OK, acceptance gate FAILED with `STAGE1_FALLBACK_GATE_FAIL: KuCoin public fallback live probe did not pass with real OHLCV, funding and hourly OI sample.` -> provider fallback is the actual blocker (OKX only proven).
- Stage 6 PR validation (run 45715852005, branch-name `if` removed by 0ffd5b1) FAILED at step "Collect 15m LRT resolution data": `INTRADAY_15M_ERROR=l1_1h_contract_invalid` (legacy LRT collector rejects the current L1 contract). This is a rejected-family (LRT) validator; main #184 now permanently quarantines it (`if: false` + `.github/scripts/rejected_workflow_guard.py`). Not treated as a V21 result.

## Changes on this branch vs main (after merge c4ca309 + this checkpoint)
- Merge of origin/main (Governance Lock #184); stage6/alpha workflow conflicts resolved by taking main's permanent quarantine (supersedes 0ffd5b1's workflow edits).
- Reverted 0ffd5b1/e1c7838 C++ cost-constant edits (they would break ledger validation/schema; see docs/evidence/V21_COST_MODEL_D1_2026-11-26.md).
- Added `config/v21_cost_model.json` and corrected D-1 evidence doc.
- Guard checks run locally: `python3 .github/scripts/test_rejected_workflow_guard.py` OK (2 tests); `python3 .github/scripts/rejected_workflow_guard.py` -> `REJECTED_WORKFLOW_GUARD=PASS workflows=13`.

## NOT verified / NOT done
- No C++ rebuild locally (container lacks libcurl/nlohmann; no network). C++ files equal main, so no C++ delta to test.
- Two-consecutive-run + replay-dedupe gate with distinct run IDs: BLOCKED. It only executes on non-PR events, sends REAL Telegram messages and writes `signals`; owner prohibited production Telegram for this task, and the fallback gate currently fails anyway.
- Per-symbol availability: only PR-run data (12 symbols in the Stage 6 job, 3 in the Stage 1 PR job). Last full scheduled-run figure remains 29/59 MARKET_DATA_DEGRADED (run #375 L2) — not re-measured.
- D-1 not wired into C++ shadow ledger (intentional, see doc).

## Decisions
- D-1=A recorded as config/evidence only; applying it to SHADOW_COST_PROXY_V1 would invalidate historical ledger rows.
- Did not reopen/open a PR (system notice: closed PR; no user request).
