# 016. Local-First Web Workbench With Desktop Distribution

Date: 2026-07-23

## Status

Accepted

## Context

ResumeCR7 is moving from a backend resume engine toward an application that can
be used directly. The desired product workflow is interactive: users edit
resume evidence, paste or edit a job description, generate a targeted resume,
review and adjust resume items, then export a final PDF.

The repo already has a FastAPI service boundary, app-owned evidence CRUD,
synchronous v1 resume-generation facade endpoints, YAML-backed local storage,
and local LaTeX/PDF artifact rendering. It intentionally avoids early auth,
database-backed persistence, hosted multi-user concerns, and async queue
infrastructure until the product boundary is clearer.

This creates a product-shape choice:

- a hosted web app with remote backend and persistent user accounts
- a pure browser-local app with local browser storage
- a desktop app that keeps data and generation local
- a local-first web workbench that can later be packaged as a desktop app

## Decision

Build the first product surface as a local-first web workbench over the existing
FastAPI backend, kept in the same repository. Treat desktop packaging as the
first distribution target after the workflow is proven.

- Add a frontend application in the monorepo, for example under `frontend/`.
- Use the FastAPI backend as the only writer of resume evidence, generation
  results, LaTeX, and PDF artifacts.
- Keep local YAML-backed storage as the first persistence adapter for evidence
  and generated artifacts.
- Run the backend locally on loopback for the initial app model.
- Let the frontend call product-facing facade APIs for evidence CRUD and resume
  generation instead of directly orchestrating low-level stage endpoints.
- Preserve the distinction between source evidence, generated resume drafts,
  and final user edits.
- Package the proven local web workbench as a desktop app before pursuing a
  hosted multi-user web service.
- Keep the frontend and backend in a monorepo until API boundaries and release
  cadence justify splitting them.

The near-term product flow should be:

```text
local frontend workbench
  -> localhost FastAPI backend
  -> file-backed evidence and generation adapters
  -> structured resume result
  -> local LaTeX/PDF artifact rendering
```

## Consequences

### Positive

- Avoids auth, account management, database migrations, hosted artifact storage,
  and multi-user data isolation while the product workflow is still evolving.
- Reuses the current FastAPI backend and app-owned evidence/generation facade.
- Keeps sensitive resume data local by default.
- Allows normal web frontend development while preserving a path to desktop
  distribution.
- Makes browser-local storage an implementation detail of the UI, not the source
  of truth for evidence or generated artifacts.
- Keeps frontend and backend schemas close while the API is still changing.

### Negative

- Users must run or install a local backend instead of visiting a hosted site.
- Desktop packaging will need process management for the local Python backend
  and a clear app data directory.
- Local PDF rendering still depends on the runtime having the required LaTeX
  tooling unless a later renderer replaces it.
- The monorepo will grow to include frontend build tooling and package metadata.

### Neutral

- This decision does not add a frontend implementation yet.
- This decision does not add auth, database persistence, remote hosting,
  background workers, or account-level artifact storage.
- A hosted web service remains possible later behind storage adapters and a
  generation-run lifecycle.
- Electron and Tauri remain viable desktop packaging options; the first choice
  can be made when packaging work begins.

## Alternatives Considered

- Hosted multi-user web app: deferred because it immediately requires auth,
  durable user storage, secret management, rate limiting, deletion/export
  policy, artifact storage, and background jobs.
- Pure browser-local app: rejected for the first product model because the
  existing Python backend owns validation, generation, OpenAI calls,
  file-backed evidence, LaTeX rendering, and PDF artifact creation.
- Desktop-only app from the start: deferred because building the workflow first
  as a local web workbench is simpler and keeps the UI reusable.
- Separate frontend and backend repositories: rejected for now because the API
  surface is still evolving and a monorepo keeps schema and workflow changes
  easier to coordinate.
