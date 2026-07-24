# 014. Canonical Link Evidence Enrichment Endpoint

Date: 2026-07-22

## Status

Accepted

## Context

ResumeCR7 exposed two semantically equivalent link enrichment endpoints:
`POST /scan-link` and `POST /enrich-link-evidence`. Both routes called the same
service function, but `/scan-link` carried the older project-only naming and a
legacy request shape that accepted `project` plus optional `context` fields.

The active enrichment flow now supports project and experience evidence through
a generic `evidence_type` plus `evidence` request contract. Keeping both routes
made the internal API harder to reason about without adding behavior.

## Decision

Use `POST /enrich-link-evidence` as the only HTTP endpoint for link evidence
enrichment.

- Remove the duplicate `POST /scan-link` route.
- Remove the legacy project/context request adapter.
- Keep the underlying link scanning service and model names stable for now to
  avoid unrelated internal churn.

## Consequences

### Positive

- Removes a duplicate internal API surface.
- Makes the accepted enrichment request contract explicit.
- Avoids preserving project-only compatibility now that enrichment covers
  multiple evidence types.

### Negative

- Clients still calling `/scan-link` must move to `/enrich-link-evidence`.
- Legacy payloads using `project` and `context` are rejected by the canonical
  endpoint.

### Neutral

- Link enrichment behavior and CLI orchestration are unchanged.
- Historical docs and devlogs may still mention `/scan-link` as prior behavior.

## Alternatives Considered

- Keep `/scan-link` as an alias: rejected because there are no production
  callsites in the repo and the duplicate route creates avoidable ambiguity.
- Deprecate before removal: rejected because these stage endpoints are internal
  capability APIs, not the product API contract.
