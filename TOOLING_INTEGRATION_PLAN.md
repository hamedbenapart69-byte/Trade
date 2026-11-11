# Tooling Integration Plan — V1

**Status:** PROPOSAL ONLY — NO TOOL INTEGRATION AUTHORIZED  
**Review date:** 2026-11-11  
**Target repository:** `hamedbenapart69-byte/Trade`  
**Related operations track:** security baseline and remediation in `Support-trade`  
**Owner constraint:** zero-cost, web-first, read-only market data, manual trade only.

> This document evaluates the proposed tools against the repository as it exists on `main`. It does not install dependencies, add runtime services, alter schedules, change production, or enable any external side effect. A separate explicit approval is required before implementation.

## 1. Executive decision

Do not add all 15 tools. The list contains useful candidates, but several are not truly zero-cost for this use case, several duplicate capabilities already present, and several introduce persistent infrastructure that the current project does not have.

Recommended direction:

1. **Keep GitHub Actions as the primary scheduler and CI runner** for the current bounded scans and validation jobs.
2. **Pilot Great Expectations (GX Core) as an additive data-quality layer**, only after mapping the existing validators and proving the new suite catches defects the current tests miss. It is not a deduplication engine and must not replace deterministic cleaning code.
3. **Benchmark Jesse and NautilusTrader side-by-side as isolated research candidates** only after a reproducible historical dataset and a current baseline simulator are identified. Do not replace any engine based on a marketing claim or a single backtest.
4. **Do not introduce Feast yet.** Current evidence does not establish a multi-model feature-serving requirement that justifies a feature-store service and its operational dependencies.
5. **Do not migrate to Windmill, Prefect, or Temporal now.** The repository already has GitHub Actions, a FastAPI control plane, SQLite persistence, an approval ledger, a durable outbox, a one-shot allowlisted worker, and a guarded n8n adapter. Add one orchestrator only if a measured workflow gap remains.
6. **Prefer Langfuse over AgentOps only if AI/agent traces become a real, approved runtime requirement.** Start with metadata-only traces and strict redaction. Do not send API keys, Telegram identifiers, private prompts, or raw sensitive payloads.
7. **Exclude Cloud Run from the zero-cost baseline.** Its free tier is a usage allowance under a required billing account, not a hard spending cap. Iran access/payment feasibility is unverified.
8. **Reject CoinGlass API and Tardis.dev for the current zero-cost architecture.** Treat them as paid research vendors, not free dependencies.
9. **Do not depend on CodeRabbit's public-repository free offer** for a project whose security objective is to make the code private. Snyk may be an optional bounded scanner, but native CI security checks should remain the baseline.

### Decision summary

| Tool | Decision | Proposed role | Gate |
|---|---|---|---|
| NautilusTrader | CONDITIONAL EVALUATION | Independent event-driven simulation benchmark | Only after a reproducible baseline and dataset exist |
| Jesse | CONDITIONAL EVALUATION | Crypto-strategy/backtest comparison candidate | Same data, rules, costs and OOS splits as Nautilus |
| Great Expectations GX Core | RECOMMENDED PILOT | Additive 15m data-quality suite | Prove value over current validators; fail closed |
| Feast | DEFER | Point-in-time feature registry/store | Only when multiple consumers require shared versioned features |
| Prefect OSS | DEFER / ALTERNATIVE | Python DAG orchestration | Only if GitHub Actions + current control plane cannot meet a measured need |
| Windmill OSS | DEFER / ALTERNATIVE | Code-centric workflows/internal apps | Do not run beside Prefect; requires persistent self-hosted infrastructure |
| Temporal OSS | DEFER | Durable long-running workflow execution | Only if current outbox/worker cannot satisfy a proven durability requirement |
| Langfuse | OPTIONAL, PREFERRED OBSERVABILITY CANDIDATE | AI/agent traces and evaluations | Only for an approved AI runtime; redact and budget events |
| AgentOps | OPTIONAL ALTERNATIVE | Agent run/event telemetry | Do not run alongside Langfuse without a distinct need |
| Snyk | OPTIONAL BOUNDED SECURITY SCAN | Dependency/code/IaC/container scanning | Free quota and private-repo account eligibility must be checked |
| CodeRabbit | NOT BASELINE | PR review assistant | Free forever is for public repositories; unsuitable as a guaranteed private-repo tool |
| Google Cloud Run | REJECT FOR ZERO-COST BASELINE | Possible container host only with explicit cost approval | Billing account required; overages billable; Iran/payment not verified |
| Val Town | REJECT FOR CORE PIPELINE | Small public cron tasks only | Free tier has 15-minute minimum cron, 1-minute runtime, and no private vals |
| CoinGlass API | REJECT | Paid derivatives data source | Official API documentation says there is no free API plan |
| Tardis.dev | REJECT | Paid high-frequency historical data | Paid subscriptions; not compatible with zero-cost requirement |

