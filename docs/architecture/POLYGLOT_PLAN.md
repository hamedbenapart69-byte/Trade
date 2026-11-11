# POLYGLOT PLAN — Trade System V1
**Status:** DESIGN ONLY — awaiting owner approval  
**Date:** 2026-11-11  
**Scope:** Go Data Collector (P1-A), Rust Core Kernel (P1-B), C++ Backtest Kernel (P2), Python orchestration/strategy, TypeScript delivery.

## 1. Executive decision

Python remains the reference implementation and the orchestration/strategy layer. New languages are isolated modules, introduced only when a measured bottleneck justifies them. No rewrite, production switch, or removal of Python code is authorized by this document.

The system remains zero-cost, web-first, read-only toward exchanges, and manual-trade-only. All collectors use public market data. No exchange trading credentials, order placement, paid runtime, or always-on paid service is introduced.

**Decision hierarchy:** correctness and data integrity > reproducibility > reliability > speed. A faster implementation that changes outputs, introduces leakage, or weakens provenance is rejected.

## 2. Target architecture

| Layer | Language | Bounded responsibility | Interface |
|---|---|---|---|
| L1 — Data Collection | Go | Concurrent public-provider collectors, provider cascade, symbol fan-out, retries, rate limits, normalization and provenance | gRPC + Protocol Buffers to Python orchestrator; Parquet/JSON artifacts at durable boundaries |
| L2 — Core Kernel | Rust | Deterministic LFS/NSS primitives, market-structure primitives, order-book transforms, selected Parquet processing | PyO3 Python extension; versioned schema at process/artifact boundaries |
| L2 — Backtest Kernel | C++ | Later-stage event/tick simulation, spread/slippage/funding/impact model and high-volume replay | pybind11 Python extension; versioned schema for persisted inputs/outputs |
| L2 — Strategy & Orchestration | Python | LRT/NMT, hypotheses, falsification, calibration, risk gates, path orchestration, experiment registry and reference calculations | Owns control flow; invokes language modules only through declared bindings |
| L3 — Delivery | TypeScript | Persian RTL web dashboard, public read-only API surface and Telegram notification integration | Versioned JSON contracts; trusted server-side notifier |
| Infrastructure | Bash/YAML + SQL | GitHub Actions CI/schedule, schemas/migrations, artifact and evidence handling | GitHub Actions and repository artifacts/branches |

No source-code sharing across languages. Shared contracts are schemas, not copied implementation code.

## 3. Interface and contract rules

### 3.1 Canonical contracts
- Protocol Buffers are the preferred Go-to-Python transport. The first deployment target is a local gRPC process pair inside the same GitHub Actions runner; no paid or always-on service is required.
- JSON Schema is used for web/API payloads and human-inspectable evidence artifacts.
- Every contract is versioned, has explicit units, timestamp timezone, symbol identity, source/provider, freshness, quality status and nullable/unavailable semantics.
- Schema changes are additive by default. Breaking changes require a version bump and compatibility tests.
- Every record carries provenance: provider, retrieval timestamp, source timestamp where available, timeframe, symbol, schema version, and REAL/PROXY/UNAVAILABLE classification.

### 3.2 Language bindings
- Rust: PyO3, built and packaged with maturin. Python remains the caller and fallback.
- C++: pybind11. ctypes is not the default because the typed C++ surface and ownership model are better represented through pybind11.
- Go: gRPC + Protocol Buffers, preferred over cgo to isolate runtimes and avoid embedding Go runtime behavior inside Python.
- TypeScript: JSON Schema contracts with Python-produced reports; no direct exchange trading integration.

### 3.3 Failure behavior
- Any unavailable module, schema mismatch, timeout, malformed response or failed equivalence check routes to the Python reference path or emits an explicit DEGRADED/UNAVAILABLE result.
- No silent fallback may relabel PROXY data as REAL.
- A module failure must not suppress the daily report guarantee. Delivery emits the correct degraded/no-qualified-setup state.

## 4. Admission gates for every new module

A new implementation is not accepted because it compiles or because one benchmark looks impressive.

