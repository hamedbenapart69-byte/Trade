# Constitution and Master Source Version Register

## Current normative source

**ACCEPTED — V18.2 is the single controlling project specification.**

- Source file: `UNIFIED_CRYPTO_FUTURES_SYSTEM_V18.2_MASTER-1(1).md`
- SHA-256: `e4e39fc1aec1924f93d9a480fadf6b2ad315388ebb5718ed9765ad89477b6a24`
- Owner acceptance: explicitly recorded in the project instruction “V18.2 MASTER SOURCE ACCEPTED — INITIATE C++ STAGE 1”.
- Binding conflict-resolution record: [V18.2 Owner Acceptance and Errata](V18.2_OWNER_ACCEPTANCE_AND_ERRATA.md).
- Source register: [SOURCE_REGISTER.md](SOURCE_REGISTER.md).

## Binding post-acceptance amendments

1. C++ is the only production implementation language for the remaining L1/L2/L3 path. Python is legacy/auxiliary only; the V18.2 Part XIV hybrid Python-L1 proposal is superseded by the later owner direction.
2. Telegram is the only user-facing delivery channel. Web dashboard and email are not production delivery dependencies.
3. Data acquisition is backend-owned and uses permitted public endpoints only. No user exchange account, private trading key, account balance, private endpoint or order execution is permitted.
4. The verified runner currently uses C++20. This is an implementation choice supported by successful builds, not a literal standard-version requirement in V18.2.

## Historical V9 source integrity

| Source | SHA-256 | Pages |
|---|---|---:|
| V9.0 `rules 1(2).pdf` | `1dbdbcca127bd368b025a554b205970b7221fe22f68139908402c8d04f1db2f3` | 54 |
| V9.1 `rules 1.1(1).pdf` | `862307dbc8cae72bfac03de24686f52c0a28d170afe26a69d4e27f22a21cf0a8` | 55 |

These are archived historical source identities. Their hashes were recalculated from the uploaded PDFs. Hash registration is not a binary backup.

## Open source-integrity items

- Original V10.0 source bytes are absent from the current accessible bundle. Exact V10.0 crosswalk: **OPEN / NOT VERIFIED**.
- Full V18.1 source bytes are absent from the current accessible bundle. Exact line-level V18.1 diff: **OPEN / NOT VERIFIED**.

No missing source is reconstructed or represented as reviewed.

## Implementation status is separate from source acceptance

- Stage 0 source acceptance: **PASS**.
- Stages 1–5: PASS at the scope documented in their SLRP reports.
- Stage 6: engineering pipeline executed successfully; statistical calibration remains BLOCKED / NOT_CALIBRATED.
- Stage 7: BLOCKED / FAIL-CLOSED.
- Stages 8–15: GATED; no later-stage PASS is claimed.
- A document acceptance or a green build does not prove production quality, calibrated edge or profitability.

## Historical V9 source-registration record

- Original main baseline: `3941d8b77b3172f0b3fe3372ba96521d580e3432`
- Initial source-register commit: `e943fa154f482dbbab547fd0eaaa2b0969a126cc`
- Initial P0 evidence addendum: `6052acf815e82bf97b9dbf6cf10bd4471005f5c9`
- V9 source-registration acceptance: `d928f3e8d93d9c69a8937d28a3d2e9c573e1b86f`
- Original PR #81 merge: `5dcb05e39f8164d805cf32d7b72c421b44cf075a`