## 2. Repository facts used for this assessment

Observed from the accessible `main` branch on 2026-11-11:

- Root control plane: `app/main.py`, `app/store.py`, `app/workflow_schemas.py`, `app/signals.py`, `worker.py`.
- The control plane uses FastAPI, SQLite, idempotency keys, audit events, a durable outbox, bounded leases, explicit reconciliation for unknown outcomes, separate operator/worker credentials, and a one-shot worker with a workflow allowlist.
- The root `requirements.txt` is currently small: FastAPI, Uvicorn and HTTPX. `compose.yaml` runs the control-plane container and a named SQLite volume; it does not currently host Windmill, Prefect, Temporal, Feast or Langfuse.
- The repository contains a guarded n8n adapter, but the README states that no live n8n instance/webhook has been configured. No Activepieces integration is visible in the current repository tree; any external Activepieces flow must be audited separately before claiming a migration target exists.
- Cloudflare Pages build/preview workflows exist, but no Cloudflare Workers application or Worker deployment source was found in the current main tree. Cloud Run is therefore not a direct replacement for a currently implemented Worker service.
- The scanner is under `signal_autopilot/`, with separate dependencies including CCXT, HTTPX, PyArrow, python-telegram-bot, Matplotlib and websockets.
- The V5 scanner is documented as read-only, using public market data, and does not place orders or connect to trading accounts. Current documented live data paths include public CoinGecko discovery and public exchange market data. No private exchange credentials or order endpoints are part of the intended system.
- The historical 1h signal engine is marked research-only/quarantined in code. The V5 design document explicitly says a verified historical backtest/performance sample is not yet established.
- The V5-specific workflow file on `main` is manual-dispatch-only, while other scheduled workflows exist in the repository. The README and workflow files therefore need a schedule-ownership reconciliation before any scheduler migration.
- CI currently runs root tests, scanner tests, a fail-closed legacy-engine smoke test, JavaScript syntax validation, Compose validation, Docker build and a container health smoke test.

**Important correction:** The current `main` branch does not establish that an active production backtest engine with a measured 100% drawdown exists. That claim must be tied to a specific engine, commit, dataset, configuration and report before any replacement decision. The V5 documentation instead records the historical backtest as unverified. NautilusTrader/Jesse are therefore benchmark candidates, not approved replacements.

## 3. Tool-by-tool assessment

### 3.1 NautilusTrader

- **License:** LGPL-3.0 (not merely an unspecified “LGPL”).
- **Fit:** Strong candidate for deterministic event-driven simulation, venue-aware execution modelling and replay-oriented research.
- **Integration concept:** Keep it in an isolated research package, for example `research/backtest/nautilus/`, with adapters that consume immutable, normalized market-data snapshots. It must not be imported by the live signal publisher in the first evaluation.
- **Risks:** Native/Rust-oriented build and dependency footprint; exchange-specific instrument and fill semantics must be modelled; migration can create false confidence if the simulator does not reproduce the existing strategy's actual assumptions.
- **Runtime/maintenance:** High relative to the current lightweight Python pipeline. CI build time and memory use need measurement.
- **Decision:** Conditional benchmark only. No replacement until parity tests and OOS validation pass.

### 3.2 Jesse

