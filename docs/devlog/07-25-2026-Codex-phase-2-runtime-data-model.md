### 2026-07-25 - Phase 2 runtime data model

**Agent:** Codex (GPT-5)

**Changes:**
- `app/data_paths.py:13-40` - Added OS-specific default app-data resolution for packaged runs.
- `app/config.py:29-99` - Added `RESUMECR7_PACKAGED`, deferred default data-root resolution, and moved generated artifacts under `resume_generation/artifacts/`.
- `app/runtime_data.py:30-141` - Added first-launch runtime directory and YAML bootstrap with schema validation and atomic writes.
- `app/main.py:42-52`, `app/resume_generation/main.py:421-433`, and `resume_evidence/cli/__init__.py:49-56` - Wired bootstrap into backend startup and default local entrypoints.
- `.gitignore` - Ignored generated runtime artifacts under `user/resume_generation/artifacts/`.
- `tests/test_config.py` and `tests/test_runtime_data.py` - Added coverage for packaged data-root resolution, artifact paths, schema-valid defaults, and non-overwrite bootstrap behavior.
- `README.md:261-266` and `docs/architecture-overview.md:132-146` - Documented the artifact layout and startup bootstrap flow.

**Rationale:**
ADR 017 phase 2 requires packaged-app writes to stay out of the repo and installed bundle. The implementation keeps local development on the existing `user/` root by default, adds an explicit packaged-mode switch for OS app-data locations, and initializes fresh runtime roots with placeholders instead of copying personal resume data.

**Tests:**
- `test_settings_packaged_mode_uses_os_data_dir`: validates packaged Linux app-data resolution through `XDG_DATA_HOME`.
- `test_settings_data_dir_override_wins_in_packaged_mode`: verifies explicit `RESUMECR7_DATA_DIR` takes precedence.
- `test_bootstrap_runtime_data_writes_schema_valid_defaults`: validates bootstrapped evidence/config/job files through existing schemas.
- `test_bootstrap_runtime_data_does_not_overwrite_existing_files`: confirms first-launch bootstrap preserves user-authored YAML.
- `PYTHONPATH=. pytest tests/test_config.py tests/test_runtime_data.py tests/test_health.py tests/test_resume_evidence.py tests/test_resume_generation.py -q`
- `PYTHONPATH=. pytest tests/test_packaging.py tests/test_resume_evidence_cli.py -q`

**Impact:**
ResumeCR7 now has a desktop-safe runtime data model for evidence, generation config, generated artifacts, and logs. Fresh packaged data roots can start without repository files, while existing file-backed persistence and schema validation remain unchanged.
