### 2026-06-02 - Standalone Resume Evidence Package

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_evidence/loader.py:9-21` - Moved the evidence package out of `app/`, updated imports to top-level `resume_evidence`, and corrected repo-root resolution for the new package depth.
- `resume_generation/__init__.py:1-5` - Added the reserved top-level generation orchestration package boundary.
- `app/main.py:15-21` - Updated FastAPI startup validation to import `load_registered_evidence()` from the standalone evidence package.
- `app/project_selection/models.py:7-23` - Updated project-selection models to reuse `ProjectSkills` from `resume_evidence.models`.
- `docs/decisions/008-standalone-resume-evidence-and-generation-layers.md:1-68` - Added the ADR for moving evidence out of `app/` and reserving `resume_generation/` for future orchestration.
- `README.md`, `docs/architecture-overview.md`, `docs/branch-03-grounded-resume-generation.md`, `docs/agent-context-index.md`, `docs/project-selection-plan.md`, `CLAUDE.md`, and `AGENTS.md` - Refreshed active docs and agent guidance for the new package layout and CLI entrypoint.
- `tests/test_resume_evidence.py:7-24` - Updated imports and added structural coverage that `resume_evidence` resolves as a top-level package.
- `tests/test_resume_evidence_cli.py`, `tests/test_project_selection_baseline.py`, `tests/test_project_selection_llm.py`, and `tests/test_project_llm_client.py` - Updated imports to the standalone evidence package.

**Rationale:**
The next resume-generation interface needs to load evidence, call skill/project selection services, and combine returned selections. Keeping that orchestration under `app/resume_evidence/` would blur dependency direction because the FastAPI app also imports evidence at startup. Moving evidence to `resume_evidence/` and reserving `resume_generation/` keeps source-of-truth management, service capabilities, and future generation orchestration distinct.

**Tests:**
- `test_resume_evidence_package_is_top_level`: validates the evidence package no longer resolves under `app/resume_evidence/`.
- `.venv/bin/python -m pytest tests/test_resume_evidence.py tests/test_resume_evidence_cli.py tests/test_project_selection_baseline.py tests/test_project_selection_llm.py tests/test_project_llm_client.py tests/test_project_selection_api.py tests/test_health.py`: 111 passed.
- `.venv/bin/python -m resume_evidence.cli --help`: verified the new CLI module entrypoint.
- `.venv/bin/python -m pytest`: 278 passed, 4 skipped.

**Impact:**
ResumeCR7 now has the intended top-level evidence and generation package structure. Selection services remain under `app/`, evidence management is standalone, and future resume-generation work has a clear home for evidence-to-selection orchestration without adding synthesis behavior prematurely.
