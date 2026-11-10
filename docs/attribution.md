# Third-Party Attribution

This file records third-party repositories reviewed as research references. Listing a project here does not imply that its code has been copied or integrated.

## Freqtrade

- Project: Freqtrade
- Repository: https://github.com/freqtrade/freqtrade
- Reviewed ref: `develop`
- Reviewed commit: `227997806986013fb6544d9253429855c603ca97`
- License: GNU General Public License v3.0 only (`GPL-3.0-only`)
- Use in Trade: concepts and architectural observations only. No source code copied. Its exchange execution and credential-handling components are excluded.

## Crypto Futures Bot

- Project: Crypto Futures Bot
- Repository: https://github.com/HuseynBabakhanov/crypto-futures-bot
- Reviewed ref: `main`
- Reviewed commit: `118c25875dce4085faf6cec43c2b270afe07ed5b`
- License: MIT
- License copyright line: Copyright (c) 2024 Huseyn Babakhanov
- Use in Trade: research ideas only. No source code copied. The repository contains exchange credentials, balance retrieval, order placement and order cancellation paths, which are prohibited by Trade's manual-only policy.

## Additional research candidates — no source copied

| Project | Repository | Reviewed commit | License | Intended use / restriction |
|---|---|---|---|---|
| pandas-ta-classic | https://github.com/xgboosted/pandas-ta-classic | `ee71ae7b044d54ef0e628d82192dfd3c00e4ccc3` | MIT | Indicator parity and causality-test reference; no dependency added |
| purgedcv | https://github.com/eslazarev/purged-cross-validation | `ea2383bf654f06cb4542862ab2bdae8f711678cb` | MIT | Backtest-only purged CV / WF / DSR / PBO evaluation candidate; no dependency added |
| TA-Lib Python | https://github.com/TA-Lib/ta-lib-python | `c42d29c9862e5884f42bf92d2e5a98018a9839f0` | BSD-2-Clause | Optional indicator oracle; native C build needs evaluation |
| QuantStats | https://github.com/ranaroussi/quantstats | `d1a214fb906e76f974f45cdccf923b601c67a756` | Apache-2.0 | Optional performance tear-sheet reference; no dependency added |
| Alphalens Reloaded | https://github.com/stefan-jansen/alphalens-reloaded | `60755d1cc7d9d36a4c70c8344cbdb168fe99df24` | Apache-2.0 | Plan B factor diagnostics research only |
| HftBacktest | https://github.com/nkaz001/hftbacktest | `5f3ec40b2afb764e0fea112f941ed85523ef4e88` | MIT | L2/L3 microstructure backtest research only; live bot components excluded |
| CCXT | https://github.com/ccxt/ccxt | `e1579cb6bf5519fe5889e249fd60fc42d5fff8f8c` | MIT | Existing public market-data adapter; private account/trading methods remain forbidden |
| cryptofeed | https://github.com/bmoscon/cryptofeed | `f3e9096d4606656474f9dce6cf730e6ba7bf680e` | AGPL-3.0-or-later + additional term | Public order-book/funding/OI feed architecture reference only; no code import |
| vectorbt | https://github.com/polakowo/vectorbt | `07f5e85e83a5286c396f4ecfd55dfaa05f25442d` | Apache-2.0 + Commons Clause | Not selected; license restriction creates service-use ambiguity |
| backtesting.py | https://github.com/kernc/backtesting.py | `ca2e2611621e472542ba90f7243a1fa06a7d7108` | AGPL-3.0 | No code copy under current policy |
| mlfinlab | https://github.com/hudson-and-thames/mlfinlab | current public page inspected 2026-11-10 | All rights reserved | No source or package adoption |
| finlab-ml | surfaced candidate `landtml/finlab-ml` | UNVERIFIED | UNVERIFIED | GitHub REST repository lookup returned 404; not approved |

## Integration record

As of 2026-11-10, no source files from these reviewed projects have been copied into Trade and no new runtime dependency has been added by the external-repository audit. If code is ever adopted from an MIT/BSD/Apache source in a separately approved change, record exact upstream commit, file paths, license, copyright notice, modifications, and local commit here before merging.