- **License:** MIT.
- **Fit:** Python-native crypto strategy research and backtesting; likely lower integration friction for existing Python strategy code than a Rust-native engine.
- **Integration concept:** Isolated benchmark adapter under `research/backtest/jesse/`. Reuse the same normalized OHLCV and cost assumptions as the Nautilus benchmark.
- **Risks:** Framework conventions may differ from the current strategy semantics; funding, contract sizing, stop/target ordering, partial fills, slippage and venue-specific constraints must be explicitly reconciled.
- **Runtime/maintenance:** Medium. Additional framework dependencies and version pinning required.
- **Decision:** Conditional benchmark, not a live execution system and not an automatic winner over Nautilus.

### 3.3 Great Expectations (GX Core)

- **License/cost:** Official GX Core materials state Apache-2.0 and free open-source core.
- **Fit:** Add a declarative quality layer around the current numerical validators.
- **Integration concept:** `signal_autopilot/quality/` with a 15m suite and CI invocation before any future historical simulation. Keep existing parser, deduplication and normalization functions as deterministic transformations.
- **Candidate expectations:** symbol/timeframe identity; UTC timestamp type; strictly increasing timestamps per symbol; unique (symbol, timeframe, open_time); exact 900,000 ms spacing where a candle is expected; OHLC invariants; finite positive prices; non-negative volume; completed candles only; freshness; source/provider metadata; and bounded coverage/gap rates.
- **Important nuance:** “No gaps anywhere” is not a universally valid rule. Listings, delistings, halts, venue maintenance and intentionally truncated windows can create legitimate gaps. Define the expected trading window and per-symbol coverage policy; classify exceptions rather than silently filling candles.
- **Risks:** GX adds dependency and configuration complexity. A passing expectation suite does not prove data truth or correct exchange semantics.
- **Runtime/maintenance:** Low-to-medium if used only as a CI/offline validation layer.
- **Decision:** First implementation candidate after this plan is approved, provided a baseline comparison shows it adds useful coverage.

### 3.4 Feast

- **License:** Apache-2.0.
- **Fit:** Point-in-time feature retrieval and feature registry for multiple training/serving consumers.
- **Integration concept:** If approved later, register immutable feature definitions with event timestamps, source timestamps, entity keys, schema versions and strategy versions. Keep raw market data as the source of truth; Feast is a feature access layer, not a raw-data archive.
- **Risks:** Feast does not automatically prevent leakage. Correct event-time semantics, point-in-time joins, offline/online store configuration and backfill discipline are still required. The current project has not demonstrated multiple independent consumers needing a shared feature store.
- **Runtime/maintenance:** High for a single-operator pipeline; offline store, registry and optional online store add operational pieces.
- **Decision:** Defer until at least two independent engines/consumers need shared, versioned, time-aware features.

### 3.5 Windmill

- **License/cost:** Open-source self-hosted Community edition is listed as free; its source is AGPLv3. The free tier has meaningful feature limits, including no audit logs and no OpenTelemetry tracing/logging in the published comparison.
- **Fit:** Code-centric scripts, flows and internal applications.
- **Integration concept:** Potentially replace selected orchestration tasks, not the signal engine or policy ledger. FastAPI remains the owner-controlled approval and audit boundary.
- **Risks:** AGPL obligations require review; self-hosting requires persistent infrastructure and database/worker operations. Free self-hosting does not make the server, disk, backups and maintenance free.
- **Runtime/maintenance:** High. It would overlap with the existing control plane and GitHub Actions unless a concrete workflow need is identified.
- **Decision:** Defer. If later selected, compare it against Prefect and choose one, never deploy both by default.

### 3.6 Prefect

- **License:** Prefect repository currently identifies Apache-2.0.
- **Fit:** Python-first flow/DAG orchestration, retries, schedules and task-level observability.
- **Integration concept:** Candidate for complex Python dependency graphs that exceed GitHub Actions' practical limits. Keep policy approval, audit ledger and external side-effect gates in the existing FastAPI control plane.
- **Risks:** A self-hosted server/worker introduces another always-on service, database/state, upgrades, auth and backup responsibilities. Prefect Cloud free-plan quotas are not assumed to be permanent or suitable.
- **Runtime/maintenance:** Medium-to-high depending on deployment mode.
- **Decision:** Defer. GitHub Actions remains the default while the number and complexity of workflows remain manageable.

### 3.7 Temporal

