# Architecture decision report

Research snapshot: 29 October 2026. Re-check prices, licenses, and service terms before choosing a hosted plan. Public product pages do not establish reachability from the user's network.

## Five strongest candidates

| Option | Best fit | Cost / license facts verified from official sources | Main trade-off |
|---|---|---|---|
| n8n Community + custom control plane + optional LangGraph | Broad integrations and deterministic workflows; agent reasoning remains a separate optional layer | Self-hosted Community edition is free under the Sustainable Use License for internal use; SaaS plans are paid. Commercial use restrictions matter if customers configure automations or the platform is resold. [License FAQ](https://support.n8n.io/article/can-i-use-your-license-for-your-use-case), [pricing](https://n8n.io/pricing/) | Best first workflow engine candidate, but licensing boundaries must be reviewed for any future multi-user/SaaS model. |
| Activepieces + custom control plane | Open-source-first integration alternative | Core is MIT; enterprise/cloud features use a commercial license. Self-host guide recommends Docker Compose with PostgreSQL and Redis. [License](https://github.com/activepieces/activepieces/blob/main/docs/about/license.mdx), [install options](https://www.activepieces.com/docs/install/overview) | Check the exact feature/edition boundary and runtime footprint before migration. |
| Windmill + PostgreSQL | Code-centric scripts, flows, internal apps | Community edition is AGPLv3; official pricing lists self-hosted free/open-source with unlimited executions, while advanced audit/SSO/observability features are paid. [Self-host](https://www.windmill.dev/platform/self-host), [pricing](https://www.windmill.dev/pricing) | Strong for developer-owned workflows; AGPL and more involved server/worker/Postgres setup. |
| Custom FastAPI + durable DB/queue + Playwright only when needed | Maximum portability and control over approvals, schemas, policy and UI | No workflow-engine license fee; infrastructure and maintenance remain real costs. Playwright is an automation library, not a complete workflow product. | More engineering burden; useful as the owner-controlled control plane, not a reason to recreate every connector. |
| Cloudflare Workers + Queues + D1 + hosted model APIs | Managed event-driven workloads with low idle server overhead | Metered platform quotas/pricing and provider-specific limits apply; no assumption of unlimited free use. Official pricing: https://developers.cloudflare.com/workers/platform/pricing/ | Less operational maintenance but more vendor coupling and regional/provider suitability must be tested. |

## Preliminary weighted comparison

Weights: integration/workflow coverage 25%, stateful agent support 20%, cost/quota resilience 20%, portability 15%, reliability/security 15%, operating simplicity 5%. Scores are engineering judgment, not measured benchmarks.

| Candidate combination | Score / 100 | Decision |
|---|---:|---|
| n8n + owner-controlled FastAPI + optional LangGraph + PostgreSQL when needed | 88 | Preferred target, subject to license and real integration tests |
| Activepieces + FastAPI + optional LangGraph | 85 | Main fallback if n8n license/feature boundaries become unsuitable |
| Windmill + PostgreSQL + FastAPI policy layer | 83 | Strong code-centric alternative |
| Custom FastAPI + PostgreSQL/queue + Playwright selectively | 80 | Most portable, highest maintenance |
| Cloudflare Workers + Queues + D1 + external model provider | 76 | Reconsider if managed runtime materially improves actual access and cost |

## Recommended architecture

Keep the owner-controlled Trade repository as the policy and execution ledger. Use deterministic workflows for predictable operations; add LangGraph only for tasks that need durable multi-step reasoning. Use API/MCP connectors before browser automation. Keep provider adapters replaceable and outbound side effects approval-gated. Start with SQLite for a single local operator; migrate to PostgreSQL only when multi-worker concurrency, operational access or recovery requirements justify it.

## Minimum useful release and current status

Implemented in repository: authenticated API routes, approval ledger/audit trail, SQLite persistence, idempotency, durable outbox, unknown-outcome reconciliation, distinct operator/worker tokens, opt-in one-shot worker, allowlisted workflow names, local mobile-first web console, backup helper, unit/API tests, container build and CI health smoke test.

Not yet verified: deployment, actual n8n instance/webhook, model provider, browser automation, external identity provider, real-device/network access, production restore drill, cost/quota telemetry. No live external side effect has been enabled or claimed.

## Next engineering gates

1. Verify local real-HTTP integration behavior and regression suite.
2. Add per-workflow input/output schemas and payload limits.
3. Test restore into a clean database and document the restore drill.
4. Add bounded structured metrics and secret redaction.
5. Test isolated authorized n8n receiver before enabling outbound dispatch.
6. Select hosting only after credentials, auth model, persistent storage, TLS, backup and actual network access are verified.
