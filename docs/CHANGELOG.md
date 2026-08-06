# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
