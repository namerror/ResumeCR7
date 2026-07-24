### 2026-06-11 - Add experience evidence

**Agent:** Codex (GPT-5)

**Changes:**
- `resume_evidence/models.py:56-93` - Added strict `ExperienceRecord` and `ExperienceFile` schemas with project-like fields, required location/start, optional end, unique id validation, and convenience iteration/id lookup helpers.
- `resume_evidence/loader.py:9-32` and `resume_evidence/__init__.py` - Registered and exported the `experience` evidence schema and default `user/resume_evidence/experience.yaml` path.
- `resume_generation/main.py:5-55` - Added pipeline preflight validation that registered evidence includes a valid experience file before selection/generation begins.
- `.gitignore` and `user/resume_evidence/experience.yaml` - Added a starter experience evidence file and a narrow ignore exception so it can be tracked.
- `tests/test_resume_evidence.py` and `tests/test_resume_generation.py` - Added direct schema validation, registered loading/startup, and resume-generation preflight coverage for experience evidence.

**Rationale:**
Experience is now a first-class grounded resume evidence file, but the implementation stays intentionally parallel to projects so it remains deterministic, strict, and easy to consume later. The pipeline currently only validates experience availability; it does not yet synthesize resume content from it.

**Tests:**
- `test_load_experience_yaml_returns_typed_runtime_object`: validates typed parsing and helper methods.
- `test_load_experience_yaml_rejects_*`: validates strict fields, required location/start, optional end behavior, skill category shape, schema version, and duplicate ids.
- `test_load_registered_evidence_loads_registered_schemas` and `test_app_startup_loads_resume_evidence`: validate registry/startup integration.
- `test_resume_generation_pipeline_requires_loaded_experience` and `test_resume_generation_pipeline_rejects_invalid_loaded_experience`: validate early pipeline failure before HTTP calls.
- `.venv/bin/python -m pytest tests/test_resume_evidence.py tests/test_resume_generation.py`: 88 passed.

**Impact:**
ResumeCR7 can now load and validate work experience from `user/resume_evidence/experience.yaml` alongside user info, education, skills, and projects. Future resume draft generation can consume experience evidence without inventing a schema at generation time.
