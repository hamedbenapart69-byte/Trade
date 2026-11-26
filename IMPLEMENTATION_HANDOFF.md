# IMPLEMENTATION_HANDOFF — 2026-11-26

Repo: hamedbenapart69-byte/Trade, branch `v21/fix-stage1-gate` (base: origin/main fe4c38b merged). Last verified commit before this checkpoint: e1c7838 (PR CI green except legacy Stage 6). HEAD after checkpoint: see `git log -1` / push result.
Uncommitted local changes: none after commit.

## Active task
Make Stage 1 acceptance genuinely pass. Current blocker (evidence: run 45655836360 log): `STAGE1_FALLBACK_GATE_FAIL` — KuCoin public fallback live probe does not pass with real OHLCV + funding + hourly OI.

## Single highest-priority next action
Diagnose the KuCoin live-probe failure: read the probe step output of the next main/dispatch Stage 1 run (or reproduce `market_pipeline` KuCoin probe path in cpp/ with the failing payload), fix root cause in C++ adapter/probe, add a regression test, then obtain two consecutive main runs. Needs owner approval for a dispatch run that sends real Telegram messages.

## Reproduce
- Guards: `python3 .github/scripts/test_rejected_workflow_guard.py && python3 .github/scripts/rejected_workflow_guard.py`
- C++: `cmake -S cpp -B build && cmake --build build -j && ctest --test-dir build --output-on-failure` (needs libcurl4-openssl-dev, nlohmann-json3-dev, libssl-dev)
- Run logs: `gh api repos/hamedbenapart69-byte/Trade/actions/runs/<id>/jobs` then `/actions/jobs/<jid>/logs`

## Constraints
V21 T1+Addendum only; no merge/deploy/prod Telegram without explicit approval; do not change gates; do not rewrite history; GraphQL blocked in this environment (use REST); open a PR only if the user asks.
