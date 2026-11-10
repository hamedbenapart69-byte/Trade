# Open-Source Tooling Landscape — 2026-11-10

## Scope and standard

This is a targeted landscape review of public projects relevant to Trade's current requirements: free operation, Python 3.12/GitHub Actions compatibility, crypto futures public market data, indicator correctness, leakage-safe validation, backtesting, and strict manual-trade-only delivery.

This is not an exhaustive review of every repository on GitHub. Repository metadata and source refs below are snapshots taken on 2026-11-10. Stars are popularity signals only, not quality evidence.

Trade constraints remain unchanged:
- Public market data only; no exchange account connection, API credentials, balance retrieval, or order placement/cancellation.
- Zero-cost deployment and web-first Persian dashboard.
- LFS/NSS definitions, weights, Gates, C10, SLRP, and current stage acceptance criteria are not altered by this review.
- No external code or dependency is added by this document.

## Recommended candidates

### 1. pandas-ta-classic — indicator reference and parity test candidate

- Repository: https://github.com/xgboosted/pandas-ta-classic
- Ref: `main`
- Commit: `ee71ae7b044d54ef0e628d82192dfd3c00e4ccc3`
- Snapshot metadata: 489 stars, 115 forks; Python; pushed 2026-10-31.
- License: MIT.
- Evidence inspected: 517-entry tree, GitHub Actions CI, broad tests, Hypothesis property tests, regression fixtures, and a dedicated `tests/test_lookahead.py`.
- Project scope: 224 indicators/utilities and 62 native candle patterns according to README.
- Fit: useful as an independent oracle for EMA, ATR, RSI, MACD, Bollinger, volume and other indicator parity tests. Its dedicated causality tests are especially relevant to G1.
- Caution: README documents forward-looking exceptions/semantics (including centered DPO, Chikou span, and selected other functions). Those modes must not be used as contemporaneous signal inputs. Main currently requires Python >=3.11, NumPy >=2.4.6 and pandas >=3.1.0; that is a meaningful dependency change from Trade's current lightweight runtime.
- Decision: **GOLD / REFERENCE FIRST**. Do not add to production requirements yet. First run an isolated compatibility/parity job on Python 3.12 and verify our EMA/ATR outputs against a pinned release. If dependency size or compatibility is poor, keep it as CI-only or reference-only.

### 2. purgedcv — leakage-safe research validation candidate

- Repository: https://github.com/eslazarev/purged-cross-validation
- Package: `purgedcv`
- Ref: `main`
- Commit: `ea2383bf654f06cb4542862ab2bdae8f711678cb`
- Snapshot metadata: 63 stars, 9 forks; Python; pushed 2026-11-08.
- License: MIT.
- Package metadata: version 0.1.12, Python >=3.11; dependencies NumPy, pandas, scikit-learn and SciPy.
- Evidence inspected: 203-entry tree, CI and docs workflows, unit/property/end-to-end tests, including explicit no-temporal-leakage, purge, embargo, walk-forward, CPCV, PBO and metrics tests.
- Project scope: purged k-fold, embargo, walk-forward, combinatorial purged CV, path reconstruction, PSR, DSR and PBO.
- Fit: directly relevant to the project's OOS validation and anti-overfitting requirements for Plans A/B/C/H.
- Caution: package declares alpha development status. README examples and demonstrations are not proof of crypto-futures edge. Correctness of the caller's event horizons, timestamps, labels and trial registry still matters; the library cannot infer them.
- Decision: **GOLD / RESEARCH HARNESS CANDIDATE**. Highest-priority library to evaluate in an isolated backtest-only job. Do not import into live signal generation. Pin exact version, compare its splits and DSR/PBO with independently calculated toy fixtures, then adopt only if the existing walk-forward protocol and output metrics match. It must not replace the project's 6m train / 2m test / 1m step rule without approval.

### 3. TA-Lib Python — independent indicator oracle

- Repository: https://github.com/TA-Lib/ta-lib-python
- Ref: `master`
- Commit: `c42d29c9862e5884f42bf92d2e5a98018a9839f0`
- Snapshot metadata: 12,396 stars, 2,009 forks; Cython/Python wrapper; pushed 2026-11-05.
- License: BSD-2-Clause.
- Evidence inspected: 77-entry tree, GitHub Actions test/build workflows, unit tests for function, abstract, pandas, Polars, streaming and threading APIs.
- Fit: independent reference implementation for checking RSI/EMA/ATR/MACD calculations and warm-up behavior.
- Caution: Python wrapper requires the native TA-Lib C library; installation/build adds platform and CI complexity.
- Decision: **GOLD / OPTIONAL ORACLE**. Use only in an isolated CI parity job if a clean Python 3.12 wheel/build path is confirmed. Do not make it a production runtime requirement by default.

