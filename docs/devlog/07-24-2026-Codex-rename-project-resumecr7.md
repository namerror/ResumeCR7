### 2026-07-24 - Rename project to ResumeCR7

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md:1-3` - Updated the public project name and top-level project description to ResumeCR7.
- `app/main.py:48-58` - Renamed the FastAPI title and health service identifier to ResumeCR7.
- `app/resume_generation/api.py:207-208` - Renamed generated PDF artifact headers from the old project prefix to `X-ResumeCR7-*`.
- `pytest.ini:1-2` - Added an explicit repo-root Python path so `.venv/bin/pytest` works after the top-level directory rename.
- `frontend/package.json:2` and `frontend/package-lock.json` - Renamed the frontend package metadata to `resumecr7-frontend`.
- `frontend/index.html:6` and `frontend/src/App.tsx:445-448` - Updated browser title, workbench label, and brand mark.
- `tests/`, `docs/`, `frontend/src/*.test.ts*`, and `user/resume_evidence/projects.yaml:106` - Updated fixtures, documentation examples, test expectations, and the user project link from the old project name to ResumeCR7.
- `docs/devlog/04-23-2026-Codex-refresh-resumecr7-docs-for-grounded-resume-engine.md` - Renamed the prior devlog filename to remove the old project slug and kept the index in sync.
- `/home/leon/Documents/proj/ResumeCR7` - Renamed the top-level project directory and repaired local `.venv` text entrypoints that embedded the old absolute path.

**Rationale:**
The user requested a project-wide rename. I used a mechanical rename for branding, service identifiers, sample project IDs, test fixtures, API examples, frontend metadata, and documentation so the repository consistently presents the project as ResumeCR7 without changing unrelated Python package boundaries.

**Tests:**
- `.venv/bin/pytest`: validates backend APIs, models, selection logic, resume evidence, and resume generation after the rename and top-level directory move.
- `npm test -- --run`: validates frontend API calls, diff logic, and workbench interactions with renamed fixture labels.
- `npm run build`: validates the renamed frontend metadata and UI still compile into production assets.

**Impact:**
ResumeCR7 is now the project identity across tracked source, tests, docs, frontend metadata, local user evidence, and the filesystem directory. The rename preserves current backend and frontend behavior while updating externally visible labels and service strings.
