### 2026-06-08 - Link Scanning Scaffold

**Agent:** Codex (GPT-5)

**Changes:**
- `app/link_scanning/models.py:14-71` - Added strict request/response schemas for one-project link scanning with patch-style highlights and skills.
- `app/link_scanning/service.py` - Added the no-op placeholder scanner that returns empty patch data and dev-mode details.
- `app/main.py:24-103` - Registered the standalone `/scan-link` API and moved health reporting to a standalone `link_scanning` section.
- `resume_generation/models.py:125-236` - Removed link scanning from bullet generation config and added top-level link scanning config plus client-side scan result models.
- `resume_generation/link_scanning.py:16-72` - Added optional orchestration logic that calls `/scan-link`, skips projects without links, and merges returned highlights/skills in memory.
- `resume_generation/main.py:45-55` - Wired link scanning before bullet-point generation.
- `user/resume_generation/config.yaml:18-25` - Moved the default link scanning toggle out of `bullet_point_generation`.
- `tests/test_link_scanning_api.py` - Added API coverage for placeholder responses and invalid project payloads.
- `tests/test_resume_generation.py:327-653` - Added orchestration coverage for scan request dispatch, merge behavior, skipped unlinked projects, and pipeline ordering.

**Rationale:**
Link scanning is now modeled as a standalone evidence-enrichment utility instead of a bullet-generation option. The API returns patch-style additions so future scanning logic can expose exactly what it wants to add while the pipeline keeps original evidence immutable and applies enrichment only for downstream generation.

**Tests:**
- `test_scan_link_api_returns_placeholder_patch_with_details`: validates the scaffold API contract.
- `test_generate_bulletpoints_api_rejects_link_scanning_field`: validates bullet generation no longer accepts the scanning flag.
- `test_enrich_projects_with_link_scanning_posts_linked_projects_and_merges_patch`: validates scan calls, project skipping, highlight appends, and stable skill additions.
- `test_resume_generation_pipeline_optionally_scans_links_before_bullet_generation`: validates scan enrichment runs before bullet generation when enabled.
- `PYTHONPATH=. pytest tests/test_link_scanning_api.py tests/test_bulletpoints_generation_api.py tests/test_health.py tests/test_config.py tests/test_resume_generation.py`

**Impact:**
ResumeCR7 now has the API and orchestration seam needed for future real link scanning without coupling the scanner to bullet prompt logic or persisting unverified scanned evidence.
