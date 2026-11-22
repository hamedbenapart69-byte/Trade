# Constitution and Master Source Version Register

## Current normative source

**ACCEPTED — V19.0 is the single controlling project specification as of 2026-11-22.**

- Source file: `UNIFIED_CRYPTO_FUTURES_SYSTEM_V19.0_MASTER.md`
- Source path: `docs/constitution/UNIFIED_CRYPTO_FUTURES_SYSTEM_V19.0_MASTER.md`
- Owner acceptance: explicit decision in the conversation dated 2026-11-22.
- Activation commit: `aa1c02748b5d7e60966d9d352c6dcb695a1109dc`
- Source SHA-256 recorded from the owner-provided activated file: `96dbd3bc5fe672a09f3f7bd680e40549c24a3df1b9da4ed0abc044498a3191bf`

## Archived master

- V18.2 remains preserved in the repository as a historical archive.
- V18.2 is no longer the controlling source.
- No V18.2 implementation status is carried forward as proof of V19.0 acceptance.

## Owner-approved V19.0 amendments and execution constraints

1. Python is the official L1 acquisition implementation; C++ remains authoritative for L2 compute and L3 Telegram delivery (ADR-001 approved by owner).
2. Stage 1 is a one-symbol BTCUSDT perpetual vertical slice.
3. Stage 1 data source: Binance Vision for the initial BTCUSDT L1 JSON export, with provenance, exact contract mapping, timestamps and versioned schema.
4. Stage 2 target: LRT 15m over 27 eligible contracts; confidence remains UNCALIBRATED until valid calibration evidence exists.
5. Overlap-safe OOS aggregation is mandatory. Duplicate OOS trades must not inflate pooled sample counts.
6. Brier Score is not sufficient alone for quality or release acceptance.
7. A 5–10 daily signal count is a KPI, never a minimum or a reason to weaken gates.
8. Telegram is the only user-facing delivery channel. No exchange-account connection, private trading keys or order execution.
9. Stage deadlines: Stage 0 up to 24 hours; Stage 1 up to 48 hours after Stage 0 PASS; Stage 2 up to one week after Stage 1 PASS; Stage 3 up to three days after Stage 2 PASS. If a deadline is exceeded, stop and state the exact blocker; do not relax acceptance criteria.

## Repository baseline at V19.0 activation

- Previous `main` baseline: `143999c8d67dba3851d00568e00287f26e7aad4e`
- Repository: `hamedbenapart69-byte/Trade`
- Default branch: `main`
- Repository permissions observed: admin=true, push=true.
- This register records source authority only. It does not declare any implementation stage PASS.

## Historical V9 source integrity

| Source | SHA-256 | Pages |
|---|---|---:|
| V9.0 `rules 1(2).pdf` | `1dbdbcca127bd368b025a554b205970b7221fe22f68139908402c8d04f1db2f3` | 54 |
| V9.1 `rules 1.1(1).pdf` | `862307dbc8cae72bfac03de24686f52c0a28d170afe26a69d4e27f22a21cf0a8` | 55 |

