### 2026-07-26 - Dynamic LLM Output Budgets

**Agent:** Codex (GPT-5)

**Changes:**
- `app/project_selection/llm_client.py:96-360` - Added dynamic project-selection output token budget resolution, retry-on-parse-failure behavior, and resolved budget metadata.
- `app/bulletpoints_generation/llm_client.py:176-488` - Added per-record bullet output token budget resolution, optional cap handling, and budget-aware retry/error metadata.
- `app/resume_generation/models.py:69-195` - Added typed resume-generation config blocks for project and bullet output token budgets.
- `app/resume_generation/selection.py:46-356` - Excluded dynamic budget controls from selection cache keys and added requested/resolved budget fields to stage response records.
- `user/resume_generation/config.yaml` - Replaced static project and bullet `llm_max_output_tokens` defaults with per-size `llm_output_token_budget` blocks.
- `tests/test_project_llm_client.py`, `tests/test_bulletpoints_llm_client.py`, `tests/test_project_selection_api.py`, `tests/test_bulletpoints_generation_api.py`, `tests/test_resume_generation.py`, `tests/test_health.py`, and `tests/test_config.py` - Updated and added coverage for dynamic budgets, override compatibility, config loading, API pass-through, and health output.

**Rationale:**
Static project and bullet output caps were brittle as resume evidence grows. Project selection needs to size scoring output from candidate count and prompt size, while bullet generation needs to size each request from the actual evidence record, requested bullet count, and highlight volume. Explicit `llm_max_output_tokens` remains supported as a debugging override, but default resume-generation config now expresses dynamic sizing with no maximum cap unless configured.

**Tests:**
- `test_resolve_project_max_output_tokens_scales_and_caps`: validates project budget scaling and optional cap behavior.
- `test_resolve_bulletpoint_max_output_tokens_scales_and_caps`: validates bullet budget scaling from bullet count, highlights, and evidence size.
- `test_score_projects_with_llm_accepts_explicit_max_output_override` and `test_generate_bulletpoints_with_llm_accepts_explicit_max_output_override`: validate backward-compatible hard-cap overrides.
- `test_select_projects_api_passes_output_token_budget` and `test_generate_bulletpoints_api_passes_output_token_budget`: validate API pass-through for nested budget objects.
- `PYTHONPATH=. .venv/bin/python -m pytest -q`: 564 passed, 4 skipped when run outside the sandbox because the packaging smoke test requires loopback socket creation.

**Impact:**
Project selection and bullet generation now scale output budgets with request size by default, preserve explicit override controls, and expose resolved budget metadata in logs, stage records, and dev details for easier diagnosis.
