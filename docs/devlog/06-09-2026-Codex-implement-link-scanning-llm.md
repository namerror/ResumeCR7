### 2026-06-09 - Implement LLM-backed link scanning

**Agent:** Codex (GPT-5)

**Changes:**
- `app/link_scanning/llm_client.py:29-296` - Added the OpenAI Responses link-scanning client with strict highlight-only JSON schema, web-search tooling, prompt construction, source URL validation, duplicate filtering, and token/latency metadata.
- `app/link_scanning/models.py:34-74` and `app/link_scanning/service.py:30-80` - Added request-level LLM overrides, removed skill additions from the response contract, and wired service-level 502 error propagation for unusable scans.
- `resume_generation/link_scanning.py:36-67` and `resume_generation/models.py:149-248` - Passed link-scanning model/token config through orchestration and merged only scanned highlights into in-memory project copies.
- `app/config.py`, `app/main.py`, `user/resume_generation/config.yaml`, `README.md`, and `docs/CHANGELOG.md` - Added link-scanning model/token settings, health output, default generation config, and user-facing documentation.
- `tests/test_link_scanning_llm_client.py`, `tests/test_link_scanning_api.py`, `tests/test_resume_generation.py`, `tests/test_health.py`, and `tests/test_config.py` - Added and updated coverage for strict schema construction, web-search request kwargs, API success/failure behavior, config overrides, and highlight-only enrichment.

**Rationale:**
Link scanning now collects grounded project facts from every configured project link while preserving the repository invariant that skills are not invented or added by model-backed enrichment. Keeping the scan output as a patch-style highlight list lets downstream bullet generation use the additional evidence without mutating source evidence files.

**Tests:**
- `test_scan_project_links_with_llm_sends_web_search_request`: validates the Responses call uses web search, strict JSON schema, all project links, and metadata extraction.
- `test_scan_link_api_returns_llm_highlight_patch_with_details`: validates `/scan-link` returns highlight-only patches and dev-mode scan metadata.
- `test_scan_link_api_returns_502_when_llm_fails`: validates strict failure behavior for unusable scans.
- `test_enrich_projects_with_link_scanning_posts_linked_projects_and_merges_patch`: validates orchestration passes scan overrides and does not modify project skills.
- `PYTHONPATH=. .venv/bin/python -m pytest tests/test_link_scanning_llm_client.py tests/test_link_scanning_api.py tests/test_resume_generation.py tests/test_health.py tests/test_config.py`: 45 passed.

**Impact:**
ResumeCR7 can now enrich selected projects with link-backed factual highlights before bullet generation. The implementation scans all project links, keeps provenance visible through source URLs, and preserves grounded resume behavior by failing closed when the model/web scan cannot produce trusted output.
