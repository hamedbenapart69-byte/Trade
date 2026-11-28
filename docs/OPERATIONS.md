# CFSS Operations Runbook — V21.1

**Active user channel:** Telegram only  
**Active production compute:** C++ on GitHub Actions
**Binding data addendum:** V21.1 Exchange-Independent Data Federation & Nine-Asset Production Universe  
**User-side provider access:** not required  
**Trading execution:** forbidden; manual trading only.

This runbook describes the V21 operational boundary. V21 Stage 1 is currently under validation and is not yet declared operational. Historical V18.2 workflows and strategy engines are not part of the V21 execution path.

## 1. Normal operation

1. GitHub Actions workers acquire public market data.
2. During V21 Stage 1, C++ validates market data and computes safe per-symbol status only. No strategy engine is admitted; strategy, calibration and risk modules remain gated for later stages.
3. Versioned outputs and provenance are persisted on the dedicated `signals` branch.
4. Telegram is the only user-facing delivery channel.
5. Stage 1 messages are market-status reports, not trade instructions. No actionable BUY/SELL signal is permitted before independent strategy, calibration and risk gates pass.

The user's browser, phone, country, exchange account, VPN, balance and private exchange credentials are not part of the data pipeline.

## 2. Active workflows

- [C++ V21 Stage 1 live vertical slice](../.github/workflows/cpp-stage1-live.yml)

**Legacy workflow quarantine:** cpp-stage6-meta-cognition-v1.yml is job-level disabled and included in the permanent rejected-workflow CI denylist. It is not an active V21 path. The denylist and regression test must remain enabled.
- [All GitHub Actions runs](https://github.com/hamedbenapart69-byte/Trade/actions)

Stage-specific contract workflows validate the relevant C++ modules and schemas. Legacy Python/V5, dashboard, email, Railway and orchestration workflows are not the active user-facing architecture.

## 3. Provider eligibility and data federation

Technical reachability and contractual eligibility are separate gates:

- Do not reject a provider solely because the owner cannot open its website from a personal device; test the backend path from GitHub Actions where the provider's terms permit use.
- Do not accept a provider solely because an HTTP request returns 200; published API terms, account eligibility, automation rights, data-license scope and attribution obligations must also permit the intended use.
- If published provider terms exclude the account context or prohibit the required automated use, disable that adapter even if the backend can technically reach it.
- Never store the owner's country, location or account eligibility details in public repository configuration or artifacts.
- The V21.1 production federation gate requires at least two independent, fresh, license-eligible providers with overlapping asset identity coverage. A single provider is discovery evidence, not production quorum.
- The latest recorded live probe has only one qualified market-wide provider. CoinRanking and CoinMarketCap authenticated keys are not configured. CoinGecko is disabled by published provider terms, not by an HTTP reachability test. No provider quorum PASS is claimed.
- The nine-asset candidate file is provisional. The evidence-only 13-criterion screen does not mutate or freeze config/universe.json; production freeze remains blocked until all mandatory evidence and explicit owner approval are recorded.

## 4. Persistent runtime state

The `signals` branch contains historical V18.2 runtime artifacts under `cpp_runtime/`, including legacy candidate registries, outcome ledgers, Stage 4/5/6/7 outputs and Telegram receipts. These are historical evidence only; they are not an approved V21 strategy state and must not be consumed by a V21 engine without a separately reviewed migration.

Treat these as immutable historical evidence. Do not edit or delete them manually. Inspect the JSON schema and source hashes before interpreting any artifact.

## 5. Telegram delivery and idempotency

- Telegram delivery is performed by the backend workflow; there is no user-side bot setup step in normal operation.
- A `DELIVERED` receipt with HTTP 200 and a message ID is evidence of a successful Telegram API response.
- `RESERVED` means a report ID was reserved but no send has yet been confirmed.
- `SENDING` without a final receipt is an uncertain delivery state. Do not manually resend; first reconcile the outbox to avoid duplicate messages.
- `DELIVERY_UNKNOWN` and `PERMANENT_FAILURE` are not successful delivery states.
- A skipped send step is not a Telegram outage; inspect the earlier workflow step that prevented delivery.

Never treat a report file, a reserved outbox record or a green C++ test as proof that a Telegram message reached the user.

## 6. Failure triage

1. Open the failed GitHub Actions run and identify the first failing step.
2. Separate L1 provider failure, L2 compute/schema failure, persistence failure and Telegram delivery failure.
3. Inspect the generated run manifest, L1/L2 status, source hashes and relevant runtime artifacts.
4. If persistence failed, verify whether the `signals` branch received the new artifacts before considering another run.
5. If the outbox is `RESERVED` or `SENDING`, inspect the report ID and receipt state before any retry.
6. Preserve `UNAVAILABLE`, `PROXY`, `MARKET_DATA_DEGRADED` and `NOT_CALIBRATED` labels. Never relax a threshold to force a signal.
7. Record a specific diagnosis (D1 data, D2 assumption, D3 implementation, D4 threshold/calibration, D5 regime, D6 expectations) and rerun the relevant tests after a code correction.

## 7. Current known operating limits

- Post-PR #169 scheduled run [#45022129611](https://github.com/hamedbenapart69-byte/Trade/actions/runs/45022129611) completed successfully on 2026-11-22. It collected 49 instruments, produced 45/49 LFS and 38/49 NSS calculations, persisted five PROXY-costed hypothetical outcomes and delivered Telegram message 83. This proves engineering execution and delivery, not Stage 6 calibration.
- The Stage 6 run and scheduled pipeline can produce daily status reports, but a daily report is not evidence of calibrated probabilities or profitable trades.

- Stage 6 remains `NOT_CALIBRATED`; current outcome volume does not establish reliable probabilities or EV.
- Five historical Shadow outcomes now have provenance-backed PROXY cost rows. Fee remains ASSUMED and slippage remains PROXY; these do not qualify as REAL costs. Any new row with incomplete coverage or provenance remains `UNAVAILABLE`.
- Stage 7 remains fail-closed: the scheduled run emitted `RISK_BASIS_INVALID_OR_NOT_FROZEN`; no owner-approved immutable Shadow NAV/risk basis exists, one pending UNI fill lacks its timestamp, and Stage 6 is NOT_CALIBRATED.
- No user account balances or exchange positions may be used to fill missing internal Shadow data.
- No signal may be promoted while a required gate is blocked.

## 8. Build and validation (engineering only)

The current verified GitHub Actions toolchain builds C++20 on `ubuntu-24.04`.

```bash
cmake -S cpp -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 2
ctest --test-dir build --output-on-failure --no-tests=error
```

Schema validation and live L1/L3 evidence are separate acceptance requirements. A local build or CTest pass does not prove production data access, persistence, Telegram delivery or statistical performance.

## 9. Security boundary

- Never add exchange private keys, account credentials or order permissions.
- Keep Telegram secrets in GitHub Actions secrets; never print or commit them.
- No secret values belong in logs, reports or generated artifacts.
- No automatic trading, copy trading or order execution.
- Production merges, deployments and final releases require explicit owner approval.
