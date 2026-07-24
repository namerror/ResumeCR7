### 2026-07-23 - Add Resume Evidence Frontend Workbench

**Agent:** Codex (GPT-5)

**Changes:**
- `frontend/package.json:1-32` - Added a React/Vite/TypeScript frontend package with build, dev, preview, and Vitest scripts.
- `frontend/vite.config.ts:1-31` - Configured Vite, Vitest, and a `/api` development proxy to the local FastAPI backend.
- `frontend/src/api.ts:24-162` - Added a typed resume-evidence API client for health checks, registry loading, singleton updates, and collection CRUD.
- `frontend/src/diff.ts:28-318` - Added pure staged-apply diffing that converts draft edits into serial calls against the existing `/resume-evidence` endpoints while omitting record IDs from create/update payloads.
- `frontend/src/App.tsx:78-461` - Added the main local-first workbench shell, evidence loading, dirty-state tracking, Apply/Reload/Discard behavior, and section routing.
- `frontend/src/App.tsx:606-1042` - Added collection lists, record editors, field/list controls, skill bucket editors, and utility presentation components.
- `frontend/src/validation.ts:1-80` - Added frontend validation to block Apply when required fields or list entries are blank.
- `frontend/src/styles.css:1-655` - Added responsive workbench styling for desktop and mobile editor layouts.
- `frontend/src/*.test.ts*` - Added frontend tests for API request shape, staged diff operations, and UI staging/apply flows.
- `docs/CHANGELOG.md:8-12` - Added an Unreleased entry for the new frontend workbench.

**Rationale:**
ADR 016 calls for a local-first web workbench that can later be packaged as a desktop app. The existing backend writes YAML immediately per CRUD call, so the frontend owns staging: it keeps a baseline copy and draft copy in browser state, computes a diff on Apply, and then calls the current backend endpoints serially. This avoids widening the backend API before the app workflow is proven.

**Tests:**
- `npm run test`: validates diffing, ID-free API payloads, FastAPI error detail handling, and UI staging behavior.
- `npm run build`: validates TypeScript and production Vite bundling.
- `.venv/bin/python -m pytest tests/test_resume_evidence_api.py`: validates the existing backend evidence CRUD contract still passes.

**Impact:**
ResumeCR7 now has its first local-first frontend surface for editing user, skills, projects, experience, and education evidence. The app keeps YAML persistence backend-owned, prepares the UI for loopback desktop packaging through configurable API base/proxy settings, and gives future resume-generation workflow work a concrete frontend foundation.
