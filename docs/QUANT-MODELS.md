# Quantitative factor models

The ten models in `app/quant/models.py` emit deterministic factor scores from 0 to 100. They are **not probabilities**, forecasts, or standalone buy signals. A model returns `INSUFFICIENT_INPUTS` rather than filling missing values.

## Input conventions

- Percentage fields are percentage points (e.g. 2.5 means +2.5%).
- `volume_ratio_20` is latest volume divided by the mean of the previous 20 completed candles.
- `rsi_14`, `adx_14`, `bollinger_percent_b`, `zscore_20`, `*_score` are numeric indicator/factor values.
- `close_above_resistance` is 1 for true and 0 for false.
- `exchange_netflow_supply_pct` is net exchange inflow as a percentage of circulating supply; negative means net outflow.
- Growth and relative-return fields use the stated lookback and percentage units.
- Catalyst scores and risk component scores must be independently evidenced and normalized 0-100 by their adapters.

## Models

1. Momentum: 1h/4h/1d returns plus RSI.
2. Early accumulation: volume expansion, OBV slope, muted price movement and range compression.
3. Breakout: distance to resistance, volume ratio, ADX and confirmed close above resistance.
4. Mean reversion: RSI, Bollinger %B, z-score and trend-strength penalty.
5. Relative strength: 7d and 30d return relative to BTC.
6. Fundamental growth: revenue, active-user and developer growth plus token value-capture quality.
7. On-chain accumulation: exchange netflow, whale balance change and active-address growth.
8. Catalyst: independently verified catalyst quality, time proximity and delivery-risk score.
9. Risk-adjusted: liquidity less volatility, drawdown, unlock and contract-risk penalties.
10. Multi-timeframe confluence: weighted 15m/1h/4h/1d trend alignment.

The initial formulas are transparent engineering baselines, not backtested or calibrated. Before signals are treated as validated, they require historical out-of-sample evaluation, transaction-cost modeling, parameter sensitivity checks and forward paper trading.