### 4. QuantStats — report metrics candidate

- Repository: https://github.com/ranaroussi/quantstats
- Ref: `main`
- Commit: `d1a214fb906e76f974f45cdccf923b601c67a756`
- Snapshot metadata: 7,843 stars, 1,286 forks; Python; pushed 2026-11-02.
- License: Apache-2.0.
- Evidence inspected: pyproject declares pytest-based tests, Python >=3.10, and portfolio statistics/reporting.
- Fit: useful for secondary performance tear sheets and familiar metrics such as Sharpe, win rate, drawdown and volatility.
- Caution: dependency list includes pandas, SciPy, matplotlib, seaborn and yfinance; yfinance is not a suitable source of crypto-perpetual funding/OI. It does not replace DSR/PBO or our custom OOS accounting.
- Decision: **IDEAS / OPTIONAL REPORTING**. Prefer current native calculations unless a report requirement demonstrates a concrete gap. Any adoption must compare metric conventions against our own fixtures.

### 5. Alphalens Reloaded — Plan B factor diagnostics candidate

- Repository: https://github.com/stefan-jansen/alphalens-reloaded
- Ref: `main`
- Commit: `60755d1cc7d9d36a4c70c8344cbdb168fe99df24`
- Snapshot metadata: 685 stars, 158 forks; Python; pushed 2026-10-26.
- License: Apache-2.0.
- Evidence inspected: pyproject supports Python 3.11–3.15, tests and GitHub Actions; README covers factor returns, information coefficient and turnover analysis.
- Fit: potentially useful for Plan B cross-sectional factor ranking diagnostics.
- Caution: library is stock-factor oriented and its maintainers state that new development focuses on ML4T Diagnostic. Crypto perpetual factor semantics, funding, survivorship and universe membership need custom handling.
- Decision: **IDEAS / PLAN B RESEARCH ONLY**. Do not integrate until factor timestamps, delisted contracts, funding and cross-sectional ranking semantics are mapped and tested.

### 6. HftBacktest — specialist microstructure replay candidate

- Repository: https://github.com/nkaz001/hftbacktest
- Ref: `master`
- Commit: `5f3ec40b2afb764e0fea112f941ed85523ef4e88`
- Snapshot metadata: 5,065 stars, 961 forks; Rust core; last push 2025-12-23.
- License: MIT.
- Evidence inspected: README, Python package metadata, Rust workspace and license.
- Project scope: tick replay, L2/L3 book reconstruction, feed/order latency and queue-position-aware fill simulation. README also documents a Rust-only live trading bot for Binance Futures and Bybit.
- Fit: could inform a future LRT microstructure validation if timestamped full-depth historical data becomes available.
- Caution: much more complex than the current 1H/4H signal system; live trading modules must remain excluded. Its Python package requires NumPy <2.3 and has Numba/Polars/visualization dependencies. Full-depth data storage and replay are not currently part of the free GitHub Actions design.
- Decision: **IDEAS / FUTURE SPECIALIST ONLY**. No current dependency or source import.

## Excluded or constrained projects

### Freqtrade

- Repository: https://github.com/freqtrade/freqtrade
- Ref: `develop`
- Commit: `227997806986013fb6544d9253429855c603ca97`
- License: GPL-3.0-only.
- It is a mature crypto strategy/backtesting/live-bot ecosystem, but its execution and exchange-account code conflicts with C18. GPL code is excluded by the project's policy.
- Decision: concepts and test ideas only; no source copied.

### HuseynBabakhanov/crypto-futures-bot

- Repository: https://github.com/HuseynBabakhanov/crypto-futures-bot
- Ref: `main`
- Commit: `118c25875dce4085faf6cec43c2b270afe07ed5b`
- License: MIT.
- Despite the alert-only description, source includes CCXT apiKey/secret, `fetch_balance`, `create_market_order`, `create_limit_order`, `place_order` and `cancel_order` paths.
- Decision: whole repository excluded; strategy concepts only.

### vectorbt

