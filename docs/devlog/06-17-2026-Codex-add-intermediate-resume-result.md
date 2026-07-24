### 2026-06-17 - Add Intermediate Resume Result Assembly

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_generation/models.py:240-286` - Added strict intermediate resume result models for top contact, education, experience, projects, and selected skills.
- `resume_generation/assembly.py:24-88` - Added deterministic assembly from loaded evidence, selected/enriched projects, and runtime project bullet points.
- `resume_generation/main.py:17-84` - Wired the pipeline to build a local `resume_result` after bullet generation and return `None` while output development remains incomplete.
- `resume_generation/__init__.py` - Exported the new schema models and assembly helper.
- `tests/test_resume_generation.py:484-608` - Added direct assembler coverage for contact data, education, active experience filtering, skill ordering, project bullets, link normalization, and selected skills.
- `tests/test_resume_generation.py:923-1053` - Updated pipeline tests for the no-return behavior and verified assembly receives generated project bullets after the HTTP stages.

**Rationale:**
The generation pipeline needed a typed intermediary result before any final resume artifact output exists. Keeping assembly in `resume_generation` preserves the current FastAPI service boundary and keeps the step deterministic: all fields are copied from already-loaded evidence, selection results, or runtime bullet-point generation without adding synthesis.

**Tests:**
- `test_assemble_intermediate_resume_result_builds_deterministic_schema`: validates the assembled schema shape, stable skill concatenation, active-only experience inclusion, project order, runtime bullets, and link normalization.
- `test_resume_generation_pipeline_loads_config_job_and_evidence_once`: validates the pipeline still loads inputs once and calls assembly after bullet generation with the expected runtime data.
- `test_resume_generation_pipeline_optionally_scans_links_before_bullet_generation`: validates link-enriched project highlights still flow into bullet generation while the pipeline now returns `None`.
- `PYTHONPATH=. .venv/bin/python -m pytest tests/test_resume_generation.py`: 18 passed.
- `.venv/bin/python -m pytest`: 383 passed, 4 skipped.

**Impact:**
ResumeCR7 now has a concrete in-memory resume draft schema that later rendering or artifact-generation steps can consume without changing existing selection, link scanning, or bullet-point APIs.
