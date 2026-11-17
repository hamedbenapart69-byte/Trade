# Stage 1 Evidence — Real Hybrid L1 → C++ L2 Run

- **Evidence classification:** PARTIAL STAGE 1 EVIDENCE; NOT a Stage 1 PASS
- **Workflow:** Hybrid Stage 1 Live L1-to-L2 Integration
- **GitHub Actions run:** [44119249492](https://github.com/hamedbenapart69-byte/Trade/actions/runs/44119249492)
- **Run commit:** `8495e165ad4ee11b81b4362e51be32780a0b78d1`
- **L1 run ID:** `94cbbfad-791a-4150-abf5-eae073260128`
- **Provider:** OKX public market-data API
- **Fallback used:** false
- **Artifact SHA-256 (GitHub artifact ZIP digest):** `31bd0a0c73afb21923bbb53cd7a703d24fd1f413ca799ad91c497b1eddc1bb16`
- **Artifact archive size:** 3,890,430 bytes
- **Contract:** `l1-market-data.v1`, schema `1.0.0`

## Real acquisition results

The run completed on GitHub-hosted infrastructure. It did not use user-side exchange connectivity, exchange account credentials, fixtures, or mocks for market acquisition.

- Requested integration universe: 10
- Exported instruments: 10
- Successful instruments in collector report: 10
- Failed instruments: 0
- BTC context: present
- Instruments: BTC, ETH, SOL, XRP, DOGE, PEPE, NEAR, UNI, WLD, SUI, all USDT-settled linear perpetual contracts.
- OHLCV timeframe: 1h
- History target: 2 years
- Exported completed OHLCV candles: 17,531 per instrument; 175,310 total.
- Collector report: 17,532 raw rows per instrument, zero duplicate rows, zero missing hourly intervals, 100.0% coverage, maximum interval 1h.
- The final raw candle timestamp was 15:00 UTC while acquisition completed at approximately 15:54 UTC; that still-open candle was excluded from the exported completed-candle contract. The exported range ends at 14:00 UTC.
- Funding observations: 276 per instrument (277 for SOL), approximately 91.67–92.00 days. This exceeds the 30-day Stage 1 target.
- Open-interest observations: 720 per instrument, approximately 29.96 days.
- The collector report explicitly notes that this OI history is limited to the latest 30 days and is not a two-year series.

## C++ L2 result

C++20 consumed the real JSON contract and produced exactly one status per instrument:

| C10 state | Count |
|---|---:|
| NO_QUALIFIED_SETUP | 10 |
| MARKET_DATA_DEGRADED | 0 |
| BUY_NOW / SELL_NOW | 0 |
| CONDITIONAL_BUY / CONDITIONAL_SELL | 0 |
| WATCHLIST | 0 |

Every output row had:
- `data_quality = REAL`
- `confidence_status = NOT_CALIBRATED`
- `actionable = false`
- `reason_code = NO_STRATEGY_ADMITTED`

This is a data-admission/status vertical slice, not a completed trading strategy. It correctly did not fabricate a trade signal.

## Acceptance mapping

| Requirement | Evidence status | Notes |
|---|---|---|
| S1-01 Clean C++ build | PASS for this build | C++ Foundation CI build completed successfully. |
| S1-02 Actual C++ runtime | PASS for this run | C++ consumed the real L1 contract and wrote the L2 artifact. |
| S1-03 Real backend data | PASS for bounded slice | 10 real OKX perpetuals, 2-year hourly OHLCV, funding and OI history. |
| S1-04 Equivalent provider fallback | NOT VERIFIED | This run used OKX only; no fallback was required. |
| S1-05 Universe coverage | PARTIAL | 10-instrument integration slice only; target is approximately 100 eligible contracts plus BTC context. |
| S1-06 L2 artifact correctness | PARTIAL | Versioned contract and C10 safe-default output verified; complete strategy/risk gates and immutable artifact manifest remain outstanding. |
| S1-07 Real Telegram outbound | NOT YET VERIFIED | C++ L3 outbox is implemented and under CI verification; this L1/L2 run did not send Telegram. |
| S1-08 Real Telegram inbound | NOT YET VERIFIED | No real update receipt is evidenced by this run. |
| S1-09 Two consecutive complete L1/L2/L3 runs | NOT PASS | Only one L1/L2 run exists; L3 is not yet proven. |
| S1-10 Failure honesty | PARTIAL | Fail-closed contract validation and C10 degraded state exist; end-to-end fault-injection evidence remains. |
| S1-11 No user-side exchange/provider connection | PASS by architecture and workflow | GitHub Actions fetched public data; no user credential or connection was used. |
| S1-12 Zero-cost | PARTIAL | Uses free public endpoints and GitHub-hosted workflow dependencies; recurring free-tier quota/usage monitoring remains. |

## SLRP

- **v1:** IN PROGRESS; no version-level PASS/FAIL declaration for Stage 1.
- **v2/v3:** NOT BUILT. No evidence-based v1 failure diagnosis authorizes a rewrite.
- **Active:** v1.
- **Handoff:** finish C++ L3 real outbound/inbound, durable state persistence, provider fallback proof, broader universe, failure tests, and two consecutive complete three-layer runs.

**Conclusion:** The bounded L1 → L2 vertical slice is verified. Stage 1 as a whole remains NOT PASS.
