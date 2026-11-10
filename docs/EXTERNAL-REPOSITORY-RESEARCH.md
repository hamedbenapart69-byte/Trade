# External Repository Research Ledger

**Target:** hamedbenapart69-byte/Trade  
**Research branch:** research/external-structure-v1  
**Base commit:** 39eb24aba7a75249b68a4e714517715ff2595abd  
**Policy:** Extract concepts and independently implement only what fits the existing architecture. No bulk imports, no strategy copying, no exchange account access, no order execution.

## Initial repository screen

| Repository | License observed | Candidate value | Decision |
|---|---|---|---|
| [joshyattridge/smart-money-concepts](https://github.com/joshyattridge/smart-money-concepts) | MIT | FVG, swing points, BOS/CHoCH definitions | **Extracted concept:** causal FVG + delayed swing confirmation. Original implementation uses negative shifts and future mitigation scans; those outputs must not be used as live-time signals. |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | GPL-3.0 | Look-ahead and recursive-analysis validation methods | **Method only:** use sliced-vs-full indicator invariance and recursive stability checks. No Freqtrade source code copied; GPL implications make direct code import undesirable. |
| [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) | Apache-2.0 | Risk/performance reporting and drawdown metrics | Candidate for independent metric cross-check. Do not use period-based returns as a substitute for trade-level statistics. |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) | MIT | Backtest/report architecture and crypto market handling | Pending deeper source/test audit before any extraction. |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | MIT | Unified public exchange market-data interfaces | Candidate only where it improves existing adapters; current collectors already use native public APIs, so no dependency added yet. |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | AGPL-3.0 | Lightweight backtesting mechanics | **Hold:** AGPL network/distribution implications require legal review; no code copied. |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | NOASSERTION from GitHub metadata | Vectorized research/backtesting | **Blocked pending license verification.** No code or dependency added. |

## EXT-007 — Causal market structure primitives

- Source concept: FVG and swing-point definitions from smartmoneyconcepts.
- Implementation: signal_autopilot/modules/market_structure.py.
- Tests: signal_autopilot/tests/test_market_structure.py.
- License: source repository reports MIT. This implementation is independently written; no source file was copied.
- Critical correction: source FVG uses negative shifts and mitigation scans future candles; swing points require right-side candles. This implementation timestamps FVG at the third candle close and swings at the first confirmation index. Backtests must execute no earlier than the next tradable bar.
- Intended path: Plan A (LRT structure context), initially research-only. Not wired into live BUY/SELL decisions.
- Status: awaiting CI and independent look-ahead tests.

## Validation gates before production use

1. Unit tests for direction, boundaries, malformed OHLC, and confirmation delay.
2. Prefix invariance: appending future candles must not change previously emitted events.
3. Walk-forward/OOS evaluation before any signal weighting.
4. No live engine wiring until the research-only PR passes.
5. Preserve attribution and license metadata for any future copied/adapted code.
