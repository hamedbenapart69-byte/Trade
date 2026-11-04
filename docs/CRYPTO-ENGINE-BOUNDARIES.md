# Autonomous Crypto Engine — isolated development boundary

## Scope

This work is developed only on branch `autonomous-crypto-engine` in this repository. It is independent of any separate Cloud/Claude project. Do not inspect, modify, import, deploy, or coordinate against that project.

## Production safety

- No Railway CLI, Railway API, deployment token, production environment, database, or service mutation is permitted in this workstream.
- The Railway deployment workflow on this repository is restricted to successful CI runs on `main`; feature-branch CI runs must never deploy.
- Do not merge this branch or change `main` without a separate explicit approval.
- Do not add secrets, exchange credentials, or private keys to Git.
- Market data integrations are read-only and must use independent public data providers; no exchange account connection or order execution.

## Decision authority

The quantitative decision engine is deterministic and returns one of: BUY_NOW, CONDITIONAL_BUY, WAIT, REJECT, INSUFFICIENT_DATA. Missing, stale, contradictory, or invalid evidence must never be converted into a buy signal. The language model may explain a decision but cannot override its gates.

## Initial implementation milestone

The first isolated milestone adds pure-Python, provider-agnostic OHLCV validation, technical indicators, correlation, and deterministic decision gates. This is not yet a complete market scanner or a validated profitable strategy. Thresholds are initial policy defaults and must be calibrated through historical and out-of-sample tests before operational use.

## Required future gates

1. Multi-provider market universe discovery and source freshness/provenance.
2. Historical OHLCV ingestion and deduplication across 15m/1h/4h/1d/1w.
3. Derivatives and on-chain adapters with explicit coverage flags.
4. Ten individually testable quantitative models with no fabricated probability outputs.
5. Portfolio covariance, drawdown, volatility and constrained optimization.
6. Backtest with fees, slippage, survivorship and look-ahead-bias controls.
7. Paper-trading period and signal calibration.
8. Independent review and explicit approval before any production deployment.