1. **Independent tests:** language-native unit tests, boundary tests, malformed-input tests and deterministic fixtures.
2. **Equivalence:** same input corpus and same canonical output. The required comparison is byte-for-byte after canonical serialization. Floating-point operations must use a deterministic operation order and pinned numeric behavior. If exact equality cannot be achieved, the module does not pass; no tolerance may be silently substituted.
3. **Performance:** benchmark against the Python reference on the same runner class, same data, warm-up, repetitions and workload. Report median, p95, throughput, memory and CPU. Publish raw benchmark inputs/results and commit hashes.
4. **Minimum gain:** 5x is the pilot screening target stated for P1-A/P1-B. The general production admission rule remains **at least 10x** on the measured target workload. A 5x result may justify continued Shadow evaluation, not production replacement.
5. **Shadow:** at least 7 consecutive days, running beside Python without controlling production output. Compare every eligible result and record divergence.
6. **Reliability:** timeout, retry, cancellation, resource limits, crash isolation and fallback tests.
7. **V9.1 validation:** no look-ahead, leakage, survivorship bias, hidden parameter tuning, unaccounted costs, or missing evidence bundle. Tests that use mocks/fixtures do not prove live-provider behavior.
8. **Cost and feasibility:** zero-cost execution in the existing GitHub Actions budget; no paid compiler service, hosted gRPC service, or runtime dependency.
9. **Rollback:** Python reference remains deployable and is the immediate fallback. No destructive migration.

The 10x rule is the final acceptance threshold. The phase-specific 5x target is an early research threshold only. This resolves the two stated targets without weakening the production gate.

## 5. P1-A — Go parallel data collector

**Objective:** evaluate whether Go materially improves L1 collection for 40–100 symbols and multiple public providers.

**Scope:**
- Independent collector module; Python continues to own orchestration, provider selection policy and final data acceptance.
- Concurrent requests with bounded worker pools, per-provider rate limits, context cancellation, timeouts, exponential backoff with jitter and circuit-breaker state.
- Provider cascade is explicit and observable. A fallback must preserve provider identity and must not merge incompatible candles or silently substitute fields.
- Initial providers follow the current approved public-data cascade. Provider availability from Iran and endpoint-specific restrictions must be verified; no provider is assumed reachable.
- Output is normalized to the current Python ingestion contract and persisted as the same Parquet layout/metadata after equivalence.

**Benchmark protocol:**
- Same 40-symbol and 100-symbol fixture/live windows, same endpoints, same concurrency ceiling and same runner.
- Compare total wall-clock time, per-provider latency, throughput, p95, error rate, retry count, memory and CPU.
- Separate network wait from CPU time. A faster mock benchmark is not evidence of faster live collection.
- Pilot target: >=5x measured improvement on the bottleneck workload. Production gate: >=10x, 7-day Shadow, exact equivalence and all V9.1 reliability/data gates.

**Failure/rollback:** keep Python collector active; Go result remains diagnostic only. No Production collector switch in P1-A.

## 6. P1-B — Rust LFS/NSS kernel

**Objective:** port one bounded, deterministic Python primitive, initially LFS calculation, only after P1-A has been reviewed.

**Scope:**
- Python implementation is frozen as the reference for the selected version and fixture corpus.
- Inputs/outputs, weights, missing-value rules, clipping, precision, ordering and rounding are specified before implementation.
- Rust implementation uses PyO3/maturin and does not own strategy decisions or thresholds.
- NSS is not ported automatically with LFS. Each primitive receives its own benchmark, equivalence suite and Shadow evidence.

**Acceptance:**
- Exact canonical output equivalence across normal, boundary, missing, extreme and malformed inputs.
- Native Rust unit tests and Python binding integration tests.
- >=5x pilot benchmark; >=10x production gate.
- At least 7 days Shadow with zero unexplained divergence.
- Python reference remains available after acceptance.

## 7. P2 — C++ backtest and microstructure kernel

**Entry condition:** do not begin merely because C++ is on the roadmap. First profile the Python backtest and establish that it has reached a verified throughput ceiling. The proposed 500,000 simulated trades/minute figure is a profiling checkpoint, not an achieved metric or a guaranteed threshold; measure the actual workload and identify the bottleneck.

**Scope:**
- Event-driven/tick-by-tick replay only where source data supports that granularity. OHLCV bars must never be presented as tick data.
- Model fee, bid/ask spread, slippage, market impact, funding, latency assumptions and ambiguous intrabar ordering conservatively.
- C++ is a compute kernel only. Python retains experiment registry, strategy orchestration, reporting and gate decisions.
- pybind11 is the selected binding. No C++-owned strategy logic or hidden parameter search.

