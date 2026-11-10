# External Repository Audit — 2026-11-10

## Scope and decision

Reviewed the public GitHub repositories and the requested refs:

- `freqtrade/freqtrade`, branch `develop`
- `HuseynBabakhanov/crypto-futures-bot`, branch `main`

No third-party source code has been copied into this repository. No dependency has been added. No trading integration has been enabled.

## R1 — Repository identity

### Freqtrade

- URL: https://github.com/freqtrade/freqtrade
- Ref: `develop`
- Snapshot commit: `227997806986013fb6544d9253429855c603ca97`
- Commit timestamp: `2026-11-09T06:08:12Z`
- GitHub metadata at audit time: 56,726 stars; 11,729 forks; 779 subscribers
- GitHub primary language: Python
- License: `GPL-3.0-only` (confirmed by repository metadata and `pyproject.toml`)
- Repository tree: 879 entries; includes a substantial automated test tree and GitHub Actions workflows.

### Crypto Futures Bot

- URL: https://github.com/HuseynBabakhanov/crypto-futures-bot
- Ref: `main`
- Snapshot commit: `118c25875dce4085faf6cec43c2b270afe07ed5b`
- Commit timestamp: `2025-10-07T05:52:52Z`
- GitHub metadata at audit time: 0 stars; 0 forks; 0 subscribers
- GitHub primary-language classification: Roff, although the application source is predominantly Python
- License: MIT; LICENSE copyright line identifies Huseyn Babakhanov, 2024
- Repository tree: 93 entries. It contains `test_setup.py`, backtest scripts and data, but no conventional `tests/` tree or `.github/workflows/` CI workflow was present in the inspected tree.

## R2 — Security and execution boundary

### Freqtrade: dangerous for direct integration

The project is explicitly an automated trading bot. The inspected current source includes exchange credential configuration and live order lifecycle code. For example, `freqtrade/freqtradebot.py` calls the exchange order-creation path; `freqtrade/exchange/exchange.py` initializes CCXT clients and reads API credential fields. This conflicts with Trade's manual-trade-only boundary.

License is GPL-3.0-only. Under the project's integration policy, no Freqtrade source code may be copied into Trade. It may be referenced for ideas only.

### Crypto Futures Bot: confirmed dangerous execution and credential code

The repository's claim that it is alert-only is contradicted by its source:

- `exchanges/exchange_manager.py` creates CCXT clients with `apiKey` and `secret`.
- The same file implements `get_balance()` using `fetch_balance()`, `place_order()` using `create_market_order()` and `create_limit_order()`, and `cancel_order()`.
- `strategies/strategy_manager.py` calls `place_order()` when `config.is_trading_enabled()` is true.
- `exchanges/binance_futures.py` reads API key and secret configuration and initializes a CCXT Binance client.
- `.env.example`, `config.example.json`, and `SETUP.md` document exchange API key/secret fields.

These are direct, source-confirmed violations of Trade's C18 boundary. The repository must not be imported or run as a whole. Its MIT license does not make unsafe functionality acceptable.

The targeted source review confirms the above dangerous paths. This report does not claim a formal third-party security certification or a complete dependency vulnerability audit.

## R3 — Classification

| Repository / component | Classification | Decision |
|---|---|---|
| Freqtrade execution, credential, exchange-account code | DANGEROUS | Exclude completely |
| Freqtrade backtesting, lookahead-analysis concepts, test architecture | IDEAS | Reference only; GPL code not copied |
| Crypto Futures Bot exchange manager, credential configuration, balance/order methods | DANGEROUS | Exclude completely |
| Crypto Futures Bot level-breakout / false-breakout / impulse / trend-volume concepts | IDEAS | Research notes only; no code import |
| Crypto Futures Bot Telegram formatting concepts | FILTER | Reimplement independently only if it fills a verified gap; existing Trade notifier remains authoritative |

## R4 — Integration map

No source file from either repository is approved for direct integration.

Potential future research topics are recorded in `docs/ideas_future.md`. They are not part of LFS_v2, do not alter its locked formula or weights, and cannot be promoted into production without a separately specified hypothesis, falsification condition, tests, and out-of-sample evidence.

Freqtrade is useful as a reference for mature backtesting/test organization, but its GPL license and execution-centric architecture make source reuse incompatible with the project's policy.

Crypto Futures Bot has an MIT license, but its strategy modules are coupled to exchange managers and a trading-enabled path. Any future clean-room implementation must be independently designed and tested. No code is being extracted in this audit.

## R5 — Project impact

- No third-party code copied.
- No third-party dependency added.
- No LFS_v2 formula, weight, threshold, Gate, or C10 behavior changed.
- No live workflow, Telegram delivery, or exchange connection changed.
- No merge or deployment performed.

## R6 — Attribution

Source identities and licenses are recorded in `docs/attribution.md`. The references are acknowledged; no code from either repository is incorporated by this audit.
