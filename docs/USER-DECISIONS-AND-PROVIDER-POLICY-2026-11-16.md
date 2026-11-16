# Owner Decisions: Telegram-Only Delivery and Provider-Neutral Data Architecture

**Recorded:** 2026-11-16  
**Status:** Owner-approved product decisions; implementation and release acceptance remain separate.  
**Repository baseline:** `main` at `d1816817e8aaa4b6f54c14da5cdfa4f9870b98cc`.

## 1. Binding owner decisions

The owner has explicitly confirmed the following decisions in the project conversation on 2026-11-16. These decisions are binding for subsequent design and implementation unless the owner explicitly changes them.

### D-001 — No exchange-account or trading integration

The system is a market-analysis and futures-signal intelligence platform, not a trading bot.

Prohibited:
- Connecting any user exchange account.
- Requesting, receiving, storing or using trading API keys or private account credentials.
- Reading private balances or positions.
- Placing, modifying or cancelling real or paper orders through an exchange.
- Managing leverage or positions on the user's behalf.

The system may read permitted public market information. Public market-data collection is not an exchange-account connection, but exchange-specific endpoints must not become an architectural single point of failure or the assumed primary solution.

### D-002 — Backend tool access is not a user-facing restriction

The owner does not personally register for, log into, configure, pay for, VPN into or connect to analytical data providers.

The project engineering/runtime layer is responsible for selecting and using the best genuinely free tools and data sources that are technically reachable and legally permitted from the actual compute environment. A provider's restriction on direct access by Iranian end users is not, by itself, a reason to exclude it from backend evaluation.

For each provider, separately verify:
- Reachability from the actual project compute runtime.
- Whether account registration, identity verification, VPN or payment is required for the backend.
- Free-plan quotas and whether they are permanent or trial-based.
- Data fields, market/instrument coverage, update cadence and historical depth.
- Timestamp semantics, revisions, gaps and data quality.
- Licence and permitted automated use, retention, derived outputs and redistribution.
- Failure behavior, rate limits and a tested fallback.

This decision does not authorize bypassing authentication, access controls, sanctions, contractual restrictions or provider terms. If a source is not lawfully or technically usable by the backend, record the exact reason and evaluate another source. Do not transfer setup work to the owner.

### D-003 — Telegram is the sole user-facing operational product

The owner only needs to open Telegram and receive the final futures-signal messages.

- Telegram is the sole required user-facing delivery channel.
- The owner must not be required to use a charting site, data-provider console, dashboard, API tool or cloud console.
- A browser dashboard may exist as an internal engineering/diagnostic artifact only if useful, but it is not the owner's daily operating interface and must not be a prerequisite for receiving signals.
- Signal delivery must be idempotent, timestamped and linked to an immutable signal identity.
- A Telegram API acknowledgement proves message acceptance by Telegram, not that the owner has read it.
- Delivery failures must be visible to the system's health/operations logic and must not silently discard a signal.

**Authority conflict to reconcile:** Earlier companion text (V13.0 §32.1 C16 and §38.4) describes web-first delivery and Telegram as secondary. D-003 is the owner's later, explicit product decision and changes that delivery preference: Telegram becomes primary and required; a dashboard is optional/internal. This crosswalk must be reflected in the next approved specification revision. Do not silently claim the old web-first wording still represents the owner's current preference.

## 2. Provider-neutral architecture

The system must evaluate tools by the information they add to signal quality, not by brand loyalty or the user's ability to log into them.

Logical layers:
1. **Chart and market context:** visual charting, market breadth, price discovery and context.
2. **Numerical data acquisition:** machine-readable OHLCV, contract metadata, funding, open interest, liquidations, trade prints, order-book history, on-chain observations, news and sentiment.
3. **Normalization and evidence:** UTC timestamps, instrument identity, source provenance, schema validation, freshness, gaps, duplicate detection and disagreement analysis.
4. **Feature and research compute:** indicators, market structure, order flow, LRT/NMT, Plans A/B/C/H, calibration, risk and independent validation.
5. **Delivery:** approved, immutable signal records delivered through Telegram.