**Acceptance:**
- Independent C++ tests and Python binding tests.
- Exact equivalence on deterministic synthetic fixtures and historical replay corpus.
- >=10x production performance gain on the measured bottleneck.
- 7-day Shadow with no unexplained divergence.
- V9.1 walk-forward, untouched final holdout, costs, DSR/PBO and evidence-bundle requirements remain mandatory. Faster backtests do not increase statistical validity.

## 8. Benchmark and equivalence evidence format

Each experiment records:
- module/language/version and source commit SHA;
- Python reference commit SHA;
- runner OS/architecture/CPU/runtime/compiler versions;
- dataset identifier, immutable data hash, schema version and row/event count;
- exact benchmark command/configuration, warm-up and repetition count;
- median/p95 latency, throughput, memory, CPU and error rate;
- equivalence corpus hash, case count, byte-identical pass count and divergence samples;
- Shadow start/end, eligible observations, mismatches, fallbacks and uptime;
- decision: REJECTED / RESEARCH_ONLY / SHADOW_ONLY / ACCEPTED;
- reviewer and evidence artifact links.

No speedup claim is valid without a reproducible baseline and raw evidence. Network-bound collection benchmarks must report network and compute components separately.

## 9. V9.1 and existing system guardrails

- Each path remains independent: Plan A, B, C and H are not blended by language migration.
- Python reference and production decision rules remain authoritative until the module passes every gate.
- Final Holdout stays untouched. Development/Validation/Final Holdout separation and Trial Registry remain mandatory.
- Walk-forward: train 6 months / test 2 months / step 1 month, where the required history exists.
- Include fee, spread, slippage, funding and impact where applicable. Missing cost inputs are explicitly PROXY/UNAVAILABLE with stricter thresholds.
- Preserve G1–G8, C1–C18, SLRP v1/v2/v3, D1–D6 diagnosis and Innovation Protocol.
- No new language module may change thresholds, labels, signal frequency targets or trade gates.
- No exchange account credentials, private trading keys or order execution are permitted.

## 10. Staged roadmap and stop conditions

| Stage | Deliverable | Stop condition |
|---|---|---|
| P0 closure | Evidence, notifier, security status and deferred-risk register | P0 is PASS WITH DEFERRED ITEMS only; residual HIGH risks remain visible |
| P1-A | Go collector prototype, tests and benchmark report | <5x pilot gain, failed equivalence or unstable provider behavior => retain Python |
| P1-A Shadow | 7-day parallel comparison | Any unexplained divergence or data provenance loss => stop and diagnose |
| P1-B | Rust LFS prototype and binding | Any byte mismatch or <5x pilot gain => retain Python |
| P1-B Shadow | 7-day parallel comparison | Any unexplained divergence => stop |
| P2 | C++ backtest kernel after Python profiling gate | No demonstrated Python bottleneck or no >=10x gain => do not build/merge |
| Production admission | Full V9.1 evidence bundle and all relevant gates | Any missing proof => SHADOW_ONLY or RESEARCH_ONLY |

Each stage is reviewed independently. A PASS in one language does not authorize another language or another layer.

## 11. P0 residuals that affect the roadmap

The latest recorded state is **P0 operational PASS WITH DEFERRED ITEMS**, not security-complete:
- Admin Branch Protection write path: DEFERRED; Policy Guard is detective, not an equivalent preventive control.
- Cloudflare production environment configuration/deploy: DEFERRED; the previously exposed Cloudflare token must not be reused.
- Activepieces Published Dashboard Read API still reports authType=none; Draft Header Auth exists but is not published.
- Stage1B durable persistence remains deferred; artifacts are temporary evidence, not a durable dataset store.
- PR #85 proxy is not production-ready solely because its CI is green. Its current design relies on an Origin allowlist, which is not authentication by itself, and its workflow references a test file not present in the PR patch. These gaps must be resolved before merge/deploy.
- Telegram report delivery has one verified successful end-to-end instance (message_id=656). This proves delivery, not calibrated trading edge.

P0 must not be described as fully secure until the Published webhook is protected and the dashboard's actual access path is tested. DEFERRED is an explicit status, not a pass for the underlying security control.

## 12. Decision requested

This document is architecture only. No Go, Rust or C++ implementation is included or authorized here. After owner approval of this plan, P1-A may begin in a development branch with Go collector prototype, isolated tests and benchmark only. It must not replace Python or affect Production before all admission gates pass.
