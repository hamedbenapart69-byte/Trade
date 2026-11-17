# STAGE 1 — C++ End-to-End Data + Compute + Telegram Delivery

**Canonical specification:** UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER  
**Implementation branch:** `feat/cpp-stage1-clean`  
**PR:** #150 (draft; not merged)  
**Status:** IN PROGRESS — one complete L1/L2/L3 run verified; inbound and second distinct scan run remain open.

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
| S1-06 | L1/L2/run-manifest schemas, deterministic tests and hashes | L1, L2 and run-manifest AJV validation passed; four artifact SHA-256 values independently matched in the uploaded ZIP; deterministic scan ID and delivery key tests | PASS |
| S1-07 | Real Telegram outbound with positive response and message ID | Push run 44135013370; HTTP 200; Telegram message ID 39; one send attempt; receipt persisted | PASS |
| S1-08 | Real Telegram inbound, update processing, offset persistence and duplicate suppression | Controlled `/status` test not yet run | NOT PROVEN |
| S1-09 | Two consecutive complete L1/L2/L3 runs with integrity and manifests | First complete run 44135013370 passed; second distinct hourly scan window not yet run | PARTIAL |
| S1-10 | Failure honesty and degraded/no-signal reporting | Partial funding/OI is classified MARKET_DATA_DEGRADED; complete data with no strategy admitted is NO_QUALIFIED_SETUP; actionable=false; confidence NOT_CALIBRATED | PASS |
| S1-11 | No user-side provider connectivity | GitHub Actions fetches public data; user receives Telegram only; no exchange account keys or account connection | PASS |
| S1-12 | Every core dependency's current free use/limits recorded | Public repository and free standard runner confirmed; no paid providers or larger runners; artifact retention/compaction implemented; account-level artifact-storage quota remains unverified | PARTIAL |

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

## Self-critique

1. **Future data used?** No. Only completed hourly bars are admitted; the candle confirmation flag and bar-end boundary are checked.
2. **Parameters tuned on test?** No strategy parameters exist in this Stage 1 vertical slice. The liquidity threshold is a fixed system requirement, not fitted on the validation sample.
3. **Costs included?** No trade is admitted or executed in Stage 1, so trade EV/cost modeling is not applicable here. The production path remains manual-trade-only.
4. **Report in no-signal case?** Yes. NO_QUALIFIED_SETUP and MARKET_DATA_DEGRADED are explicit C10 states and are delivered through Telegram.
5. **Weakest assumption?** OKX is currently the only equivalence-verified futures data adapter. Other providers remain explicitly UNAVAILABLE until C++ adapter equivalence is tested. The account's artifact-storage quota also remains unverified.

## Handoff

Stage 1 is **not PASS yet**. Required remaining evidence:
- A second complete push run using a different hourly scan ID and a real Telegram delivery receipt.
- Owner sends `/status` to the configured Telegram bot; then the tagged inbound-test workflow must prove a newly received update, processed reply, persisted offset and no duplicate response.
- Confirm the account-level artifact-storage allowance or an equivalent billing guard for S1-12.

Do not merge PR #150 or begin Stage 2 until the complete S1-01 through S1-12 matrix is PASS and the owner confirms the Stage 1 handoff.