A chart-rendering product is not automatically a data provider. For example, TradingView Advanced Charts documentation states that the library itself does not provide market data; an external datafeed must be implemented. Numerical engine inputs must be independently retrievable and auditable.

No provider is permanently trusted. Use multiple independent providers where they contribute genuinely independent evidence. Do not average conflicting values blindly. Preserve source identity and data semantics. Mark unavailable measurements `UNAVAILABLE` and approximations `PROXY`; never fabricate real order flow, liquidation or on-chain observations.

## 3. Initial public-provider screening (not yet integration approval)

The following is a preliminary, source-backed screening snapshot. It is not proof of live runtime connectivity, legal suitability for every intended use, or production acceptance.

| Provider | Verified public information | Preliminary role | Current decision |
|---|---|---|---|
| CryptoHFTData | Official docs describe hourly Parquet datasets for L2 order books, tick trades, liquidations, OI and funding across nine venues; history begins 2025-06-28; each hour is published about 15 minutes after close; REST works without a key at up to 60 requests/minute. | Historical microstructure/order-flow research, historical OI/funding and backtest enrichment. Not a live feed and not a two-year history source. | HIGH-PRIORITY CANDIDATE; test actual files, gaps, licence, coverage and runtime reachability before adoption. |
| CoinGecko Demo API | Official pricing page lists $0, no credit card, 10,000 calls/month and 100 calls/minute; API covers aggregated markets, on-chain endpoints and derivative exchange metadata. Historical endpoint depth varies by endpoint and plan. | Broad asset discovery, market context, asset metadata and selected on-chain/derivatives discovery fields. | CANDIDATE; do not assume its free plan supplies two-year intraday perpetual OHLCV or all required derivatives history. |
| CoinPaprika Free | Official API pages list no-key access, 20,000 calls/month per IP, up to 2,000 assets, one-year daily price history and only latest full-day OHLCV on Free. | Independent market discovery and daily cross-checks. | SECONDARY CANDIDATE; insufficient as the core intraday futures feed. |
| Coin Metrics Community | Official docs state Community data is free under Creative Commons, no API key for community endpoints, with a limit of 10 requests per 6 seconds; Atlas history is limited to 30 days for selected assets and reference rates have limited granular history. | Selected network/on-chain and reference-rate context. | CANDIDATE for specific metrics only; not a substitute for futures order flow or complete market data. |
| DefiLlama Free API | Official docs describe free API endpoints without a key; the free yield endpoints `/pools` and `/chart/{pool}` were shut down on 2026-11-13 and moved to API-plan endpoints. | DeFi protocol, TVL and documented free endpoint context. | CANDIDATE only after endpoint-by-endpoint review; do not use discontinued free yield routes. |
| CoinGlass API | Official plan documentation lists Hobbyist at $35/month; the lowest API plan is paid. | Strong derivatives/OI/funding/liquidation/order-flow coverage. | EXCLUDED from the zero-cost core; monitor only if a genuinely free endpoint is documented later. |
| TradingView Advanced Charts | Official docs say the chart library does not provide data; an external datafeed is required. Access to the Advanced Charts repository is gated. | Optional chart presentation/visualization, not a numerical source. | NOT A CORE DATA PROVIDER; never confuse the chart with its datafeed. |

Provider references:
- CryptoHFTData datasets: https://www.cryptohftdata.com/datasets
- CryptoHFTData docs: https://www.cryptohftdata.com/docs
- CoinGecko pricing: https://www.coingecko.com/en/api/pricing
- CoinGecko API: https://www.coingecko.com/en/api
- CoinPaprika pricing: https://coinpaprika.com/api/pricing
- CoinPaprika docs: https://coinpaprika.com/developers
- Coin Metrics Community: https://docs.coinmetrics.io/packages/coin-metrics-community-data
- DefiLlama docs: https://api-docs.defillama.com/
- CoinGlass plans: https://docs.coinglass.com/reference/plans-and-permissions
- TradingView datafeed tutorial: https://tradingview.com/charting-library-docs/latest/tutorials/implement_datafeed_tutorial/

## 4. Current implementation evidence and blocker

