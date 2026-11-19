# STAGE 1 — C++ End-to-End Data + Compute + Telegram Delivery

**Canonical specification:** UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER  
**Implementation branch:** `feat/cpp-stage1-clean` (PR #150 merged into main)  
**PR:** #150 (MERGED; commit `16cb5e874e89649e049abb6debc6300572e24f09`)  
**Status:** PASS — all S1-01 through S1-12 acceptance criteria have project-scope evidence. Controlled inbound replay/dedupe verification passed in run 44246767969. Stage 2 and Stage 3 are now merged into main; Stage 2 LFS resilience and Stage 3 NSS resilience remain versioned separately.

## Objective

Deliver one real C++20 vertical slice from public market-data acquisition through C10 safe-state computation to Telegram. No Python production runtime, exchange account connection, private trading key, order placement, dashboard or email channel.

## Acceptance matrix

| ID | Acceptance requirement | Evidence / measured result | Status |
|---|---|---|---|
| S1-01 | Clean C++20 build, compiler/version and build identity | C++ Foundation and Stage 1 workflows; GCC toolchain; binary SHA-256 written to run manifest | PASS |
| S1-02 | Production data collection and compute actually execute in C++ | `market_pipeline --collect-okx` ran on GitHub Actions; C++ generated L1 and L2 artifacts | PASS |
| S1-03 | Real provider data, not fixtures or mock data | OKX live response; 17,532 closed 1h BTC candles over two years, 100% coverage; 90 funding rows/29.67d; 720 OI rows/29.96d; 730 FNG observations | PASS |
| S1-04 | Fallback chain is equivalence-tested or explicitly UNAVAILABLE | Bybit 403, Binance 451; KuCoin/MEXC/Bitget reachable but no equivalence-verified C++ adapter; all classified UNAVAILABLE; CoinGecko reference-only | PASS (explicit unavailability) |
| S1-05 | Frozen universe and per-symbol coverage report | 529 declared active USDT swaps; 90 passed metadata and >USD 10M 24h quote-notional gate; frozen selected ID list and per-symbol coverage emitted | PASS |
| S1-06 | L1/L2/output/run-manifest schemas, deterministic tests and hashes | L1, L2, signals, performance, coverage, system-status and run-manifest AJV validations passed; L1/L2 hashes logged; eight persisted output SHA-256 values independently recomputed and matched; deterministic scan ID and delivery key tests | PASS |
| S1-07 | Real Telegram outbound with positive response and message ID | Runs 44135013370 and 44149930383; HTTP 200; Telegram message IDs 39 and 40; one send attempt each; both receipts persisted | PASS |
| S1-08 | Real Telegram inbound, update processing, offset persistence and duplicate suppression | Live run 44240412741 processed update 610176013, persisted offset 610176013, and replied with Telegram message ID 43 (`DELIVERED`). C++ unit test in run 44242513881 verifies that `PROCESSED` cannot resume a reply. Controlled live re-poll run 44246767969 passed: `last_update_id` remained 610176013; `poll_count` increased 36→48; delivered reply count remained 1; reply message ID remained 43; outbound outbox count remained 4; no second reply was sent. Workflow emitted `CPP_TELEGRAM_INBOUND_REPLAY_DEDUPE_PASS`. | PASS |
| S1-09 | Two consecutive complete L1/L2/L3 runs with integrity and manifests | Runs 44135013370 and 44149930383 both have L1_L2_L3_PASS and DELIVERED receipts; scan IDs differ; second run's eight persisted artifact hashes independently matched | PASS |
| S1-10 | Failure honesty and degraded/no-signal reporting | Partial funding/OI is classified MARKET_DATA_DEGRADED; complete data with no strategy admitted is NO_QUALIFIED_SETUP; actionable=false; confidence NOT_CALIBRATED | PASS |
| S1-11 | No user-side provider connectivity | GitHub Actions fetches public data; user receives Telegram only; no exchange account keys or account connection | PASS |
| S1-12 | Every core dependency's current free use/limits recorded | Owner confirmed GitHub Free. Public repository uses standard `ubuntu-24.04` runner (free); GitHub Free includes 500 MB shared Actions/Packages storage. Historical artifact 14352156550 (866,358 bytes) was deleted and HTTP 404 verified in run 44246854270; the original run's artifact list is empty. Current Stage 1 and quarantined legacy workflows upload no new artifacts. Alternative.me's official API terms confirm free use, including commercial projects, subject to terms and attribution. | PASS (project scope) |

## SLRP — v1

### v1 implementation

- C++20 OKX public linear USDT perpetual discovery.
- Liquidity threshold: >USD 10M 24h quote notional.
- Two-year completed 1h OHLCV, 30-day funding and OI, Fear & Greed history, provider-health and provenance.
- C++ L1 contract, C10 L2 safe-state artifact, SHA-256 integrity, Telegram L3 sender/receiver.
- L1, L2 and run-manifest JSON Schemas.
- Deterministic scan ID and scan-window-based Telegram idempotency.
- Persistent outbox, inbound update state and per-run manifest.
- Four-hour schedule configured for up to 100 symbols and two years. Stage 1 validation profile is one BTC symbol and two years.

### v1 diagnosis log

All observed failures were implementation defects in v1 (D3); no v2 or v3 rewrite has been authorized or needed.

| Defect | Evidence | D-code | Correction |
|---|---|---|---|
| OHLCV cursor used the wrong parameter | Only 299 hourly candles returned instead of the expected two-year window | D3 | Use OKX history-candles `after` cursor; verify monotonic pagination |
| OI pagination used unsupported cursor and stopped on a short page | 99 OI rows and only a few days of coverage | D3 | Use OI endpoint `end` cursor; continue until the requested start boundary |
| OI array semantics were mis-mapped | Base-asset OI was incorrectly labeled as USD notional | D3 | Map contract count, base-asset amount and USD notional separately |
| UTC schema pattern was over-escaped | AJV rejected valid UTC timestamps | D3 | Use strict `[0-9]` UTC pattern |
| Partial derivatives could be labeled NO_QUALIFIED_SETUP | L2 state did not distinguish incomplete required data | D3 | Require OHLCV, funding and OI availability; otherwise MARKET_DATA_DEGRADED |
| C++ compile and test integration defects | Missing frozen-universe variable, initializer brace error and test timestamp shadowing | D3 | Correct declaration, initializer and test fixture |
| Workflow YAML negation parsed incorrectly | Push workflow had no jobs | D3 | Wrap negated condition in GitHub expression syntax |
| Telegram inbound executable omitted OpenSSL Crypto at link time | GCC link failed with undefined reference to SHA256 and `DSO missing from command line` | D3 | Link `OpenSSL::Crypto` explicitly to `telegram_inbound`; subsequent C++ Foundation and unit-test workflows passed |

### Active version

**Active: v1.** No v2/v3 implementation is permitted unless a new, measured v1 FAIL requires it under R11. Current remaining failures are acceptance evidence not yet collected, not a reason to rewrite the architecture.

### Escalation

If the remaining gates fail:
1. Data expansion or provider adapter only if evidence shows a provider-specific limitation.
2. Timeframe shift only with owner approval and no relaxation of acceptance criteria.
3. Simplicity audit and explicit UNAVAILABLE status before any proxy substitution.
4. If all permitted recovery options fail, report Honest Stop. Do not fabricate data or loosen thresholds.

## First complete run — evidence

**GitHub Actions run:** `44135013370`  
**Run status:** `L1_L2_L3_PASS`  
**Telegram status:** `DELIVERED`, HTTP 200, message ID `39`  
**Data sample:** BTC-USDT-SWAP  
**OHLCV:** 17,532 closed hourly candles, 100% coverage  
**Funding:** 90 rows, 29.67 days  
**Open interest:** 720 rows, 29.96 days  
**Fear & Greed:** 730 observations  
**L2:** `NO_QUALIFIED_SETUP`, `data_quality=REAL`, `actionable=false`, `confidence_status=NOT_CALIBRATED`

The first complete run did not claim a trade. The L2 output correctly reported that no strategy had qualified.


## Second complete run — evidence

**GitHub Actions run:** `44149930383`  
**Run ID:** `okx-cpp-1794940713508`  
**Scan ID:** `scan-3b61df4b5612af77b1b364b82f0363da8d2764514d9abcd76acd837486ce2279`  
**Run status:** `L1_L2_L3_PASS`  
**Telegram:** HTTP 200, message ID `40`, one send attempt, persisted as `DELIVERED`  
**Build ID:** `78be8cc006ea5de963f54c59a13fed390447ba6298ce102592be989ec2b613fa`

The first run's scan ID was `scan-f4e01b3a015c9aa427ee592482d90f92587128fab5f619fcbfd46872ad9c8ac6`; the second scan ID is different. Both runs therefore represent distinct hourly scan windows, not a repeated delivery for the same idempotency key.

Second-run real data:
- BTC/USDT:USDT: 17,532 completed 1h OHLCV rows; 100% coverage.
- Funding: 90 rows; 29.6667 days.
- Open interest: 720 rows; 29.9583 days.
- OHLCV, funding and OI all marked AVAILABLE; coverage summary 1 fully available, 0 partial, 0 unavailable.
- L2 state: `NO_QUALIFIED_SETUP`; `data_quality=REAL`; `confidence_status=NOT_CALIBRATED`; `actionable=false`.
- Signals artifact: zero actionable signals; one C10 status row. This is an honest no-setup report, not a missed signal.
- Performance artifact: `NOT_CALCULATED`, zero trades, all metrics null because no strategy engine or executed trades exist in Stage 1.
- Provider health: OKX primary HTTP 200; Bybit 403; Binance 451; KuCoin/MEXC/Bitget reachable but fallback remains UNAVAILABLE without an equivalence-verified C++ adapter; CoinGecko reference-only.
- Eight persisted artifacts (L2, provider health, Fear & Greed, signals, history, performance, coverage, system status) were independently SHA-256 recomputed from the `signals` branch and matched the manifest exactly. L1/L2 raw file hashes were printed by the runner and matched their manifest entries.

**S1-09 is PASS.** The second complete run is independently verified and the two scan IDs differ. **S1-08 is also PASS** after controlled replay.

## Self-critique

1. **Future data used?** No. Only completed hourly bars are admitted; the candle confirmation flag and bar-end boundary are checked.
2. **Parameters tuned on test?** No strategy parameters exist in this Stage 1 vertical slice. The liquidity threshold is a fixed system requirement, not fitted on the validation sample.
3. **Costs included?** No trade is admitted or executed in Stage 1, so trade EV/cost modeling is not applicable here. The production path remains manual-trade-only.
4. **Report in no-signal case?** Yes. NO_QUALIFIED_SETUP and MARKET_DATA_DEGRADED are explicit C10 states and are delivered through Telegram.
5. **Weakest assumption?** OKX is currently the only equivalence-verified futures data adapter. Other providers remain explicitly UNAVAILABLE until C++ adapter equivalence is tested. Stage 1 has no strategy engine or calibrated confidence, so NO_QUALIFIED_SETUP is expected rather than a trade signal.

## Handoff

Stage 1 acceptance matrix S1-01 through S1-12 is not yet fully closed: S1-08 is PASS: the controlled live replay in run 44246767969 verified unchanged `last_update_id`, increased poll count, unchanged delivered reply count/message ID, and no duplicate response. S1-12 is PASS at project scope: the sole historical artifact was deleted and no current Stage 1 artifact uploads remain. The live inbound update was processed and acknowledged. The controlled replay verified duplicate suppression.

The project footprint is within GitHub Free allowances on measured project evidence. Account-wide unrelated Packages usage remains outside repository observability.

**Handoff:** Do not merge PR #150 or release Stage 2 until the S1-08 replay verification passes. Stage 2 code exists in a separate draft branch but is not released.
