# Third-Party Attribution

This file records third-party repositories reviewed as research references. Listing a project here does not imply that its code has been copied or integrated.

## Freqtrade

- Project: Freqtrade
- Repository: https://github.com/freqtrade/freqtrade
- Reviewed ref: `develop`
- Reviewed commit: `227997806986013fb6544d9253429855c603ca97`
- License: GNU General Public License v3.0 only (`GPL-3.0-only`)
- Copyright: retain the upstream notices if the project is ever used under its license.
- Use in Trade: concepts and architectural observations only. No source code copied. Its exchange execution and credential-handling components are excluded.

## Crypto Futures Bot

- Project: Crypto Futures Bot
- Repository: https://github.com/HuseynBabakhanov/crypto-futures-bot
- Reviewed ref: `main`
- Reviewed commit: `118c25875dce4085faf6cec43c2b270afe07ed5b`
- License: MIT
- License copyright line: Copyright (c) 2024 Huseyn Babakhanov
- Use in Trade: research ideas only. No source code copied. The repository contains exchange credentials, balance retrieval, order placement and order cancellation paths, which are prohibited by Trade's manual-only policy.

## Integration record

As of 2026-11-10, neither repository contributes copied source files or new runtime dependencies to Trade. If code is ever adopted from an MIT/BSD/Apache source in a future approved change, record the exact upstream commit, file paths, license, copyright notice, modifications, and local commit here before merging.
