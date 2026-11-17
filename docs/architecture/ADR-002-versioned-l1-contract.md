# ADR-002: Versioned L1 Market Data Contract and Provenance

- **Status:** ACCEPTED FOR STAGE 1 IMPLEMENTATION
- **Effective date:** 2026-11-17
- **Owner approval basis:** The project owner approved the Hybrid Stage 1 implementation plan.
- **Related decision:** ADR-001

## Decision

Python L1 exports raw public-market observations through `contracts/l1-market-data.v1.schema.json`. C++ L2 independently validates the contract before admitting any observation.

The initial vertical-slice contract uses 1-hour candles and exact linear USDT-settled perpetual instrument identity. The 10-instrument integration target is a bounded first slice, not proof of full 100-symbol coverage.

## Required run-level fields

- schema version and unique run ID;
- producer name/version/source commit;
- acquisition timestamp in UTC;
- timeframe and requested time window;
- primary provider identity, display name, and fallback declaration.

## Required instrument-level fields

- exchange instrument ID and unified symbol;
- base, quote, settlement currency, contract type, and contract size;
- provider identity and timeframe;
- OHLCV timestamps and numeric values;
- explicit candle completion and retrieval timestamp;
- funding and open-interest observations, preserving nulls;
- independent availability labels;
- coverage counts/percentage and error list.

## Numeric and temporal rules

- Missing values remain JSON null and are never coerced to zero.
- NaN and Infinity are rejected.
- OHLCV timestamps must be unique and strictly increasing.
- Only completed candles are exported as completed observations.
- OHLC relationships and non-negative volume are checked.
- Future-dated or stale observations must not be admitted by C++.
- Provider fallback must not silently combine incompatible contract identities. Exact equivalence is required.
- Availability and data quality are distinct from operational health.

## Ownership

Python may acquire, normalize the exchange response shape, and serialize observations. It must not compute features, signals, C10 states, strategy scores, gates, risk, confidence, or EV.

C++ independently checks the version, identity, series chronology, numeric finiteness, OHLC relationships, candle completion, freshness, and availability before producing an L2 artifact.

## Versioning and compatibility

Breaking changes require a new schema major version and explicit C++ support. Unknown major versions fail closed. Additive optional fields may be introduced only with backward-compatible schema and consumer tests.

## Current implementation boundary

This ADR authorizes the Stage 1 contract implementation. It does not assert that the contract exporter, C++ consumer, full data coverage, or Stage 1 acceptance has passed. All claims require CI and real-run evidence.
