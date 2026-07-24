### 2026-07-23 - App-Owned Resume Generation API

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_generation/api.py:24-189` - Added `/resume-generation` facade routes for batch link enrichment, full `.tex` generation, and PDF byte responses.
- `app/resume_generation/selection.py:54-101` - Added an in-process stage client that dispatches pipeline stages to app services by default while preserving HTTP-shaped cache/manifest records.
- `app/main.py:33-50` - Registered the resume-generation router with the FastAPI app.
- `app/skill_selection/baseline_filter.py:119-127` - Fixed full baseline-filter fallback so it no longer includes zero-score filler skills.
- `resume_generation/` - Replaced top-level implementation modules with compatibility shims pointing at `app.resume_generation`, preserving local module entrypoints.
- `tests/test_resume_generation.py:4120-4390` - Added facade endpoint coverage and a local-service pipeline regression.
- `tests/test_compat_imports.py` - Added assertions that legacy resume-generation imports alias canonical app modules.
- `docs/decisions/015-app-owned-resume-generation-api.md` - Recorded the app-owned generation API decision.
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/architecture-overview.md`, `docs/agent-context-index.md`, and `docs/CHANGELOG.md` - Updated public and agent-facing docs for the new package boundary and endpoints.

**Rationale:**
The backend now owns evidence CRUD and should also own full resume-generation workflows. Moving implementation under `app.resume_generation` keeps product-facing routes in the FastAPI app, removes the default loopback HTTP dependency inside generation, and keeps existing local imports/commands stable through shims.

The full-suite run also exposed that baseline-filter fallback was not matching normal baseline behavior when a second-pass scorer failed. Removing zero-score filler from that fallback keeps the required baseline method behavior intact.

**Tests:**
- `test_resume_generation_enrich_link_evidence_route_returns_batch_result_and_refreshes_state`: validates the batch enrichment facade response and evidence-state refresh.
- `test_resume_generation_tex_route_runs_pipeline_and_returns_tex_content`: validates the `.tex` facade runs the pipeline and returns artifact content.
- `test_resume_generation_pdf_route_returns_rendered_pdf`: validates PDF bytes, headers, and configured render options.
- `test_resume_generation_pdf_route_returns_404_for_missing_tex`: validates missing `.tex` maps to 404.
- `test_resume_generation_pdf_route_returns_502_for_latex_failure`: validates LaTeX renderer failures map to 502.
- `test_resume_generation_pipeline_uses_local_stage_services_by_default`: validates pipeline stages use in-process services without a patched HTTP client.
- `test_baseline_filter_embedding_failure_returns_full_baseline`: validates failed model-backed baseline-filter second passes return the same selections as normal baseline.

**Impact:**
ResumeCR7 now exposes synchronous backend resume-generation endpoints for enrichment, `.tex`, and PDF output while preserving existing local workflows. Future async run/status APIs can build above this app-owned boundary without clients coordinating low-level stage endpoints.
