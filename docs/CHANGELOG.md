# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-08-09

### Added
- Configurable bullet generation strategy with whole-section batch generation
  as the default and per-entry generation available as a compatibility mode.
- Configurable concurrent bullet-point LLM requests for faster resume generation.
- Configurable Qwen LLM provider support with Config UI controls for selecting
  OpenAI or Qwen and managing both provider API keys.
- Improvement on generation speed by fully parallelizing LLM requests for skill selection, project selection etc.

### Fixed
- Fixed skill selection and project selection failure due to max output token limit exceeded for LLM requests.
- Recognize multiple month date formats to avoid incorrect ranking of experience entries.

## [0.1.3] - 2026-08-07

### Added
- Main Skills page categories render alphabetically.
- + inserts the new empty skill input at the top and focuses it.
- New/edited skills are placed alphabetically after focus leaves the category.
- Main Skills saves use alphabetized category arrays.
- Duplicate main skill names are blocked case-insensitively across categories.


## [0.1.2] - 2026-08-07

### Added
- Configurable user-facing resume output directory for generated `.tex` and `.pdf`
  copies, separate from internal generation artifacts.

### Fixed
- Descending order of experience entries by latest end date, secondarily by earliest start date.
- Improved prompt quality for bullet generation, including stricter requirements for bullet length, action verbs, and avoidance of unstructured bullet lists and unclear project purposes or redundant technical details.
- Improved resume layout formatting by moving the job position next to the company name in "Experience" entries, leaving space for the long skill lists in the second row.

## [0.1.1] - 2026-08-06

### Added
- Support authenticated GitHub repository context for link evidence enrichment,
  including private repositories accessible through a read-only GitHub token.

### Fixed
- Support proxy settings that require SOCKS when sending requests to OpenAI endpoints 

## [0.1.0] - 2026-07-28

### Added
- Local resume evidence workbench for contact info, skills, projects,
  experience, and education.
- YAML-backed local runtime data with schema validation, bootstrap defaults, and
  atomic writes.
- FastAPI backend with resume evidence CRUD, generation configuration, health,
  metrics, and resume generation routes.
- Tailored LaTeX resume generation from user-authored evidence and a target job.
- Optional local PDF rendering through `latexmk` and a TeX installation.
- Ubuntu/Debian PDF dependency installer and checker for Linux AppImage users.
- Optional OpenAI-backed skill selection, project selection, job-focus
  derivation, bullet generation, and link evidence enrichment, with
  deterministic baseline paths kept available.
- React/Vite workbench for editing evidence, staging changes, configuring
  generation, enriching linked evidence, generating `.tex`, and downloading
  PDFs.
- Linux AppImage desktop preview using Tauri v2 and a packaged FastAPI sidecar.
