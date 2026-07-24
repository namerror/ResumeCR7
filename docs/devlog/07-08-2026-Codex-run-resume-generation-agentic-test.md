### 2026-07-08 - Run Resume Generation Agentic Test

**Agent:** Codex (GPT-5)

**Changes:**
- `docs/notes/07-08-2026-Codex-resume-generation-agentic-test.md:1` - Added an agentic testing report for the full `resume_generation` pipeline, including run setup, failure history, final JSON artifact assessment, selection critique, bullet critique, token notes, and recommendations.
- `docs/devlog/Index.md:12` - Added this session to the devlog index.

**Rationale:**
The user requested an agentic testing session for the whole `resume_generation` pipeline, focused on the intermediate JSON artifact rather than LaTeX output. I followed the existing agentic testing style while adapting it to the pipeline entrypoint and stage cache. Because the sandbox could not bind or reach local API sockets, I ran the API and pipeline outside the sandbox on an alternate port and used a temporary config under `/tmp` so the tracked user config was not modified.

**Tests:**
- `run_resume_generation_pipeline(config_path=/tmp/resumecr7-resume-generation-config.yaml)` - Exercised the full pipeline against `user/resume_generation/job_target.yaml` and `user/resume_evidence/`.
- `IntermediateResumeResult.model_validate(...)` - Validated `user/resume_generation/resume_result.json` against the intermediate artifact schema.
- Stage cache inspection with `jq` - Reviewed skill-selection fallback, project ranking, bullet-generation details, and token usage for the final assessment.

**Impact:**
Documents the current behavior of the full resume generation pipeline under realistic evidence and job-target inputs. The report identifies runtime brittleness around bullet JSON generation and timeout settings, skill-selection fallback quality concerns, and the need for run metadata in or near the final JSON artifact.