- Repository: https://github.com/polakowo/vectorbt
- Ref: `master`
- Commit: `07f5e85e83a5286c396f4ecfd55dfaa05f25442d`
- License: Apache-2.0 with Commons Clause; repository explicitly restricts selling products/services whose value derives primarily from the software.
- Decision: not selected because the license condition creates unnecessary uncertainty for a hosted web app/service, even if the current user-facing service is intended to be free.

### cryptofeed

- Repository: https://github.com/bmoscon/cryptofeed
- Ref: `master`
- Commit: `f3e9096d4606656474f9dce6cf730e6ba7bf680e`
- License: AGPL-3.0-or-later, with an additional attribution term.
- It exposes public L1/L2/L3, trades, funding, OI, liquidations and candles across many exchanges. However current package metadata requires Python >=3.13, while the Trade workflow currently runs Python 3.12; AGPL is also excluded by project policy.
- Decision: no code import. Its normalized event model and timestamp handling may be studied as ideas only.

### backtesting.py

- License: AGPL-3.0.
- Decision: no source copy under the current project policy. Use general event-driven backtest concepts only.

### vectorbt / mlfinlab / finlab-ml status

- vectorbt is excluded for the license reason above.
- Hudson & Thames mlfinlab describes all-rights-reserved licensing; no code or package adoption.
- A web search surfaced `landtml/finlab-ml`, but the GitHub REST repository lookup returned 404 during this audit. It is therefore **UNVERIFIED** and not an approved candidate.

## Integration map for Trade

| Trade area | Best candidate | Intended use | Current decision |
|---|---|---|---|
| Indicator correctness / G1 | pandas-ta-classic | Independent EMA/ATR/RSI parity + causality tests | Evaluate in isolated CI |
| Indicator oracle | TA-Lib | Independent calculations for fixtures | Optional CI only |
| OOS / WF / DSR / PBO | purgedcv | Backtest-only validation harness | Highest priority to evaluate |
| Plan B factors | Alphalens Reloaded | IC, turnover, factor tear sheets | Research only |
| Performance reports | QuantStats | Secondary tear sheets | Not required yet |
| LRT microstructure | HftBacktest | Historical L2 replay/queue simulation | Future only; data blocker |
| Market data | Existing CCXT public endpoints | Public tickers/OHLCV/funding/OI where supported | Keep; enforce public-only code guard |
| L2/L3 real-time feeds | cryptofeed | Reference architecture only | Excluded by AGPL/Python mismatch |

## Required adoption gates

No package is to be added to the production runtime until all of the following are true:

1. Exact pinned version, commit, license and dependency tree are recorded.
2. Python 3.12/GitHub Actions install is tested from a clean runner without paid services.
3. Security review confirms no account credentials, balance endpoints, private authenticated channels, order placement or cancellation enter the runtime.
4. Numerical parity is tested on fixed, hand-calculated fixtures and pathological cases.
5. Look-ahead/causality, missing candles, gaps, duplicate timestamps, timezone, warm-up, NaN and zero-volume edge cases are tested.
6. Performance and install-time impact are measured.
7. OOS calculations are compared against independent references; no library output is accepted as truth by itself.
8. Any code copied from MIT/BSD/Apache sources receives exact path, upstream SHA, license and copyright attribution in `docs/attribution.md`.
9. GPL/AGPL/Commons-Clause/unknown-license code is not copied or imported under current project policy.
10. No change is made to locked strategy formulas, thresholds, Gates, C10 states or stage acceptance criteria.

## Project-state observation

The inspected `main` signal engine remains an EMA20/EMA50 + ATR14 MVP. Its current tests explicitly permit a `FETCH_TIME_PROXY` ticker to produce `BUY_NOW`. The separate PR #35 branch contains the proposed downgrade and stronger 4H/pullback/stop gates, but PR #35 is still open and Draft; it is not main and its OOS performance is not established.

Therefore, the immediate quality bottleneck is not a shortage of indicator libraries. It is validating and hardening the active engine, proving data freshness/coverage, and establishing reproducible OOS performance. Adding ten more indicator packages would only make the codebase heavier without proving an edge.

## Final decision

Adopt the research practices of the candidates, not entire trading bots. Prioritize an isolated `purgedcv` evaluation for OOS validation, then pandas-ta-classic and TA-Lib parity/causality tests. Keep all new libraries out of the live runtime until their dedicated compatibility and security gates pass. No source code or dependency was added by this audit.
