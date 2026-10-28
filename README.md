# AI Orchestration Foundation

Portable, security-conscious foundation for a user-controlled AI automation platform.

## Status

This repository is selected as the home for the orchestration project. The local foundation includes a FastAPI + SQLite control plane, approval-gated run records, audit events, idempotency handling, backup tooling, and a Docker Compose definition.

This is not yet a production deployment. Real workflow/model integrations, a persistent worker queue, internet-facing authentication hardening, and deployment verification remain outstanding.

## Principles

- Explicit approval before external actions
- No secrets committed to source control
- Portable architecture and replaceable providers
- Tests before integrations are enabled
- No deployment or CI claims without evidence

## Security

Do not expose the API publicly without a proper identity layer, TLS termination, secret management, rate limits, and monitoring. Keep external workflow execution disabled until explicitly configured and tested.