Verified on 2026-11-16:
- PR #131 was merged into `main` at `d1816817e8aaa4b6f54c14da5cdfa4f9870b98cc`.
- GitHub Actions run `43879014391` completed successfully and persisted the P0 dataset to the `market-data` branch.
- The persisted `datasets/stage1b/data_report.json` reports `status=DEGRADED`, `symbols_complete=26/27`, `symbols_fresh=26/27`, and `signal_engine_executed=false`.
- FILUSDT has 431 of 631 expected tail bars, 200 missing bars and two continuity gaps; MEXC reports the contract is not listed. The report records Bybit HTTP 403 and Binance HTTP 451 in the runner, while OKX/MEXC results vary by symbol.
- The P0 persistence workflow's artifact-cleanup job completed; no artifact remained in the run artifact listing at the time of this audit.

Therefore, this run proves successful dataset validation/persistence workflow execution, not a complete data gate, a signal-engine run, a Telegram signal delivery, or Stage 1 PASS.

## 4.1 Provider-specific retention and redistribution controls

The repository `hamedbenapart69-byte/Trade` is **public** (verified 2026-11-16). CryptoHFTData's Terms & Licensing page, last updated 2026-10-06, permits personal/internal use and keeping downloaded files on the user's own servers or cloud/hosting providers, but prohibits sharing, redistributing, republishing, or embedding raw data in downstream products. It explicitly permits derived signals, features, models and analysis when the underlying data cannot be reconstructed.

Therefore:
- CryptoHFTData raw Parquet files may be downloaded and processed transiently inside the GitHub Actions runner for internal computation.
- Do **not** commit, publish, upload as public workflow artifacts, or otherwise expose raw CryptoHFTData files or reconstructable tables to the public repository, public Pages, Telegram or any third party.
- Persist only sanitized provenance, row counts, quality metrics, non-reconstructable features, signal records and derived research results that cannot recreate the underlying feed.
- Remove raw provider data from the runner after the computation step; do not place it in the public `market-data` branch.
- Any change to repository visibility, retention or distribution model requires a fresh licence review; do not assume a private repository or public Telegram channel is permitted without checking the exact terms.

Official terms: https://www.cryptohftdata.com/terms  
The provider's terms explicitly permit AI tools/processors used for internal inference/research, while retaining the no-redistribution rule.

## 5. Execution policy

- Continue reversible research, documentation, provider probes, isolated code branches and tests without asking the owner to configure backend providers.
- Do not relax frozen thresholds, gates, risk limits or statistical acceptance criteria.
- Do not use a provider merely because it exists; measure the information gain and data quality.
- Do not build v2/v3 after a v1 PASS. Build alternatives only after a documented real FAIL and diagnosis.
- Preserve separate logic and performance ledgers for Plans A/B/C/H and separate signal profiles where approved.
- No production deployment, merge of material implementation changes, secret changes, destructive repository action or change to frozen numeric gates without the required explicit approval.
- Stage advancement remains evidence-gated. “Continue until completion” authorizes diligent progression through reversible work; it does not authorize bypassing acceptance criteria or claiming a PASS without evidence.

## 6. Immediate next work

1. Complete the provider-neutral inventory by data category, prioritizing independent aggregators and data vendors; retain public exchange endpoints only as optional backend sources where they add unique data and never as the user-facing integration.
2. Run bounded read-only probes from the actual GitHub Actions runtime for high-priority candidates, capturing status, response time, schema, timestamp, symbol coverage, history depth, quota behavior and reproducibility.
3. Evaluate CryptoHFTData as a historical microstructure candidate, explicitly respecting its hourly publication delay and June 2025 history start.
4. Diagnose FILUSDT missing baseline/tail coverage and determine whether the instrument should be replaced in the research universe or supplied by a verified independent data source. Do not silently drop it or fabricate candles.
5. Reconcile Telegram-only delivery with V13 C16 and the older web-first design docs in the next specification update.
6. Re-run the Stage 1 acceptance only after L1, L2 and Telegram L3 evidence are all available; require two consecutive valid L2 runs as specified.

