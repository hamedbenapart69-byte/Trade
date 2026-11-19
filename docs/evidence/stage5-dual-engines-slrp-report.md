# STAGE 5 — INDEPENDENT LRT / NMT ENGINES (V18.2)

**Result:** PASS — LRT v1 and NMT v1 independent candidate engines.  
**Implementation:** C++20.  
**Delivery:** Telegram only.  
**Active versions:** LRT_V1 and NMT_V1.  
**Confidence:** NOT_CALIBRATED.  
**Output:** candidate/no-setup reports only; never actionable.

## Architecture and invariants

- LRT and NMT are separate engines with separate hypotheses, features, gates, falsification conditions and output artifacts.
- No blended LFS/NSS score exists.
- LRT consumes LFS plus confirmed Stage 4 liquidity events.
- NMT consumes directional NSS plus Stage 4 market phase and breakout/volume evidence.
- The only cross-engine interaction is the hard Golden Rule veto.
- All upstream artifacts must match the exact L1 bytes, run ID, scan ID and decision timestamp.
- Missing LFS or either NSS direction blocks both engines because the Golden Rule cannot otherwise be evaluated.
- No account connection, order execution, BUY_NOW/SELL_NOW or actionable trade is produced.

## v1 hypotheses and gates

### LRT — 30m to 4h

Hypothesis: a confirmed active demand/supply zone is swept and reclaimed/rejected by a closed 4H candle with relative quote volume >= 1.20; this is a candidate for short-horizon liquidity reversion.

- LONG: last closed 4H low below active demand-zone low and close above demand-zone high.
- SHORT: last closed 4H high above active supply-zone high and close below supply-zone low.
- Zone must have been confirmed before the trigger candle closed.
- LFS is reported independently; it is not blended with NSS.
- Falsification: a later closed 4H candle closes beyond the sweep extreme or the zone is invalidated.

### NMT — 1 to 7 days

Hypothesis: directional phase, 20-bar 4H breakout, relative quote-volume expansion >= 1.20 and directional NSS jointly support a continuation candidate.

- LONG: UPTREND and last close above the preceding 20-bar high.
- SHORT: DOWNTREND and last close below the preceding 20-bar low.
- Relative quote volume >= 1.20 against the preceding 20 closed 4H bars.
- NSS_LONG or NSS_SHORT is used only by NMT.
- Market-derived participation inputs are PROXY; no external-news claim is made.
- Falsification: a later 4H close returns through the breakout level or phase loses directional alignment.

### Golden Rule

At the same decision timestamp:

`LFS > 0.70 AND max(NSS_LONG, NSS_SHORT) > 0.70 => NO_TRADE`

- Strict greater-than; exactly 0.70 does not trigger.
- Veto blocks both engines and clears candidate reference prices.
- Missing LFS/NSS data blocks both engines as INSUFFICIENT_DATA.

## Numeric acceptance

1. Shared L1 hash, run ID, scan ID and decision timestamp: PASS.
2. LFS 5/5 and NSS LONG/SHORT 5/5 for both instruments: PASS.
3. Independent LRT and NMT artifacts: PASS.
4. Synthetic LRT sweep/reclaim test: PASS.
5. Synthetic NMT phase/breakout/volume test: PASS.
6. Golden Rule strict threshold, veto and missing-input tests: PASS.
7. Independence tests (NSS changes do not alter LRT below veto; LFS changes do not alter NMT below veto): PASS.
8. Candidate hypotheses/falsification and NOT_CALIBRATED: PASS.
9. All outputs non-actionable: PASS.
10. C++20 build and full CTest: PASS, 9/9.
11. Three JSON schemas: PASS.
12. Real BTC and ETH same-snapshot evaluation: PASS.
13. Telegram receipt: PASS, HTTP 200.

## Live evidence

GitHub Actions run: `44305974876`  
Branch: `feat/cpp-stage5-dual-engines-v1`  
L1 run ID: `okx-cpp-1795005637653`  
Decision timestamp: `1795003200000`  
L1 SHA-256: `155d1c41ea27f57c25d46f826275fa43917ea029d87df4c8882f9bc5714881e8`

LFS v2 and NSS v2 were computed from the exact same L1 snapshot and decision timestamp. Both were PROXY. Stage 4 liquidity/phase also used the same L1 hash.

| Symbol | LFS | NSS LONG | NSS SHORT | LRT | NMT | Golden Rule |
|---|---:|---:|---:|---|---|---|
| BTC/USDT:USDT | 0.388894 | 0.551490 | 0.463542 | NO_QUALIFIED_SETUP | NO_QUALIFIED_SETUP | NOT_TRIGGERED |
| ETH/USDT:USDT | 0.452596 | 0.486413 | 0.552000 | NO_QUALIFIED_SETUP | NO_QUALIFIED_SETUP | NOT_TRIGGERED |

Specific live diagnosis:
- LRT: `NO_CONFIRMED_LIQUIDITY_SWEEP_RECLAIM` on BTC and ETH.
- NMT: `NO_TREND_BREAKOUT_WITH_VOLUME` on BTC and ETH.
- Golden Rule was evaluated for both symbols and did not trigger.
- This is a valid no-setup outcome, not an engine failure. No thresholds were relaxed to force a candidate.

### Delivery and persistence

- Telegram HTTP 200, status DELIVERED, message_id 55.
- Receipt persisted at `signals/cpp_runtime/dual_engine_stage5_telegram_outbox.v1.json`.
- Separate LFS/NSS/Stage4 inputs and LRT/NMT candidate outputs persisted to the `signals` branch:
  - `lfs_stage5_v2.json`
  - `nss_stage5_v2.json`
  - `liquidity_stage5_v1.json`
  - `lrt_candidates_stage5_v1.json`
  - `nmt_candidates_stage5_v1.json`
  - `dual_engine_stage5_v1.json`
- No Actions artifact storage used.

## v2 / v3 decisions

- v1 passed; v2 and v3 were NOT BUILT under R11.
- v2 remains a distinct retest/volume-profile LRT and multi-timeframe continuation NMT hypothesis, only if a measured v1 FAIL occurs.
- v3 remains a simplified structural fallback, only if a measured v2 FAIL occurs.
- Maximum three versions; no parameter-only rewrites.

## Five-question self-critique

1. Future data used? No; shared snapshot, same timestamp/hash and causal tests passed.
2. Parameters tuned on test? No; gates were predeclared and no sweep was performed.
3. Costs included? No trade/EV is produced at this stage; cost-aware risk gates are later.
4. No-signal report? Yes; both symbols explicitly report NO_QUALIFIED_SETUP in Telegram.
5. Weakest assumption? LFS/NSS and Stage 4 phase are proxies; neither candidate engine is calibrated or proven profitable.

## SLRP result

```text
STAGE 5 — INDEPENDENT LRT / NMT ENGINES
├── Acceptance: same-snapshot inputs, separate engines/artifacts, strict Golden Rule, causal tests, schema, BTC+ETH and Telegram receipt
├── v1 → PASS → CTest 9/9; LRT/NMT independent; no candidate on live BTC/ETH; Golden Rule evaluated
├── v2 → NOT_BUILT → v1 passed (R11)
├── v3 → NOT_BUILT → v2 not required
├── Active: LRT_V1 + NMT_V1 (PROXY / NOT_CALIBRATED)
└── Handoff: Stage 6 — Meta-Cognition + Calibration
```
