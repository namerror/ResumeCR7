### 2026-04-26 - Refactor App Into Subsystem Packages

**Agent:** Codex (GPT-5)

**Changes:**
- `app/skill_selection/` - Moved skill-selection models, selector orchestration, baseline filter, model clients, scoring logic, role profiles, synonym data, and embedding caches into a dedicated subsystem package.
- `app/project_selection/service.py` - Added API-facing project-selection service orchestration with defaults, structured logging, fallback-method metrics, and token accounting.
- `app/project_selection/models.py` - Added `ProjectSelectRequest` for the new API route.
- `app/main.py` - Renamed the FastAPI app to ResumeCR7 Resume Engine, added `POST /select-projects`, and expanded `/metrics-lite` with per-subsystem metrics.
- `app/models.py`, `app/scoring/*`, `app/services/*` - Added compatibility shims for legacy imports.
- `tests/test_project_selection_api.py` and `tests/test_compat_imports.py` - Added route and compatibility coverage.
- `docs/architecture-overview.md`, `README.md`, `docs/agent-context-index.md`, `docs/project-selection-plan.md`, `docs/decisions/005-subsystem-package-organization.md` - Updated architecture docs and recorded the subsystem organization decision.

**Rationale:**
The repo is now a resume engine with multiple subsystems, but skill-selection code still occupied root-level app paths. Moving skill-specific code and data under `app/skill_selection/` makes project selection and future resume modules peers, while compatibility shims avoid a breaking import change.

**Tests:**
- `test_select_projects_api_baseline_success_with_top_n_and_details`: validates the new project-selection route, top-N behavior, and dev metadata.
- `test_select_projects_api_llm_fallback_returns_baseline`: validates API fallback behavior when the project LLM client fails.
- `test_select_projects_api_records_project_metrics_and_tokens`: validates project-selection request and token metrics.
- `test_legacy_skill_selection_imports_alias_canonical_modules`: validates old import paths alias canonical modules.
- `.venv/bin/python -m pytest -q`: full suite passes.

**Impact:**
ResumeCR7 now has a clearer subsystem layout for skill selection, project selection, and resume evidence. Project selection is available through a public route, and metrics can distinguish skill-selection and project-selection traffic while keeping existing aggregate fields.
