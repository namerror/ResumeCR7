# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Frontend Config page and `/resume-generation/config` API for editing selected local generation settings, including masked YAML-backed OpenAI API key setup.
- Updated token budgeting logic with dynamic settings. Project selection and bullet generation now scale output budgets with request size by default, preserve explicit override controls, and expose resolved budget metadata in logs, stage records, and dev details for easier diagnosis.

## [0.4.0] - 2026-07-26

### Added
- Tauri desktop shell support with a PyInstaller-built FastAPI sidecar, runtime backend URL discovery, app-data logs, and AppImage build output.
- User/developer README guide covering desktop usage, local setup, repository structure, runtime data, exposed endpoints, configuration, tests, and current development rules.
- Frontend resume generation controls for request-scoped job targets, `.tex` generation, PDF download, and per-project/per-experience link enrichment.
- Local-first React/Vite resume evidence workbench that stages edits in browser state and applies them through the existing `/resume-evidence` FastAPI CRUD endpoints.

### Fixed
- Direct AppImage launches now resolve the Tauri-managed sidecar URL instead of falling back to the browser `/api` proxy and reporting the backend as offline.

## [0.3.0] - 2026-07-23

### Added
- `/resume-generation` REST facade for batch link enrichment, full `.tex` resume generation, and PDF rendering from the configured local resume artifacts.
- `/resume-evidence` REST CRUD API for file-backed resume evidence, with ID-based project, experience, and education routes plus singleton user and skills updates.
- Optional LaTeX PDF rendering through local `latexmk` via `python -m resume_generation.pdf` or `resume_output.render_pdf`.
- `POST /derive-job-focus` API and resume-generation job-focus stage that distills long job descriptions into compact resume-relevant context before bullet generation.
- LaTeX resume output generation from `resume_generation` runtime resume results, using the configured `resume_output.path` with a default `.tex` artifact path.
- Standalone link evidence enrichment through `POST /enrich-link-evidence` and `python -m resume_generation.enrich`, with project and experience support, configurable requested highlight count, and dynamic scanner output-token budgeting.
- LLM-backed link scanning that uses OpenAI web search to collect grounded evidence highlights from configured links, with GitHub repository exploration constrained to the linked repo.
- `POST /generate-bulletpoints` API for OpenAI-backed, grounded project bullet-point generation from a job target and `ProjectRecord`.
- `resume_generation` orchestration that loads resume evidence, reads `user/resume_generation` YAML config, and calls selection plus bullet-point generation APIs over HTTP.
- Modern project and highlight picker support, including a command-complete action menu, in the resume evidence CLI.
- Project-style action menus and indexed highlight editing for the experience evidence CLI.
- `user/resume_evidence/skills.yaml` evidence support with strict loading, startup registration, and staged CLI editing via `python -m resume_evidence.cli --schema skills`
- Staged resume evidence CLI workflows for `education`, `experience`, and `user` schemas via `python -m resume_evidence.cli --schema <schema>`.

### Changed
- Resume generation domain code now lives under `app/resume_generation`; top-level `resume_generation` modules remain compatibility shims for legacy imports and local module entrypoints.
- Resume generation orchestration now calls in-process backend services by default instead of calling the FastAPI app over loopback HTTP.
- Resume evidence domain code now lives under `app/resume_evidence`; top-level `resume_evidence` modules remain compatibility shims for legacy imports and CLI usage.
- Resume-generation bullet requests now use derived `job_focus` context from the pipeline instead of repeating the full job description for every selected project and active experience.
- Resume generation no longer runs link scanning or web search in the normal pipeline; it consumes already-enriched evidence for selection and bullet generation.
- Resume evidence CLI components now live under the standalone `resume_evidence/cli/` package.
- Runtime selection configuration is now subsystem-scoped: use `SKILL_METHOD`, `SKILL_TOP_N`, `SKILL_BASELINE_FILTER`, `PROJ_METHOD`, and `PROJ_TOP_N` instead of generic selection env vars.
- Skill-selection and project-selection LLM defaults are configured separately with `SKILL_LLM_*` and `PROJ_LLM_*` settings; legacy `LLM_MODEL` and `LLM_MAX_OUTPUT_TOKENS` are no longer read.
- `/health` now reports scoped `skill_selection` and `project_selection` config blocks instead of top-level generic selection keys.

## [0.2.0] - 2026-04-27

### Added
- `POST /select-projects` project-selection API with baseline/LLM methods, local validation, baseline fallback, and project-selection metrics
- `app/skill_selection/` subsystem package for skill-selection models, scoring, clients, data, and compatibility shims for legacy import paths
- Interactive projects evidence CLI with staged in-memory CRUD, hidden auto-generated IDs, and explicit `apply` confirmation before writing `user/resume_evidence/projects.yaml`
- Optional `baseline_filter` request/config flag that pre-filters deterministic baseline matches before embeddings or LLM scoring, with full-baseline fallback behavior
- `/metrics-lite` now reports cumulative model token usage and counts fallback responses under the effective baseline method
- LLM skill-selection method (`method="llm"`) with OpenAI Responses API scoring, strict local validation, deterministic ranking, dev metadata, and baseline fallback
- Embeddings scorer (`embedding_select_skills`) in `app/skill_selection/scoring/embeddings.py` with per-category cosine similarity ranking, stable tie-breaking, dev mode similarity scores, short role text warnings, and rate limit error handling
- Role family detection and inheritance in baseline scorer
- Baseline scoring algorithm with role-specific boosts
- Skill selection service with latency tracking and structured logging
- `include_zero` option in skill ranking to include irrelevant skills for evaluation purposes, defaulting to False

### Fixed
- Empty string handling in baseline scorer to prevent false partial matches
- TOP_N environment variable type conversion (string to int)
- Attribute name mismatch in `baseline_select_skills()` (job_role vs role)
- Embedding truncation logging now uses standard logging extras
- `embed_role` honors `EMBEDDING_DIMENSIONS` for consistent embedding sizes
- `embed_skills` now validates against empty input batches

## [0.1.0] - Initial Setup

### Added
- Basic FastAPI application structure
- Baseline scoring algorithm with synonym normalization
- Role profile definitions for multiple engineering roles
- Health check endpoint
- Select skills endpoint (placeholder implementation)