- **License:** MIT for the Temporal server repository.
- **Fit:** Durable, long-running workflows with retries and recovery semantics.
- **Integration concept:** Only for a demonstrated workflow that cannot be safely represented by the current transactional outbox and explicit unknown-outcome reconciliation.
- **Risks:** A Temporal cluster/service and persistence layer add significant operational complexity. Automatic retries are not safe for external side effects unless idempotency and reconciliation are designed per activity.
- **Runtime/maintenance:** Very high compared with current single-operator deployment.
- **Decision:** Defer as a contingency, not a planned immediate dependency.

### 3.8 Langfuse

- **License/cost:** Open-source self-hosting is available; official pricing currently lists Hobby at 50,000 units/month, 30 days of data access and two users, with no credit card required.
- **Fit:** Trace approved AI/agent interactions, tool calls and evaluation results.
- **Integration concept:** If an AI agent runtime is introduced, emit structured trace metadata from a dedicated adapter. Log run IDs, tool names, latency, status, model/version and redacted evaluation scores. Never emit credentials, chat identifiers, raw private data or full market payloads by default.
- **Risks:** Cloud telemetry sends data to a third party and the Hobby plan has limited retention/access. Self-hosting has a nontrivial storage and service footprint. Langfuse records what the agent did; it does not prove the agent's decisions were correct.
- **Runtime/maintenance:** Medium for cloud; high for self-hosted.
- **Decision:** Preferred observability candidate only if an approved AI/agent runtime is actually added. No telemetry SDK in the signal scanner at this stage.

### 3.9 AgentOps

- **License/cost:** AgentOps publishes an MIT-licensed SDK/application repository and a hosted Basic tier currently advertised as free up to 5,000 events.
- **Fit:** Agent session and tool-event observability.
- **Integration concept:** Alternative to Langfuse for the same narrowly scoped AI observability requirement.
- **Risks:** Event cap and retention/hosting terms need periodic verification; hosted telemetry has the same privacy boundary as any third-party trace service. Self-host entitlement and deployment requirements are not assumed from the SDK license.
- **Runtime/maintenance:** Medium if hosted; higher if self-managed.
- **Decision:** Alternative only. Do not add AgentOps and Langfuse together without evidence of non-overlapping needs.

### 3.10 Snyk

- **Cost:** Official Free plan is currently $0 with bounded project and test allowances; the published page lists five projects and separate monthly test limits across products.
- **Fit:** Optional SCA/SAST/IaC/container scanning.
- **Integration concept:** A non-blocking trial on a limited repository set, followed by a decision on whether it provides coverage beyond native tools.
- **Risks:** Free quotas can be exhausted; account and private-repository eligibility need verification. It is a hosted third-party scanner, so repository permissions and data handling must be reviewed.
- **Runtime/maintenance:** Low-to-medium; CI integration and quota monitoring required.
- **Decision:** Optional. Native dependency auditing, secret scanning and container checks remain mandatory baseline controls regardless of Snyk.

### 3.11 CodeRabbit

- **Cost/eligibility:** Current official pricing describes free reviews for public repositories; paid plans apply to private-repository usage. Current paid plan hourly limits differ from the old “three reviews/hour” claim.
- **Fit:** AI-assisted PR review.
- **Risks:** The project's target is private source code. Relying on a public-repository free offer conflicts with that security goal. AI review is not a substitute for tests, threat modelling or human approval.
- **Decision:** Exclude from the zero-cost/private baseline.

### 3.12 Google Cloud Run

- **Cost:** Current request-based free tier includes up to 2 million requests/month, 180,000 vCPU-seconds and 360,000 GiB-seconds at the documented Tier 1 baseline. Usage above allowances is billable and region/billing configuration affects cost.
- **Critical constraint:** Google requires an active Cloud Billing account even to use services covered by the Free Tier. A free allowance is not a hard spending cap.
- **Fit:** Container hosting for APIs/jobs if a paid-capable billing account and operational access are available.
- **Risks:** Unexpected overage charges, account/payment verification, regional differences and unverified usability from Iran. It is not a drop-in replacement for Cloudflare Workers; it is a container runtime with a different operating model.
- **Decision:** Reject for the strict zero-cost baseline. Reconsider only after explicit owner approval of billing exposure and a real connectivity/account test.

