### 2026-07-24 - Phase 1 Package Hygiene

**Agent:** Codex (GPT-5)

**Changes:**
- `pyproject.toml` - Added setuptools package metadata, runtime/dev dependency groups, package data, and `resumecr7-*` console scripts.
- `app/api_launcher.py` - Added the `resumecr7-api` uvicorn launcher with host, port, and reload flags.
- `app/config.py` - Added `RESUMECR7_DATA_DIR` plus derived evidence, generation, artifact, and log paths with legacy override support.
- `app/resume_generation/` - Routed no-argument config, evidence, LaTeX/PDF, manifest, and enrichment defaults through the settings path layer.
- `app/main.py` and `app/logging_config.py` - Added data-root-backed file logging and health path metadata for desktop startup diagnostics.
- `README.md` - Documented editable package install, data-root settings, and the new console commands.
- `tests/` - Added packaging and path-resolution coverage and updated health/logging/generation/evidence tests.

**Rationale:**
ADR 017 Phase 1 requires the backend and frontend to be packageable before installer work begins. The implementation keeps the existing FastAPI and YAML-backed architecture intact while creating stable installed commands and a single data-root settings layer. Existing repo-local defaults remain unchanged for development, and narrower legacy overrides still win when supplied.

**Tests:**
- `test_pyproject_exposes_expected_console_scripts`: validates installed command names and targets.
- `test_settings_data_dir_derives_runtime_paths`: validates `RESUMECR7_DATA_DIR` path derivation.
- `test_settings_preserves_specific_path_overrides`: validates legacy/specific path override precedence.
- `test_generation_default_paths_follow_settings`: validates no-argument generation path resolvers.
- `test_default_evidence_paths_follow_settings`: validates evidence loader defaults use the current settings root.
- `python -m pytest`: 536 passed, 4 skipped.
- `npm run build` in `frontend/`: production Vite build succeeded.

**Impact:**
ResumeCR7 can now be installed as a Python package for backend-side packaging smoke work, launched through stable command names, and pointed at a desktop-safe data root without changing the current local development layout.
