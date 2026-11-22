# Bitget C++ Public Futures Provider Probe v1

**Status:** RESEARCH ONLY — not connected to the production provider chain.  
**Production language:** C++20.  
**Access boundary:** public unauthenticated GET endpoints only. No API key, account endpoint, trading permission, or order route.

## Why this probe exists

The current production C++ market-data adapter is OKX-only. A provider-health HTTP response from a second venue is not an acceptable fallback. Before a venue can be considered, the same instrument must provide complete and correctly normalized public inputs under the V18.2 data contract.

This isolated probe checks BTCUSDT and ETHUSDT from Bitget V3. It deliberately does not send Bitget data into the production L1 contract or merge any data with OKX.

## Official endpoints used

- Instruments: `GET /api/v3/market/instruments?category=USDT-FUTURES`
- Tickers: `GET /api/v3/market/tickers?category=USDT-FUTURES`
- Historical 1H candles: `GET /api/v3/market/history-candles`
- Historical funding: `GET /api/v3/market/history-fund-rate`
- Historical open interest: `GET /api/v3/market/open-interest-history?period=1h`

Official references:
- [Bitget Market Data V3](https://www.bitget.com/docs/catalog/market/market-data)
- [Bitget Derivatives and Funding Rate V3](https://www.bitget.com/docs/catalog/market/derivatives)
- [Bitget V3 API changelog](https://www.bitget.com/legacy-docs/uta/changelog)

## Acceptance gates

For each tested symbol:

1. Instrument is online, perpetual, crypto type, and USDT quoted.
2. 24-hour quote turnover is strictly greater than USD 10,000,000.
3. Closed 1H OHLCV covers two years or the complete time since listing, with no missing 1H intervals in the measured span.
4. Funding history covers at least 30 days, including the contract's published funding interval.
5. Historical OI at 1H covers at least 30 days with no missing hourly intervals.
6. Prices, timestamps, funding rates, OI, volume units and quote notional pass normalization checks.

A failed or missing field remains unavailable. The code keeps Bitget's OHLCV volume in BASE_COIN units and OI in BASE_COIN / USDT value units. It never relabels base-coin volume as contracts.

## Version and scope

- v1 is a live research probe only.
- No fallback order is changed.
- No production adapter is registered.
- No cross-venue dataset is merged.
- Promotion requires a separate equivalence review for contract identity, listing time, quote/base/settlement, volume units, funding intervals, OI units, candle finality and history continuity.
- Even a successful BTC/ETH probe does not prove coverage for the full 100-symbol universe.

## SLRP status

- Objective: determine whether Bitget can independently satisfy the C++ L1 public futures data requirements for the two reference symbols.
- Acceptance: online USDT perpetual crypto instrument; >$10M 24h quote turnover; two years (or full listing history) of gap-free 1H OHLCV; at least 30 days of funding; at least 30 days of 1H OI; and valid unit/freshness provenance.
- **v1: FAIL — D1 (measured live-data coverage failure), not an implementation/build failure.** Run [45024100468](https://github.com/hamedbenapart69-byte/Trade/actions/runs/45024100468): C++ build and all 16 CTest cases PASS, but the live BTCUSDT/ETHUSDT probe returned zero eligible symbols. For each reference symbol, the API confirmed an online crypto USDT perpetual instrument and turnover above $10M; 90 funding observations covered 29.6667 days with an 8-hour settlement interval; 17,344 1H candles spanned 729.9167 days but had 175 missing hourly intervals; 30 hourly OI observations covered only 1.2083 days. This fails the required 30-day OI and gap-free OHLCV gates. No live fallback is claimed.
- **v2: built on the measured v1 failure and currently under live validation.** It changes the collection assumption, not acceptance thresholds: 98-hour unique candle windows with a 2-hour page overlap; align the 730-day range to completed-hour boundaries; accept `launchTime=0` only when the full 730-day OHLCV window is verified; report freshness explicitly; and retrieve daily OI as a separate `RESEARCH_ONLY` diagnostic. Daily OI is never substituted for the required 1H OI and cannot turn the full-provider eligibility gate green.
- The v2 C++20 build and all-target Foundation build have passed; the previous version's 16/16 CTest result is confirmed. The dedicated v2 live-coverage run is still executing; no v2 PASS is claimed until its own full CTest and live result complete.
- v3: NOT BUILT under R11. It cannot be created before v2 produces a real measured FAIL.
- Diagnosis D1 is specific: 175 missing 1H candle intervals and only 1.2083 days of 1H OI versus 30 days required. API documentation currently exposes only `symbol` and `period` on the OI-history endpoint, with no documented cursor or date-window parameters; therefore no undocumented pagination parameters are assumed.
- Escalation: if 1H OI is genuinely limited to the recent ~30 observations, classify Bitget as unavailable for the full L1 fallback contract. Daily OI may be recorded as a distinct lower-frequency research field only after its own coverage and freshness tests pass.
- Budget: maximum three versions; v1 and v2 only, research-only, no production activation.

## Live result

v1 failure evidence is linked above. v2 live coverage: PENDING as of 2026-11-22. Production adapter remains `NOT_IMPLEMENTED`; fallback remains `UNAVAILABLE`.
