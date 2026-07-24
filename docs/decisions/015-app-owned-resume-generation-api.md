# 015. App-Owned Resume Generation API

Date: 2026-07-23

## Status

Accepted

## Context

ResumeCR7's evidence domain has already moved into `app/resume_evidence/`, with
top-level `resume_evidence` kept as a compatibility layer for the local CLI.
The resume-generation pipeline was still implemented as a top-level
`resume_generation/` package and called the running FastAPI app over HTTP for
selection, focus derivation, and bullet generation stages.

That shape was useful while generation was local-only, but it is now awkward for
backend product routes: the backend should own internal generation workflows,
and a request handled by FastAPI should not need to call the same app through a
loopback HTTP client.

## Decision

Move resume-generation implementation into `app/resume_generation/` and expose
a synchronous v1 FastAPI facade under `/resume-generation`.

- `app.resume_generation` owns config loading, stage cache, selection
  orchestration, job-focus orchestration, bullet orchestration, assembly,
  LaTeX rendering, PDF rendering, link-enrichment batch orchestration, and the
  FastAPI router.
- Top-level `resume_generation` modules remain compatibility shims for existing
  imports and `python -m resume_generation.*` entrypoints.
- Generation stages call in-process app services by default instead of making
  loopback HTTP requests.
- `POST /resume-generation/enrich-link-evidence` scans all selected project and
  experience records with links, appends unique highlights, writes YAML
  atomically unless `dry_run`, and refreshes app evidence state after writes.
- `POST /resume-generation/tex` runs the full pipeline, writes the existing JSON
  result and run manifest, writes the configured `.tex` artifact, and returns
  paths plus `.tex` content.
- `POST /resume-generation/pdf` renders the configured/default `.tex` artifact
  to PDF and returns the generated PDF bytes.

## Consequences

### Positive

- Backend product routes can trigger full resume-generation workflows directly.
- The pipeline no longer depends on a running loopback HTTP server for internal
  stages.
- Existing imports and local module entrypoints continue to work while clients
  migrate.
- The new facade separates user-facing generation actions from lower-level
  stage endpoints.

### Negative

- The repo carries compatibility shims until legacy imports are retired.
- Synchronous v1 endpoints can still be long-running because LLM-backed stages
  and local LaTeX rendering happen inside the request.

### Neutral

- File-backed `user/` storage remains the local persistence mechanism.
- No auth, database, job queue, background worker, or multi-user artifact store
  is introduced.
- Existing stage endpoints such as `/select-skills`, `/select-projects`,
  `/derive-job-focus`, `/generate-bulletpoints`, and `/enrich-link-evidence`
  remain available as internal capabilities.

## Alternatives Considered

- Keep top-level `resume_generation/` as the implementation package: rejected
  because the backend product API is now centered on `app/`.
- Make the facade call internal endpoints over HTTP: rejected because it keeps
  the loopback dependency and adds failure modes without improving isolation.
- Implement the async run lifecycle from ADR 012 immediately: deferred because
  the current request needs three concrete endpoints and the repo still avoids
  early queue/database dependencies.
- Remove top-level imports immediately: rejected because existing tests,
  scripts, and CLI entrypoints still use `resume_generation`.
