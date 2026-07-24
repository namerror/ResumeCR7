# 013. App-Owned Resume Evidence CRUD API

Date: 2026-07-22

## Status

Accepted

## Context

ResumeCR7 is transitioning from a prototype with standalone local orchestration
into a FastAPI-backed resume service. Resume evidence had been moved to a
top-level `resume_evidence/` package so CLI and local generation code could use
it independently, but the next product boundary needs evidence to be exposed
through backend HTTP endpoints.

The repo still needs to preserve the legacy CLI, avoid early database
dependencies, and keep user-authored evidence files out of importable
application package code.

## Decision

Move the evidence domain implementation into `app/resume_evidence/` and expose
typed REST CRUD endpoints under `/resume-evidence`.

- The backend owns evidence schemas, loading, session mutation, service helpers,
  and the FastAPI router under `app.resume_evidence`.
- Top-level `resume_evidence` modules remain as compatibility shims for the
  legacy CLI and existing import paths.
- REST mutations write immediately to YAML through the existing atomic
  validation-before-commit session behavior.
- Evidence YAML remains under configurable runtime storage, defaulting to
  `user/resume_evidence/` through `RESUME_EVIDENCE_ROOT`.
- List-backed resources use stable IDs in URLs. Education evidence now has an
  `id` field, with deterministic ID filling for older YAML that does not yet
  include it.

## Consequences

### Positive

- Product clients can manage resume evidence through normal REST resource URLs.
- Backend code has a clear app-owned module boundary for future service work.
- Existing local YAML and CLI workflows continue to work during migration.
- Database persistence can still be added later behind the service/storage
  boundary.

### Negative

- The repo keeps compatibility shims until legacy imports are retired.
- Education evidence gains a persisted stable ID field.
- File-backed HTTP writes are suitable for local mode but not a final
  multi-user persistence model.

### Neutral

- Existing selection, generation, link scanning, and bullet endpoints remain
  unchanged.
- The API does not add auth, user accounts, database tables, or background jobs.
- The legacy CLI remains index-oriented even though HTTP routes are ID-oriented.

## Alternatives Considered

- Keep `resume_evidence/` as the implementation package and import it from the
  backend: rejected because the product API boundary is now centered on the
  FastAPI app.
- Move YAML files under `app/`: rejected because user-authored mutable evidence
  should not be packaged as application source.
- Expose CLI-style staged apply/reload over HTTP: rejected because immediate
  writes match normal REST expectations and keep clients simpler.
- Add a database now: rejected because the repo still needs a stable API/storage
  boundary before committing to durable multi-user persistence.
