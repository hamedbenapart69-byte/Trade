# ADR-003 — Deterministic Replay and Immutable Artifacts

**Status:** PROPOSED — implementation is incremental  
**Scope:** L2 artifact identity, reproducibility, audit and replay

## Context
A signal or status report is not auditable unless the exact source data, contract, code, configuration and computation can be identified and replayed. A timestamp or a Telegram message alone is not sufficient evidence.

## Decision
Every finalized L2 artifact must carry or reference an immutable run manifest containing:
- unique run_id and artifact_id;
- source commit SHA and reproducible build identity;
- L1 schema version and canonical input digest;
- exact dataset identity, source provider(s), instrument identity and retrieval window;
- configuration and strategy/path version identifiers;
- execution timestamp and runtime environment identity;
- per-instrument admission, quality and rejection trace;
- output artifact SHA-256 digest.

The artifact is written atomically and never overwritten. A correction creates a new artifact identity and preserves the earlier artifact and audit history.

## Determinism
For identical canonical inputs, configuration, source revision and build identity, deterministic L2 components must produce equivalent outputs. Bitwise identity is preferred. If floating-point or platform behavior prevents bitwise identity, each field requiring tolerance must define that tolerance explicitly and be tested.

Replay must not silently fetch new market data. It consumes the immutable L1 contract captured for the original run.

## Current implementation
- C++ SHA-256 artifact sealing and pre-delivery verification are implemented.
- Atomic L2 output creation is implemented.
- Full source-commit/build manifest, input digest linkage, replay command and replay equivalence suite remain pending.
- SHA-256 sealing does not by itself prove the entire computation is deterministic.

## Acceptance
1. Artifact hash verification passes for unmodified content and fails after any mutation.
2. The manifest identifies source commit, build, L1 schema and input digest.
3. Replay from the retained L1 input produces equivalent L2 output under the declared comparison rules.
4. Finalized artifacts cannot be overwritten by a repeated run.
5. Corrections retain lineage to the superseded artifact.

## Prohibitions
- No mutable finalized artifact.
- No replay that substitutes newly fetched data for the original input.
- No claim of reproducibility from a hash alone.
