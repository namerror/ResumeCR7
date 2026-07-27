### 2026-07-27 - Persist Desktop Job Target

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_generation/config.py` - Added atomic validated writes for `job_target.yaml`.
- `app/resume_generation/api.py` - Added `GET` and `PUT` routes for the saved resume-generation job target.
- `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx` - Loaded, staged, validated, applied, reloaded, and discarded job target data through the desktop workbench.
- `tests/test_resume_generation_config_api.py`, `frontend/src/App.test.tsx`, `frontend/src/api.test.ts`, `frontend/src/testFixtures.ts` - Added backend and frontend coverage for saved job target persistence.

**Rationale:**
The desktop Generate screen previously kept job title and description only in React state and sent them as a request-scoped generation override. Restarting the app cleared those fields even though `job_target.yaml` already existed as the pipeline source of truth. Persisting the job target through the existing staged Apply workflow keeps the target durable and lets generation reuse cache entries keyed by the saved target.

**Tests:**
- `test_resume_generation_job_target_get_reads_saved_yaml`: validates the API reads the saved YAML target.
- `test_resume_generation_job_target_put_persists_yaml`: validates trimmed, schema-valid target writes.
- `test_resume_generation_job_target_put_rejects_blank_title_without_writing`: validates invalid target edits do not corrupt the saved file.
- Frontend app/API tests validate startup hydration, staged Apply persistence, and generation from the saved target.

**Impact:**
Desktop users can restart the app without losing job target data after applying changes. Resume generation now uses the durable target by default, reducing repeated token cost when cacheable stages already exist for the same job.