### 3.13 Val Town

- **Cost/limits:** Official Free plan currently lists 15-minute minimum cron intervals, one-minute maximum wall-clock runtime, three-day log retention and zero private vals.
- **Fit:** Small public scheduled scripts.
- **Risks:** Private signal workflows and secret-bearing automation are not suitable for a free tier with no private vals; one-minute runtime is too restrictive for market-wide scans.
- **Decision:** Reject for core pipeline. Do not place private logic or secrets in public vals.

### 3.14 CoinGlass API

- **Cost:** Current official API documentation says there is no free API version and requires a subscription. The official pricing page and API documentation currently show different Hobbyist monthly figures ($29 vs $35); the exact current checkout price therefore needs confirmation if ever reconsidered.
- **Fit:** Aggregated derivatives, CVD, liquidation and order-flow data.
- **Risks:** Direct conflict with zero-cost. Hobbyist/Startup usage is personal-only according to current plan documentation; commercial use requires a higher plan. Data granularity/history also varies by plan.
- **Decision:** Reject from the current architecture. Use only after a separate paid-data approval, never as a silent dependency.

### 3.15 Tardis.dev

- **Cost:** Current official pricing lists paid subscriptions. Pricing varies by data scope and plan; the site currently lists Academic, Solo, Professional and Business plans, with paid monthly/quarterly/yearly access.
- **Fit:** High-frequency historical tick/order-book replay and granular market data.
- **Risks:** Far outside zero-cost; API access and historical depth are subscription-dependent.
- **Decision:** Reject. Keep as a future external research vendor only if the owner explicitly changes the zero-cost constraint.

## 4. Migration map

| Capability | Current implementation | Candidate | Phase | Migration rule |
|---|---|---|---|---|
| Scheduling/CI | GitHub Actions workflows | Keep GitHub Actions | P0/current | Audit trigger ownership and permissions before changing anything |
| Approval/audit/outbox | FastAPI + SQLite + one-shot worker | Keep current control plane | P0/current | No orchestrator may bypass approval, allowlists or reconciliation |
| 15m data validation | Existing Python validators/tests in scanner | GX Core additive suite | P0 pilot after approval | Compare against current checks; no silent replacement or data imputation |
| Historical simulation | No verified current OOS performance baseline established in main | Jesse vs Nautilus | P1 research | Same immutable data, strategy rules, costs, fills and walk-forward windows |
| Feature definitions | Python calculations in signal pipeline | Feast | P2 only | Introduce only for multiple shared consumers and point-in-time retrieval |
| Complex Python orchestration | GitHub Actions + FastAPI worker/outbox | Prefect OR Windmill | P2 only | Select one after measured orchestration gap; do not dual-run by default |
| Durable long-running tasks | SQLite outbox and bounded worker leases | Temporal | P3 contingency | Only if existing recovery model fails a documented requirement |
| AI/agent tracing | No verified production agent runtime in current signal pipeline | Langfuse OR AgentOps | P2 conditional | Metadata-only, redacted, bounded retention and event budget |
| Security scanning | Existing CI and Support-trade secret-pattern checks | Native scanners + optional Snyk | P0 security track | Keep secret scanning independent of third-party quota |
| Hosting | GitHub Actions/Pages and existing Railway preview | Keep current until secure hosting decision | P0 security track | Cloud Run is not accepted as a zero-cost replacement |

## 5. Three-layer integration contract

Every adopted tool must contribute to a complete stage, not a data-only addition:

- **L1 Data:** source identity, timestamps, schema/version, provenance, immutable snapshot/checksum and explicit REAL/PROXY/UNAVAILABLE labels.
- **L2 Compute:** deterministic validation, feature calculation or simulation with frozen configuration, bounded resources and reproducible run IDs.
- **L3 Delivery:** inspectable report/artifact with PASS/FAIL, diagnostics, data coverage, assumptions and links to the exact source/run. Telegram remains reserved for actual signal notifications, not routine tool telemetry.

A tool that only adds data or a dashboard without connecting to the other required layers is not an accepted integration.

## 6. Proposed implementation stages and gates

### P0 — Baseline, audit and GX pilot design

