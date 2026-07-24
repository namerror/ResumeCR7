### 2026-06-05 - Bullet Point Generation API

**Agent:** Codex (GPT-5)

**Changes:**
- `app/bulletpoints_generation/models.py` - Added strict job context, bullet-count range, request, and response models.
- `app/bulletpoints_generation/llm_client.py` - Added an OpenAI Responses API client with strict JSON schema output, grounded prompt payloads, count-range instructions, and local response validation.
- `app/bulletpoints_generation/service.py` - Added default range resolution, link-scanning rejection, metrics recording, logging, and no-fallback LLM error propagation.
- `app/main.py` - Added `POST /generate-bulletpoints` and exposed bullet-point generation settings in `/health`.
- `app/config.py` and `app/metrics.py` - Added bullet-point generation defaults and subsystem metrics.
- `docs/decisions/009-bullet-point-generation-api-boundary.md` - Recorded the first prose-generation API boundary.
- `tests/test_bulletpoints_generation_models.py`, `tests/test_bulletpoints_llm_client.py`, and `tests/test_bulletpoints_generation_api.py` - Added model, client, service, API, and metrics coverage.
- `docs/CHANGELOG.md` - Added the new endpoint under Unreleased user-facing additions.

**Rationale:**
Bullet generation is the first grounded prose-writing capability in ResumeCR7, so it needs a narrow service boundary rather than being mixed into full resume orchestration. The implementation follows the existing selection-service pattern while intentionally avoiding deterministic prose fallbacks and external link scanning in v1.

**Tests:**
- `test_bullet_count_range_accepts_exact_and_flexible_ranges`: validates exact and flexible range inputs.
- `test_generate_bulletpoints_with_llm_sends_strict_schema`: validates the Responses API request shape and metadata handling.
- `test_build_bulletpoint_prompt_payload_excludes_links`: validates link URLs are not included in the v1 prompt.
- `test_generate_bulletpoints_api_success_with_default_count_and_details`: validates endpoint success, default count resolution, dev metadata, and metrics.
- `test_generate_bulletpoints_api_returns_502_on_llm_failure`: validates no-fallback error behavior.
- Full suite: `.venv/bin/python -m pytest` passed with 308 passed and 4 skipped.

**Impact:**
ResumeCR7 can now generate job-tailored project bullet points from grounded project evidence through a minimal REST API, with explicit configuration, observability, and tests before broader resume synthesis is wired in.
