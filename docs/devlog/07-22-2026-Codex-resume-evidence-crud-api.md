### 2026-07-22 - Resume Evidence CRUD API

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_evidence/models.py:36-293` - Moved evidence models under `app/`, added API input models, added education IDs with legacy YAML ID filling, and introduced a typed registry response.
- `app/resume_evidence/loader.py:18-69` - Moved evidence loading under `app/` and added configurable path resolution from `RESUME_EVIDENCE_ROOT`.
- `app/resume_evidence/session.py:70-429` - Added education ID generation/preservation and switched default session loading to dynamic configured paths.
- `app/resume_evidence/service.py:31-257` - Added ID-oriented backend CRUD helpers over the existing staged session classes.
- `app/resume_evidence/api.py:46-293` and `app/main.py:33-48` - Added `/resume-evidence` FastAPI routes and included the router in the application.
- `resume_evidence/{__init__,models,loader,session}.py` - Replaced top-level implementation modules with compatibility shims for legacy imports and CLI usage.
- `user/resume_evidence/education.yaml` - Added the stable starter education record ID.
- `docs/decisions/013-app-owned-resume-evidence-crud-api.md` - Recorded the app-owned evidence package and YAML storage boundary decision.
- `docs/architecture-overview.md`, `docs/agent-context-index.md`, `README.md`, and `docs/CHANGELOG.md` - Updated docs for the implemented CRUD API and package migration.

**Rationale:**
The backend should own the evidence HTTP boundary while the current YAML files remain local runtime storage rather than package data. Immediate writes match normal REST expectations, and compatibility shims keep the legacy CLI working while internal backend code imports from `app.resume_evidence`.

**Tests:**
- `tests/test_resume_evidence_api.py` - Added REST coverage for listing registered evidence, singleton reads/updates, project/experience/education create-read-update-delete flows, stable ID generation, missing IDs, validation failures, and YAML persistence.
- `tests/test_resume_evidence.py` - Updated migration assertions and added legacy education ID filling coverage.
- `tests/test_resume_evidence_cli.py` and `tests/test_resume_generation.py` - Updated education fixtures for the stable ID field.
- `python -m pytest tests/test_resume_evidence.py tests/test_resume_evidence_api.py` - 86 passed.
- `python -m pytest tests/test_resume_evidence_cli.py` - 82 passed.
- `python -m pytest tests/test_health.py tests/test_project_selection_api.py tests/test_bulletpoints_generation_api.py tests/test_link_scanning_api.py tests/test_resume_generation.py` - 103 passed.
- `python -m pytest tests/test_resume_evidence.py tests/test_resume_evidence_api.py tests/test_resume_evidence_cli.py tests/test_health.py tests/test_project_selection_api.py tests/test_bulletpoints_generation_api.py tests/test_link_scanning_api.py tests/test_resume_generation.py` - 271 passed.
- `python -m resume_evidence.cli --help` - verified the legacy CLI entrypoint still imports and renders help.
- `python -m pytest` - 512 passed, 4 skipped, 1 failed in `tests/test_baseline_filter.py::test_baseline_filter_embedding_failure_returns_full_baseline`; this failure is outside the resume-evidence migration and reflects the existing baseline-filter fallback/zero-score fill expectation mismatch.

**Impact:**
ResumeCR7 now exposes file-backed resume evidence through FastAPI CRUD endpoints while preserving legacy CLI workflows. The repo is closer to a product-facing backend service without introducing database dependencies or changing existing stage endpoints.