**Objective:** Establish the exact current validators, data contracts, workflow triggers, data formats and historical data availability before adding dependencies.

Acceptance:
- Inventory all 15m candle producers/consumers and their timestamp semantics.
- Map existing duplicate, gap, OHLC, volume, freshness and completed-candle checks to a single test matrix.
- Identify the canonical historical dataset, its source, symbol coverage, period, timezone and immutable checksum.
- Demonstrate that GX catches at least one deliberately injected defect not already caught by the existing tests, without false-failing documented valid exceptions.
- No live pipeline, scheduler, delivery or production behavior changes.

### P1 — Backtest engine benchmark

**Objective:** Compare Jesse and Nautilus as research simulators without changing live signal production.

Acceptance:
- One immutable dataset and checksum for both engines.
- Same strategy specification and frozen parameters.
- Same timestamp/closed-candle rules, fees, slippage, funding, contract multiplier, tick/lot rules and stop/target ordering assumptions.
- Walk-forward splits are identical and strictly out-of-sample.
- Compare runtime, memory, trade count, fill/SL/TP event parity, equity curve, MaxDD, PF, Sharpe and rejected/unknown events.
- Any missing cost or execution assumption is labelled UNAVAILABLE, not set to zero.
- No winner selected solely on headline returns.

### P2 — Feature store and orchestration decision

**Objective:** Add no new always-on service unless multiple paths require it.

Acceptance:
- Written evidence that at least two independent consumers need shared point-in-time features before Feast is considered.
- Written evidence that current Actions/outbox cannot meet a specific DAG, retry, scheduling or observability requirement before Prefect/Windmill is considered.
- Only one orchestration candidate is prototyped at a time.
- Existing approval, audit, idempotency and fail-closed behavior remain mandatory.

### P3 — Agent observability

**Objective:** Add traceability only if an AI/agent runtime is actually approved.

Acceptance:
- Data classification and redaction tests.
- No tokens, API keys, chat IDs, private prompts or raw sensitive market payloads in traces.
- Event cap, retention and export policy documented.
- Langfuse and AgentOps compared on the same synthetic workload; choose at most one.
- A trace records an action; it does not certify decision correctness.

## 7. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dependency bloat and CI slowdown | High if all tools are added | High | One candidate at a time; benchmark cold install/runtime/memory |
| Conflicting scheduler ownership | Medium | High | Inventory all cron triggers; one source of truth per job |
| Orchestrator bypasses approval gate | Medium | Critical | FastAPI control plane remains policy boundary; no direct side effects |
| Backtest engine gives false confidence | High | Critical | Identical data/costs/rules; OOS-only validation; event-level parity |
| Data quality false positives | Medium | High | Symbol-specific expected windows and explicit gap exceptions |
| Feature leakage despite Feast | Medium | Critical | Event-time/availability-time discipline and point-in-time join tests |
| Third-party telemetry leaks private data | Medium | High | Redaction, minimal metadata, no credentials/raw payloads |
| Free-tier limits change or are exceeded | High over time | High | Prefer self-hosted OSS only when infrastructure is genuinely free; quotas and alerts |
| Cloud billing surprise | Medium | High | Cloud Run excluded unless explicit billing approval and budget controls |
| Iran network/payment restrictions | Unknown | High | Test actual account/network feasibility before adoption; no bypass assumptions |
| AGPL obligations overlooked | Low-to-medium | Medium | License review before adopting Windmill |
| Private repo becomes ineligible for a free review plan | High for CodeRabbit | Medium | Exclude CodeRabbit from baseline |

## 8. Development environment proposal — not yet created

The suggested `docker-compose.tools.yml` must not be created in this proposal stage.

Reason:
- The user requires web-first, mobile-friendly operation and zero recurring infrastructure cost.
- The current repository's Compose stack only runs the control plane locally and binds to loopback.
- Windmill, Prefect, Temporal, Feast and Langfuse self-hosting would require persistent compute/storage and additional operational ownership.
- A Docker Compose file is configuration, not free hosting. It does not provide an always-on server.
- Running all proposed services together would create a large and unnecessary development footprint.

If approved later, create a **separate optional development profile** for one selected tool only. Never auto-start it in production or CI. Keep all secrets in environment variables/secret stores and use synthetic data.

