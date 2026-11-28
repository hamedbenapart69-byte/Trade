# V21 Stage 1 — SLRP and Live Acceptance Ledger

**Historical status snapshot (2026-11-25):** v1 FAIL (D3) / v2 FAIL (D3) / v3 engineering CI PASS; PR #179 corrections were subsequently merged. This snapshot is superseded by the 2026-11-28 production acceptance evidence in Section 9. **Current disposition: IN PROGRESS — V21.1 NONCONFORMANCE FOUND.** The V21.0 vertical-slice evidence below is historical and does not establish full V21.1 acceptance.

- **Controlling source:** T1.md — MASTER SOURCE V21.0 + V21 Execution Protocol Addendum
- **Architecture:** CFSS V21 Architecture Design V1
- **Stage 0:** OWNER ACCEPTED / DESIGN PASS (2026-11-23)
- **Active candidate:** v3; no v4 is permitted.
- **Current PR:** [#179 — KuCoin fallback payload and run-manifest schema alignment](https://github.com/hamedbenapart69-byte/Trade/pull/179)
- **Production main at audit start:** `69bde397a5dcb779f0dcd27298064e7ea1bafafe`
- **VTM quarantine:** merged separately in commit `9e22c2efb8a2bdf93b53395c1d37979026f7c96c`; research source files are preserved.

## 1. Objective

Establish a reproducible, zero-cost, C++ production vertical slice for V21 using public market data, fail-closed L2 status computation, versioned V21 run provenance, and Telegram delivery. Stage 1 is infrastructure and safe reporting only. No strategy engine is admitted in this stage. LRT, NMT and VTM remain rejected.

## 2. Mandatory Acceptance Criteria

All criteria are mandatory. Stage 1 requires **two consecutive, independent complete main-branch runs** with distinct run IDs and the same accepted code revision.

1. **Build:** C++20 configure and full production build on ubuntu-24.04 complete with exit code 0.
2. **Tests:** all registered CTest tests execute; 100% pass; zero unexpected skips or test failures.
3. **L1:** live public data for BTCUSDT and at least one liquid non-BTC USDT perpetual; 1h OHLCV, funding and open-interest series; strictly increasing timestamps; completed candles; currency/unit validation; explicit freshness and coverage.
4. **Provider truth:** primary provider and every fallback status are recorded. Unimplemented or unreachable fallbacks remain NOT_IMPLEMENTED or UNAVAILABLE. Partial equivalence must remain explicitly PARTIAL.
5. **L2:** C++ emits one valid C10 state per selected instrument. `actionable=false` for every instrument in Stage 1; `confidence_status=NOT_CALIBRATED`; missing/stale/partial required inputs resolve to MARKET_DATA_DEGRADED, not a fabricated signal.
6. **V21 manifest:** `run-manifest.v2.json` validates against `run-manifest.v2.schema.json`; `document_version=V21.0`; rejected families exactly [LRT,NMT,VTM]; active strategy engine list empty.
7. **L3 outbound:** Telegram API returns HTTP 200, `ok=true`, and a persisted positive message_id; manifest records DELIVERED and L1_L2_L3_PASS.
8. **L3 inbound:** at least one of the two runs receives and processes a controlled `/status` update from the authorized chat; the exact same processed update_id is replayed through the production duplicate-update handler; no second reply is sent; manifest records RECEIVED_PROCESSED and replay PASS.
9. **Persistence:** run manifest, L1/L2 provenance, Telegram outbox and receipts are persisted on the dedicated `signals` branch. No GitHub Actions artifact upload/storage is used.
10. **Repeatability:** both runs independently satisfy criteria 1–7 and 9; at least one also satisfies criterion 8; no manual editing of generated artifacts between runs.
11. **Safety:** no private exchange credentials, account endpoints, order placement, paid services or non-C++ production runtime.
12. **Scope:** no strategy-performance, profitability, calibration or OOS claim is inferred from Stage 1.

A pull-request run may prove build, CTest, live L1/L2 and schema validation, but skips Telegram delivery and persistent-state writes. It does **not** count as either of the two complete Stage 1 acceptance runs.

## 3. v1 — Original Implementation

**Assumption:** existing C++ L1, L2 C10 and Telegram L3 components could be reused after replacing the legacy run manifest with the V21 contract and excluding rejected strategy execution.

**Result:** FAIL (D3). Main run `45223598065` on `7ef03f861a9e41906f1aa4787da6ffca21c2cd4d` passed build/tests and delivered Telegram (HTTP 200, message_id=91), but the manifest remained DATA_DEGRADED. ZEC-USDT-SWAP had 9,182 hourly candles but was measured against the global two-year denominator, producing 52.37% coverage. The instrument's official listing time was 2025-11-06 03:15 UTC. The collector had listing_time_ms, but final coverage and cache denominators did not use it. This was a D3 implementation defect, not missing market history.

The old replay workflow also polled from `last_update_id + 1` rather than replaying the same processed update through the production duplicate-update handler.

## 4. v2 — Listing-Aware Coverage and Exact Replay

**Alternative assumption:** OHLCV completeness must be measured against each instrument's tradable history, and duplicate-update behavior must be tested by replaying the exact same update_id through the production handler.

**Implementation on isolated branch:** listing-aware expected rows, consistent cache/final coverage, removal of legacy shadow_candidate_registry dependency, deterministic exact-update replay, replay fields in the V21 manifest, and controlled inbound test after outbound delivery.

**Result:** FAIL (D3). Commit `48d01026ad88a4bf7736e7b4a088a495934195f2` passed its then-current C++ build/CTest and PR L1/L2 checks, but a source-level audit found that expected row count used the exact listing timestamp rather than the aligned candle-open grid. For a 03:15 listing, the 03:00 candle overlaps the valid trading window and must count. Count-only coverage could also allow an extra row to mask a missing expected timestamp. The old test expected 9,181 while supplying 9,182, then accepted the result after percentage clamping. No threshold was relaxed.

## 5. v3 — Exact Candle-Grid Completeness

**Alternative assumption:** row count alone cannot establish completeness. Coverage must be evaluated against the exact aligned candle-open timestamp grid; duplicate, missing, off-grid or invalid in-window rows cannot substitute for an expected candle.

**Implementation on isolated Stage 1 branch:**
- Align the first expected candle to the opening boundary containing max(global lookback start, listing time).
- Compute expected rows through the exclusive end boundary.
- Validate the exact expected timestamp grid, including missing, duplicate, pre-listing, off-grid and extra in-window rows.
- Apply continuity checks to final availability and cache acceptance/retention.
- Add a regression fixture where an extra row preserves raw count while an expected timestamp is missing.

**Engineering CI result:** PASS on isolated head `0b3ae5209deaa44461ccab309f927c2b6d692e24`. C++ foundation, Stage 1 L1/L2, CTest, LFS/NSS contracts, Stage 5/6/7 contracts and Policy Guard completed successfully. PR semantics skipped Telegram and signals-branch persistence. This was an engineering/CI PASS only, not Stage 1 acceptance.

## 6. Expanded Live Integration Findings — 2026-11-25

The following findings concern the current expanded provider-health and manifest integration. They do not change the v3 candle-grid assumption or relax any acceptance criterion.

### D3-A — KuCoin fallback error-array shape

- **Evidence:** main workflow run `45622871420`, commit `174d3b45d30add0cd158f36f700b8320628cdd95`.
- C++20 build and CTest passed; live OKX L1/L2 collection completed.
- L1 schema validation failed at `/provider_health/providers/3/fallback_probe/errors/0`: expected string, received array.
- **Root cause:** `Bundle::errors` in `cpp/include/cfss/kucoin_provider.hpp` used `json errors{json::array()};`, producing a nested empty array.
- **Correction proposed in PR #179:** use `json errors = json::array();` and add a deterministic C++ regression test for an empty flat error list and string entries.

### D3-B — Run-manifest fallback-status enum

- **Evidence:** PR workflow run `45653441255`, head `aec0bcf2aa506fcf30f7e29619f8000667a9189f`.
- C++20 build, CTest, live OKX collection, L1 market-data schema and crypto-universe schema passed after D3-A was corrected.
- Run-manifest schema then failed at `/provider_status/providers/3/fallback_status`.
- Actual runtime value: `AVAILABLE_PARTIAL`. The L1 market-data schema already allowed this explicit partial state, but the run-manifest schema enum omitted it.
- Live KuCoin probe evidence showed HTTP reachable, 168 OHLCV rows, 90 funding rows, only 1 OI row, 0 days measured OI coverage and a 7-day hourly OI retention limitation. It must remain `AVAILABLE_PARTIAL` / `PARTIAL`, not a full-equivalence fallback.
- **Correction proposed in PR #179:** add `AVAILABLE_PARTIAL` to the run-manifest `fallback_status` enum. This aligns the schema with an existing explicit runtime state; it does not relax data coverage or acceptance thresholds.

### Current verification status

- PR run `45653879982`, head `a829512ad580ed5a90ad8aa7bdf8ae98f72e3f3a): C++20 build, CTest, live L1 collection, L1 schema and universe schema passed; it reproduced D3-B because it predates the schema correction.
- PR #179 latest head after the evidence-ledger update: `d6b3b25ef07476c735d20e6d49332ba3dad2a5a0`; the Stage 1 run `45654141018` was launched against the preceding code/schema head `d9a5866598278fe696fb51b12de7acb0e742564a`.
- PR Stage 1 run for that head: `45654141018`, pending/in progress at the time of this update. No result is claimed until the run completes.
- All PR-event runs skip Telegram and persistent-state acceptance by design.

## 7. Provider Reality Snapshot

From the persisted main-branch manifest `okx-cpp-1795613093962` (2026-11-25):

- OKX: HTTP 200, primary adapter implemented.
- Bybit: HTTP 403, adapter NOT_IMPLEMENTED / UNAVAILABLE.
- Binance Futures REST: HTTP 451 from the runner, adapter NOT_IMPLEMENTED / UNAVAILABLE.
- KuCoin: HTTP 200, secondary adapter implemented partially; fallback equivalence PARTIAL because hourly OI history is limited to 7 days, below the 30-day requirement.
- MEXC and Bitget: HTTP reachable, but production adapter equivalence NOT_PROVEN and adapters NOT_IMPLEMENTED.
- CoinGecko: reference-only, not a futures fallback.

A separate research workflow successfully downloaded checksum-pinned Binance Vision archives from GitHub Actions. This proves archive reachability from that runner at that time; it does not prove Binance Futures REST reachability or full provider equivalence. User geography is not a backend provider-selection rule.

## 8. SLRP Budget, Escalation and 2026-11-25 Historical Gate Snapshot

- Maximum versions remain v1, v2 and v3. No v4 is permitted.
- v1: FAIL (D3), listing-window coverage and replay-handler defects.
- v2: FAIL (D3), count-only coverage and incorrect handling of a non-aligned listing timestamp.
- v3: at this 2026-11-25 snapshot, engineering CI had passed on its isolated branch; complete live acceptance was NOT_VERIFIED. Expanded live integration had exposed D3-A and D3-B, with narrow corrections pending verification in PR #179.
- No acceptance threshold has been weakened.
- If the corrected v3 candidate fails another mandatory acceptance criterion, stop further rewrites and invoke the V21 Innovation Protocol in order: Data Expansion, Timeframe Shift, Simplicity Audit, Regime Restriction, Alternative Market, Honest Stop.
- At the time of this 2026-11-25 snapshot, Stage 1 remained **IN PROGRESS — NOT ACCEPTED** pending two qualifying main-branch L1/L2/L3 runs and controlled inbound/replay evidence. This historical disposition is superseded by Section 9.
- Stage 2 and all strategy promotion remain gated.


## 9. Historical V21.0 vertical-slice execution — 2026-11-28 (not V21.1 stage acceptance)

**Disposition: V21.0 vertical-slice checks passed; V21.1 Stage 1 acceptance NOT MET.** This section records actual historical execution evidence only. It does not approve a strategy or authorize Stage 2.

### Qualifying main-branch runs

The main-branch C++ Stage 1 workflow completed run **46138691159** on 2026-11-28 at 11:11:22 UTC. Its job completed successfully, including C++20 configure/build, CTest, live L1 collection, C++ L2 generation, schema checks, Telegram outbound, signals-branch persistence and the final Stage 1 acceptance gate.

Evidence from the workflow log:
- C++ build identity: `6b7f8eb3acf854d47244a017b74d6be60e50b5b1c44974c3f50231a0a97e6d81`.
- Live collection: `CPP_L1_COLLECTED provider=okx symbols=50 crypto_universe=VERIFIED`.
- Telegram API preflight: HTTP 200.
- Outbound receipts: message IDs 111, 112 and 113; each recorded as `DELIVERED`, HTTP 200.
- Persistent signals-branch verification: `SIGNALS_BRANCH_REMOTE_PERSISTENCE_PASS run_id=okx-cpp-1795864418221`.
- Final workflow assertion: `STAGE1_ACCEPTANCE_GATE_PASS revision=3ea17e71264aad4e8e0ecf7d550914dcd338ae26 consecutive_runs=2 inbound_replay_runs=1`.

The acceptance gate inspected the latest two qualifying main-branch manifests. Run #398's overall Actions conclusion was `failure` only because its final aggregate step correctly reported that a second qualifying manifest did not yet exist; the preceding C++ build, CTest, live L1/L2, outbound delivery, inbound exact-update replay and persistence steps succeeded. Its persisted manifest therefore records the completed first qualifying vertical slice as `STAGE1_CONTROLLED_ACCEPTANCE_PASS`. Run #525 was the next main-branch Stage 1 workflow run and completed the two-run aggregate gate:

| Manifest run number | Run ID | Repository commit | Run status | Telegram message IDs | Inbound/replay |
|---:|---|---|---|---|---|
| 398 | `okx-cpp-1795801953622` | `8e9ea66cb090e39c94884013bf02904f0e3bcebb` | `STAGE1_CONTROLLED_ACCEPTANCE_PASS` | 110 | `HISTORICAL_RECEIPT_REPLAYED`, replay PASS, update_id 610176016 |
| 525 | `okx-cpp-1795864418221` | `3ea17e71264aad4e8e0ecf7d550914dcd338ae26` | `L1_L2_L3_PASS` | 111, 112, 113 | Not requested in this run; prior qualifying run supplies the required inbound/replay proof |

Both manifests record the same production source-tree hash:
`2efdeebac803ca366aeec438523d7a7d695890f4f5859ea723102a49853225c4`.
Their scan IDs are distinct:
- `scan-ed9910dedf304c0b2950182ac638562e6dc01acc2ac5d38b0479b4c3cbd2ba66`
- `scan-1a0ba50f5eeb6d7930e26a21818ae1ffa773d591ad15990b7fc32d9e0e8c8f5d`

The repository commits differ, but the workflow's production-source hash—which covers the production C++/contracts/configuration/build scripts and Stage 1 workflow scope—is identical. The acceptance gate explicitly compares this source hash across the two qualifying runs.

### Acceptance interpretation

- **Build and tests:** PASS on GitHub Actions ubuntu-24.04 runner. This is runner evidence; no local build is claimed from this environment.
- **L1/L2:** live OKX collection and C++ C10 safe-state generation completed. The Stage 1 workflow's provider-health and schema gates passed.
- **L3:** outbound Telegram receipts were returned with HTTP 200 and positive message IDs; receipts and run artifacts were verified on the dedicated signals branch.
- **Inbound/replay:** one of the two qualifying runs records a previously verified authorized inbound update and exact-update replay with replay status PASS.
- **Strategy status:** no strategy engine is admitted; actionable remains false and confidence remains NOT_CALIBRATED. Stage 1 is infrastructure acceptance only, not trading-edge evidence.
- **Provider limitation:** OKX is the production primary. Partial/unavailable fallbacks remain explicitly labelled; Stage 1 PASS does not imply full provider equivalence.
- **Cost semantics:** this infrastructure-stage PASS does not resolve one-way versus round-trip cost interpretation for later strategy backtests.

### Handoff

The workflow's V21.0 vertical-slice gate passed for the 50-instrument run. This is not a V21.1 Stage 1 PASS because the production universe was not restricted to exactly nine assets and the provider federation requirements were not met. See Section 10. Stage 2 remains blocked.


## 10. V21.1 compliance audit — 2026-11-28

The prior live run is not accepted as a complete V21.1 Stage 1 run. The following source-level and persisted-artifact findings are verified:

- `config/universe.json` contains the required nine symbols, but the Stage 1 workflow did not consume it. The workflow exposed symbol-count inputs up to 100 and the scheduled path defaulted to 100; the run manifest recorded 50 L2 instruments.
- The persisted L2 artifact `cpp_runtime/l2-status-okx-cpp-1795864418221.json` contains 50 rows. All nine configured assets appear, but 41 additional assets are also present. This violates V21.1's exact 9/9 C10 denominator.
- `cpp_runtime/provider-health-okx-cpp-1795864418221.json` records OKX as the implemented primary; KuCoin as `IMPLEMENTED_SECONDARY_PARTIAL` with 6.75 days of hourly OI coverage; Bybit and Binance as unavailable/unimplemented; MEXC and Bitget reachable but unimplemented; CoinGecko as reference-only. This does not satisfy the V21.1 independent market-wide reference-source and provider-equivalence requirements.
- The run manifest marks the 331,391,103-byte L1 artifact as not retained on the signals branch and not retained as a workflow artifact. Its SHA-256 is present, but the raw L1 artifact cannot be independently inspected from the retained record.
- The persisted artifacts include `crypto_universe`, but no dedicated frozen `universe_manifest.json` or `release_manifest.json` is recorded in the run manifest. The config file has no selection timestamp, source snapshot hashes, exclusion record, or freeze approval reference.
- Telegram outbound is verified for the historical run (HTTP 200; message IDs 111, 112, 113). Owner-side receipt in Iran remains NOT_VERIFIED. The inbound/replay proof came from the prior qualifying manifest, not this specific run.

**Disposition:** V21.0 vertical-slice evidence = VERIFIED; V21.1 exact-nine and federation acceptance = NOT_MET; Stage 1 overall = IN PROGRESS. The correction branch `fix/v21.1-nine-asset-stage1-20261128` and PR #188 implement the first exact-nine reconciliation, but PR validation and live nine-asset L1/L2/L3 acceptance remain pending. No Stage 2 work is authorized.
