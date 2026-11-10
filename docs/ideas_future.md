# Future Research Ideas — External Repository Review

These are research candidates only. They are not active strategies, not approved signals, and not part of LFS_v2.

## Candidate concepts from Crypto Futures Bot

Source: https://github.com/HuseynBabakhanov/crypto-futures-bot  
Reviewed commit: `118c25875dce4085faf6cec43c2b270afe07ed5b`  
License: MIT. No source code copied.

1. **Multi-touch level breakout** — support/resistance levels built from repeated touches, followed by a breakout and volume confirmation.
2. **False breakout / failed auction** — price breaches a prior level, fails to hold beyond it, and returns through the level. The upstream README says its false-breakout module was disabled after negative expectancy; treat this as a warning, not evidence of edge.
3. **Impulse with volume expansion** — price displacement confirmed by relative volume.
4. **Trend-volume expansion** — higher-timeframe trend context with lower-timeframe entry and volume confirmation.

### Required research before implementation

- Write a numerical hypothesis and a falsification condition before coding.
- Use timestamp-safe, closed-candle data and explicitly test for look-ahead/leakage.
- Include fees, slippage, funding, liquidity and realistic fill assumptions.
- Run walk-forward OOS validation and compare with the project's required baselines.
- Report sample size, Win, PF, expectancy, MaxDD, Sharpe, Brier, DSR and PBO where applicable.
- Keep each generator independent and preserve C10's seven output states.
- Do not weaken existing thresholds or acceptance criteria to make a candidate pass.

## Candidate engineering concepts from Freqtrade

Source: https://github.com/freqtrade/freqtrade  
Reviewed commit: `227997806986013fb6544d9253429855c603ca97`  
License: GPL-3.0-only. No source code copied.

Potential references:
- Backtesting result analysis and reproducibility practices.
- Dedicated look-ahead analysis and recursive-analysis test concepts.
- Exchange market-data abstraction and broad test organization.

No Freqtrade execution, API credential, order lifecycle, wallet, or live-trading code may enter Trade.

## Promotion rule

A concept remains here until it has a separate design, data availability assessment, implementation plan, tests, and OOS evidence. It must not silently modify LFS_v2, NSS, Plan A/B/C/H, Gates, or locked weights.