## 9. Google Cloud Run manifest decision

Do not create `infra/cloudrun-service.yaml` in V1. The service is not approved for the strict zero-cost baseline because a Cloud Billing account is required even within the free tier and overages are billable. If the owner later explicitly approves billing exposure and proves account/network feasibility, a deployment manifest can be authored as a separate proposal.

## 10. Security and operational constraints

- No trading-account connections, exchange private API keys, order endpoints or order execution.
- No paid provider or paid plan without explicit owner approval.
- No GitHub token or provider credential in browser JavaScript, repository files, test fixtures, trace events or logs.
- No new workflow may receive write permissions unless that exact job requires it.
- No PR-triggered untrusted code may receive secrets.
- Every tool adapter must have timeouts, bounded retries, idempotency, rate limits and a fail-closed degraded state.
- Preserve raw market data and evidence; never silently overwrite or deduplicate away source discrepancies.
- Production and live Telegram destinations remain untouched during evaluation.
- A tool's open-source license does not make its hosting, storage, network, backup and maintenance free.
- Global availability does not prove usability from Iran; account eligibility, geo-blocks, payment and real network access must be verified separately.

## 11. SLRP for this tooling track

**Objective:** Select only tools that improve validated system quality without violating zero-cost, privacy or reliability constraints.

**Acceptance criteria:**
- No production behavior changes in the proposal stage.
- Every candidate has a documented license, cost boundary, integration surface, maintenance burden and risk.
- At most one tool is piloted per capability category.
- No paid service is introduced.
- No performance or reliability improvement is claimed without a reproducible benchmark.

**v1:** Documentation-only assessment against the current repository and official vendor materials.

**Diagnosis:** If a candidate's value cannot be shown from current repository gaps, defer it rather than adding it.

**v2:** Only after an observed failure of v1, revise the tool selection or scope based on evidence.

**v3:** Only after v2 fails, test a materially different architecture. Maximum three versions.

**Escalation:** If no zero-cost, Iran-usable, maintainable solution satisfies the acceptance criteria, keep the current architecture and mark the capability UNAVAILABLE rather than silently introducing paid infrastructure.

**Budget:** Zero. No cloud resource, subscription, paid API, credit-based execution or external side effect is authorized by this plan.

## 12. Approval boundary

This PR contains documentation only.

Approval of this document may authorize a separate P0 implementation proposal for the GX pilot and benchmark harness design. It does **not** authorize:
- installing any package;
- adding `docker-compose.tools.yml`;
- adding `infra/cloudrun-service.yaml`;
- deploying Windmill, Prefect, Temporal, Feast, Langfuse or AgentOps;
- changing GitHub Actions schedules or permissions;
- changing Cloudflare, Railway or Telegram;
- changing repository visibility;
- enabling any live or production integration.

## 13. Official references checked on 2026-11-11

- NautilusTrader license: https://github.com/nautechsystems/nautilus_trader and https://nautilustrader.io/legal/open-source-licensing/
- Jesse repository/license: https://github.com/jesse-ai/jesse
- GX Core license and product: https://greatexpectations.io/
- Feast repository/license: https://github.com/feast-dev/feast
- Windmill pricing/self-hosted feature limits: https://www.windmill.dev/pricing
- Prefect repository/license: https://github.com/PrefectHQ/prefect
- Temporal server repository/license: https://github.com/temporalio/temporal
- Langfuse pricing/self-hosting: https://langfuse.com/pricing
- AgentOps SDK and pricing: https://github.com/AgentOps-AI/agentops and https://www.agentops.ai/
- Snyk Free plan: https://snyk.io/plans/
- CodeRabbit pricing and public-repository free offer: https://www.coderabbit.ai/pricing
- Google Cloud Run pricing: https://cloud.google.com/run/pricing
- Google Cloud Billing requirement: https://docs.cloud.google.com/billing/docs
- Val Town pricing and limits: https://www.val.town/pricing and https://www.val.town/limits
- CoinGlass API plans and permissions: https://docs.coinglass.com/reference/plans-and-permissions
- Tardis.dev pricing: https://tardis.dev/

**Final status:** V1 proposal drafted for owner review. No integration code or production change is included.
