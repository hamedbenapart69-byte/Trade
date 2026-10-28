# Architecture decision report

## Recommendation

Use n8n for deterministic integration workflows, LangGraph only for stateful multi-step reasoning, PostgreSQL when multi-worker durability is introduced, and Playwright only when no suitable authorized API exists. Keep a small owner-controlled API/UI and provider-neutral adapters.

## Preliminary weighted decision matrix

Criteria: workflow capability 25%, agent orchestration 20%, cost/quota resilience 20%, portability 15%, security/reliability 15%, operational simplicity 5%. Scores are engineering judgment, not benchmark results.

| Option | Score / 100 | Notes |
|---|---:|---|
| n8n + LangGraph + PostgreSQL | 88 | Good division between deterministic workflow and agent state |
| Activepieces + LangGraph | 85 | Alternative workflow engine; check edition/license requirements |
| Windmill + PostgreSQL | 83 | Strong developer workflow; higher operations complexity |
| Custom FastAPI + LangGraph + Playwright | 80 | Maximum control; greater maintenance burden |
| Cloudflare Workers + Queues + D1 | 76 | Managed option; vendor-specific runtime and quotas |

## Decision caveats

These scores are not measured benchmarks. Before selecting a hosting target, verify current regional reachability, actual price/quotas, license fit, backups, and availability from the user's network. Do not assume any provider is accessible from Iran based on marketing pages alone.
