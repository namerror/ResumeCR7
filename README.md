# ResumeCR7 Resume Engine

ResumeCR7 is in a transition from a resume-generation prototype into a FastAPI-backed resume service and local-first resume workbench. The current repo can already run grounded resume generation locally, and the recommended service direction is to keep the FastAPI backend as the integration point for product-facing APIs.

Today the repo ships three capability tracks:

- a FastAPI backend in `app/` with reusable data-processing and generation capabilities
- a grounded evidence engine in `app/resume_evidence/` for strict schemas, deterministic loading, REST CRUD, and local YAML-backed workflows
- a backend-owned resume orchestration pipeline in `app/resume_generation/` that reads `user/resume_generation/` and `user/resume_evidence/`, calls in-process backend services, and assembles resume artifacts

The current `user/` tree is local development data and runtime output. It is useful for prototyping and file-backed operation, but it should be treated as a storage adapter target rather than the final production persistence model.

## Product Direction

The first official app model is a local-first web workbench over the existing FastAPI backend, with desktop packaging as the first distribution target once the workflow is proven.

Planned product shape:

```text
frontend workbench
  -> localhost FastAPI backend
  -> local evidence and generation adapters
  -> structured resume result
  -> local LaTeX/PDF artifacts
```

The initial frontend should live in this monorepo, for example under `frontend/`, so UI work can stay aligned with the still-evolving backend API schemas. The backend remains the source of truth for evidence validation, generation orchestration, artifact rendering, and writes to local storage.

The first app should support editing resume evidence, editing a target job description, generating a targeted resume, reviewing or editing generated resume items, and exporting a PDF. It should preserve the product distinction between user-authored source evidence, generated draft content, and final user edits.

The project is intentionally not starting as a hosted multi-user web service. Remote hosting, auth, database-backed persistence, account-level artifact storage, and background workers remain future work after the local product workflow and storage adapter boundaries are stable. See `docs/decisions/016-local-first-web-workbench-desktop-distribution.md`.

## Vision

The long-term goal is a resume service that assembles targeted (job-specific) resumes from user-authored evidence without inventing claims. The intended pipeline is:

```text
user-authored evidence files
  -> deterministic load/validate/index
  -> grounded synthesis/extraction
  -> deterministic assembly
  -> generated resume artifact
```

Job descriptions can influence prioritization, but they are not evidence. Supported claims must trace back to user-authored source files.

## Implemented Today

### Skill selection API

The current public API is a FastAPI service for ranking user-provided skills by category for a target role.

- `POST /select-skills`
  - deterministic `baseline` method
  - `embeddings` method with cached OpenAI embeddings
  - `llm` method with local validation and deterministic ranking
  - optional `baseline_filter` that lets deterministic matches bypass model-backed scoring
  - required fallback to baseline behavior when model-backed methods fail
- `GET /health`
  - reports service liveness and effective config
- `GET /metrics-lite`
  - reports request totals, error totals, average latency, total model tokens, and effective method usage

Skill selection remains constrained by the repo invariants:

- outputs must stay within the user-provided skill set
- category boundaries remain `technology`, `programming`, and `concepts`
- deterministic ordering is required
- baseline must remain functional even if embeddings or LLM methods fail

### Grounded resume evidence foundation

The first implemented milestone is the app-owned resume evidence package with legacy CLI compatibility.

- `app/resume_evidence/models.py`
  - strict Pydantic models for all registered evidence YAML schemas
- `app/resume_evidence/loader.py`
  - schema registry and deterministic YAML loading from `RESUME_EVIDENCE_ROOT`
- `app/resume_evidence/session.py`
  - staged in-memory CRUD with validation-before-mutation and atomic apply-to-disk writes
- `app/resume_evidence/service.py`
  - ID-oriented backend helpers over the session layer
- `app/resume_evidence/api.py`
  - REST CRUD routes under `/resume-evidence`
- `resume_evidence/cli/`
  - CLI entrypoint and schema dispatcher
- `resume_evidence/cli/base.py`
  - shared interactive CLI base helpers
- `resume_evidence/cli/{projects,skills,education,experience,user}.py`
  - schema-specific command implementations
- `app/resume_generation/`
  - evidence-to-selection orchestration, batch link enrichment, bullet-point generation, intermediate result assembly, LaTeX/PDF artifact rendering, and `/resume-generation` facade routes
- `resume_generation/`
  - compatibility shims for legacy imports and `python -m resume_generation.*` entrypoints
- `app/main.py`
  - loads registered evidence on startup into `app.state.resume_evidence`

The currently implemented evidence schemas are:

- `user/resume_evidence/projects.yaml`
  - `schema_version: 1`
  - strict project records with `id`, `name`, `summary`, `highlights`, `active`, `skills`, and optional `links`
- `user/resume_evidence/skills.yaml`
  - `schema_version: 1`
  - strict categorized skill lists under `technology`, `programming`, and `concepts`
- `user/resume_evidence/education.yaml`
  - `schema_version: 1`
  - strict education records with `id`, `name`, `degree`, `grade`, `start`, optional `end`, `location`, and `relevant_coursework`
- `user/resume_evidence/experience.yaml`
  - `schema_version: 1`
  - strict experience records with `id`, `name`, `role`, `summary`, `highlights`, `active`, `skills`, `location`, `start`, optional `end`, and optional `links`
- `user/resume_evidence/user.yaml`
  - `schema_version: 1`
  - strict basic contact info with required `name`, `email`, and `phone`, plus optional `linkedin`, `github`, and `website`

Resume evidence can be managed through `/resume-evidence` REST routes, the legacy CLI, or other tools that write to the configured evidence root.

Evidence REST routes:

- `GET /resume-evidence`
- `GET /resume-evidence/{projects|experience|education|skills|user}`
- `POST /resume-evidence/{projects|experience|education}`
- `GET /resume-evidence/{projects|experience|education}/{id}`
- `PUT /resume-evidence/{projects|experience|education}/{id}`
- `DELETE /resume-evidence/{projects|experience|education}/{id}`
- `PUT /resume-evidence/{skills|user}`

### Project selection API

The project-selection subsystem ranks explicit project candidates for a job target without generating resume prose.

- `POST /select-projects`
  - accepts `context` with job title/description and explicit project `candidates`
  - supports deterministic `baseline` and model-backed `llm` methods
  - validates LLM project-id scores locally and falls back to baseline when needed
  - returns project IDs and scores, not project summaries, highlights, links, or generated claims

### Evidence CLI workflow

Use the CLI to manage staged edits to evidence YAML without hand-editing:

```bash
PYTHONPATH=. python -m resume_evidence.cli
```

Default `projects` commands:

- `list`
- `show <index>`
- `create`
- `edit <index>`
- `delete <index>`
- `apply`
- `reload`
- `quit`

The default schema is `projects`. Use `--schema` to manage any registered evidence file:

```bash
PYTHONPATH=. python -m resume_evidence.cli --schema skills
PYTHONPATH=. python -m resume_evidence.cli --schema education
PYTHONPATH=. python -m resume_evidence.cli --schema experience
PYTHONPATH=. python -m resume_evidence.cli --schema user
```

Projects, education, and experience support list/show/create/edit/delete/apply/reload/quit workflows. Skills and user info support list/show-style inspection, edit, apply, reload, and quit.

The CLI keeps edits staged in memory until `apply` is confirmed, preserves stable hidden IDs for projects and experience entries, and writes atomically to disk.

### Evaluation and support scripts

The repo also includes utilities for skill-selection evaluation and data preparation:

- `scripts/build_skill_pools.py`
  - builds normalized skill pools
- `scripts/eval_cases_generator.py`
  - generates evaluation datasets
- `scripts/eval.py`
  - runs skill-selection evaluation against case files

See [scripts/README.md](/scripts/README.md) for command details.

## How The Pieces Fit Together

ResumeCR7 now has a broader resume-engine shape:

- the FastAPI `app/` layer provides reusable backend capabilities for selection, focus derivation, bullet generation, enrichment, metrics, and health checks
- the skills API helps prioritize and rank skills for the Skills section
- the project-selection API helps prioritize grounded projects for a target job
- the app-owned resume-evidence package exposes grounded source-of-truth data from `user/resume_evidence/`
- the `app/resume_generation/` layer combines target job context, evidence, and selected service outputs into an intermediate resume result
- deterministic assembly and LaTeX rendering turn that structured result into resume artifacts without inventing claims

Skill selection is no longer the whole project. It is one subsystem inside the larger grounded resume pipeline.

## Recommended Service Architecture

The FastAPI backend now has a synchronous v1 resume-generation facade while keeping the existing stage endpoints as internal backend capabilities.

For the first app, the backend should run locally on loopback and serve as the local product API for a web frontend or packaged desktop shell. A hosted backend is deferred until auth, persistence, artifact storage, and generation-run infrastructure are justified.

### Product-facing facade

Product clients should call higher-level resume service APIs, not orchestrate every generation stage themselves. The current facade owns evidence CRUD and synchronous generation actions:

- `POST /resume-generation/enrich-link-evidence`
- `POST /resume-generation/tex`
- `POST /resume-generation/pdf`

The next facade step is an async run lifecycle for long-running product workflows:

- generation-run creation with a job target and selected evidence scope
- generation-run status and artifact retrieval
- structured resume result retrieval for web-app editing or rendering

The current stage APIs remain valuable, but they are better treated as internal capabilities that the facade calls.

### Internal capability APIs

The existing FastAPI routes are useful backend building blocks:

- `/select-skills`
- `/select-projects`
- `/derive-job-focus`
- `/generate-bulletpoints`
- `/enrich-link-evidence`

As the service boundary matures, these routes should either move behind an internal namespace or be documented separately from the product API. That keeps the future web app from depending on orchestration details such as cache keys, prompt-specific payloads, or per-stage retry behavior.

### Storage transition

Keep the current YAML-backed `user/resume_evidence/` and `user/resume_generation/` layout for local development and prototype runs. The next implementation step should introduce repository/adapter interfaces around evidence, generation runs, cache entries, and artifacts. The first adapter can continue to read and write files; a database-backed adapter can follow when service requirements are clearer.

This avoids an early database dependency while preventing file paths from leaking into the final API design.

### Generation run model

Full resume generation should be exposed as an async run:

```text
POST create generation run
  -> return run_id
GET run status
  -> queued | running | succeeded | failed
GET run result/artifacts
  -> structured result, manifest, rendered output
```

The current local CLI-style pipeline can remain synchronous internally, but the product API should not require a web client to hold a request open across multiple LLM-backed stages.

## Resume Generation Usage

Resume generation is implemented in `app/resume_generation/`, with top-level `resume_generation` compatibility entrypoints. It reads generation settings, the target job, and all registered evidence files, then calls in-process backend services for selection, job focus derivation, and bullet generation. Link scanning is exposed as a standalone evidence-enrichment capability rather than part of the normal generation pipeline.

Then run the generation pipeline from the repo root:

```bash
PYTHONPATH=. python -m resume_generation.main
```

The direct module entrypoint writes:

- `user/resume_generation/artifacts/resume_result.json` - intermediate structured resume data
- `user/resume_generation/artifacts/resume_run_manifest.json` - generation inputs, stage metadata, and token usage
- `user/resume_generation/artifacts/resume.tex` - LaTeX resume output, unless `resume_output.path` overrides it
- `user/resume_generation/artifacts/resume.pdf` - optional rendered PDF when `resume_output.render_pdf: true`

To render an existing `.tex` file without rerunning the full pipeline:

```bash
PYTHONPATH=. python -m resume_generation.pdf
```

The PDF renderer uses local `latexmk`, so the runtime environment needs TeX Live plus `latexmk` installed when `resume_output.render_pdf: true`.

`user/resume_generation/config.yaml` controls generation:

- `app` - compatibility base URL and request timeout for older HTTP-style orchestration tests
- `skill_selection` - method, `top_n`, baseline-filter toggle, debug mode, and LLM overrides for skill selection
- `project_selection` - method, `top_n`, debug mode, and LLM overrides for project selection; `top_n: null` omits the request override and lets the app's `PROJ_TOP_N` default decide the limit
- `job_focus_generation` - LLM overrides for one job-focus derivation per target role
- `link_scanning` - standalone enrichment settings used by the link enrichment runner
- `project_bullet_point_generation` - bullet count range, debug mode, and LLM overrides for selected projects
- `experience_bullet_point_generation` - bullet count range, debug mode, and LLM overrides for active experience records
- `cache` - stage cache toggle, path override, and force-refresh behavior
- `resume_output` - optional `.tex` output path plus opt-in PDF rendering settings

`user/resume_generation/job_target.yaml` supplies the target role:

- `schema_version: 1`
- `title` - required job title
- `description` - optional job description text used for selection and bullet generation context

The pipeline loads every registered resume-evidence schema from `user/resume_evidence/`:

- `user.yaml` - contact/header data for the resume top section
- `education.yaml` - education entries and relevant coursework
- `experience.yaml` - active work experience entries and evidence for experience bullets
- `projects.yaml` - active project candidates, highlights, skills, and optional links
- `skills.yaml` - categorized skills available for the Skills section

Only `active: true` projects are sent to project selection, and only selected projects are sent to project bullet generation. Only `active: true` experience entries are assembled into the final experience section.

## API

### Resume generation facade

- `POST /resume-generation/enrich-link-evidence`
  - scans project and/or experience links in batch
  - appends unique new highlights to YAML evidence unless `dry_run: true`
  - returns per-record scan results, skipped reasons, and updated evidence paths
- `POST /resume-generation/tex`
  - runs the full configured resume pipeline
  - writes the structured result, run manifest, and `.tex` artifact
  - returns the structured result plus `.tex` path and content
- `POST /resume-generation/pdf`
  - renders the configured/default `.tex` artifact with local `latexmk`
  - writes the configured/default PDF artifact
  - returns `application/pdf` bytes

### Health

`GET /health`

Example response:

```json
{
  "status": "ok",
  "version": "0.3.0",
  "service": "resumecr7-resume-engine",
  "dev_mode": true,
  "skill_selection": {
    "method": "baseline",
    "top_n": 10,
    "baseline_filter": false,
    "llm_model": "gpt-5-mini",
    "llm_max_output_tokens": 1200
  },
  "project_selection": {
    "method": "llm",
    "top_n": null,
    "llm_model": "gpt-5-mini",
    "llm_max_output_tokens": 1200
  },
  "link_scanning": {
    "enabled": false,
    "llm_model": "gpt-5-mini",
    "llm_max_output_tokens": 1200
  }
}
```

### Select Skills

`POST /select-skills`

Example request:

```json
{
  "job_role": "AI/ML Engineer",
  "job_text": "Optional job description text",
  "technology": ["Docker", "Kubernetes", "AWS", "PostgreSQL", "TensorFlow"],
  "programming": ["Python", "TypeScript", "SQL"],
  "concepts": ["Machine Learning", "CI/CD", "Distributed Systems"],
  "top_n": 5,
  "method": "embeddings",
  "baseline_filter": true,
  "dev_mode": true
}
```

Example response:

```json
{
  "technology": ["TensorFlow", "AWS", "Docker"],
  "programming": ["Python"],
  "concepts": ["Machine Learning", "Distributed Systems"],
  "details": {}
}
```

### Select Projects

`POST /select-projects`

Example request:

```json
{
  "context": {
    "title": "Backend Engineer",
    "description": "Build Python APIs with Django and PostgreSQL."
  },
  "candidates": [
    {
      "id": "resumecr7",
      "name": "ResumeCR7",
      "summary": "Resume engine with deterministic selection and grounded evidence.",
      "skills": {
        "technology": ["Django", "PostgreSQL"],
        "programming": ["Python"],
        "concepts": ["API"]
      }
    }
  ],
  "method": "baseline",
  "top_n": 1,
  "dev_mode": true
}
```

Example response:

```json
{
  "selected_project_ids": ["resumecr7"],
  "ranked_projects": [
    {
      "project_id": "resumecr7",
      "score": 0.75,
      "method": "baseline"
    }
  ],
  "details": {}
}
```

### Metrics

`GET /metrics-lite`

Example response:

```json
{
  "requests_total": 42,
  "errors_total": 1,
  "total_tokens": 12000,
  "avg_latency_ms": 25.3,
  "method_usage": {
    "baseline": 30,
    "embeddings": 8,
    "llm": 4
  },
  "subsystems": {
    "skill_selection": {
      "requests_total": 38,
      "errors_total": 1,
      "total_tokens": 9000,
      "avg_latency_ms": 22.1,
      "method_usage": {
        "baseline": 30,
        "embeddings": 8
      }
    },
    "project_selection": {
      "requests_total": 4,
      "errors_total": 0,
      "total_tokens": 3000,
      "avg_latency_ms": 55.7,
      "method_usage": {
        "llm": 4
      }
    }
  }
}
```

`method_usage` reflects the method that actually produced the response. If a model-backed method falls back to baseline, the request is counted under `baseline`. The top-level metrics remain aggregate; `subsystems` breaks out skill selection and project selection.

## Configuration

ResumeCR7 reads settings from environment variables via `app/config.py`.

```bash
RESUMECR7_DATA_DIR=user # root for evidence, generation config/artifacts, and logs
RESUMECR7_PACKAGED=false # use OS app-data defaults when true and DATA_DIR is unset
# RESUME_EVIDENCE_ROOT=user/resume_evidence # optional legacy evidence-root override
# RESUME_GENERATION_ROOT=user/resume_generation # optional generation-root override
# RESUMECR7_LOG_DIR=user/logs # optional log directory override

SKILL_METHOD=baseline # available options: baseline, embeddings, llm
SKILL_TOP_N=10 # how many top-ranked skills to return per category
SKILL_BASELINE_FILTER=false # if true, deterministic skill matches bypass model-backed scoring

PROJ_METHOD=llm # available options: baseline, llm
# PROJ_TOP_N=2 # optional; omit to return all ranked projects unless the request overrides it

DEV_MODE=true # return debugging info
LOG_LEVEL=INFO

OPENAI_API_KEY=your_key_here

EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=100

SKILL_LLM_MODEL=gpt-5-mini
SKILL_LLM_MAX_OUTPUT_TOKENS=1200
PROJ_LLM_MODEL=gpt-5-mini
PROJ_LLM_MAX_OUTPUT_TOKENS=1200
LINK_SCANNING_ENABLED=false
LINK_SCANNING_LLM_MODEL=gpt-5-mini
LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS=1200
```

When `RESUMECR7_PACKAGED=true` and `RESUMECR7_DATA_DIR` is not set,
ResumeCR7 resolves the data root from the OS app-data location:
`$XDG_DATA_HOME/resumecr7` or `~/.local/share/resumecr7` on Linux,
`~/Library/Application Support/ResumeCR7` on macOS, and
`%LOCALAPPDATA%\ResumeCR7` on Windows. Startup bootstraps missing evidence and
generation YAML files with schema-valid placeholder defaults, creates
`resume_generation/artifacts/`, and never overwrites existing runtime files.

`OPENAI_API_KEY` is only required for skill-selection `embeddings`, skill-selection `llm`, project-selection `llm`, bullet-point generation, and enabled link-scanning requests.
Link scanning treats normal URLs as single-page sources; `github.com/{owner}/{repo}` links allow repository-scoped exploration for technical project evidence.
Legacy generic selection variables such as `METHOD`, `TOP_N`, `BASELINE_FILTER`, `LLM_MODEL`, and `LLM_MAX_OUTPUT_TOKENS` are no longer read.
Baseline filtering is skill-selection-only; project selection does not define a baseline pre-filter pass yet.

## Running Locally

Install dependencies:

```bash
uv sync --extra dev
```

Start the FastAPI app:

```bash
uv run resumecr7-api --reload
```

Run the evidence CLI:

```bash
uv run resumecr7-resume-evidence
```

Run a specific evidence schema CLI:

```bash
uv run resumecr7-resume-evidence --schema skills
uv run resumecr7-resume-evidence --schema education
uv run resumecr7-resume-evidence --schema experience
uv run resumecr7-resume-evidence --schema user
```

Run resume generation after the app is running:

```bash
uv run resumecr7-resume-generation
```

After `uv sync --extra dev`, the installed `resumecr7-*` commands can also be run
directly from the active virtual environment. The legacy
`uvicorn app.main:app --reload`, `PYTHONPATH=. python -m resume_evidence.cli`, and
`PYTHONPATH=. python -m resume_generation.main` commands remain supported for local
development.

## Tests

Tests assume the repo root is on `PYTHONPATH`:

```bash
uv run pytest
```

Useful targeted runs:

```bash
uv run pytest tests/test_resume_evidence.py
uv run pytest tests/test_resume_evidence_cli.py
uv run pytest tests/test_integration.py
```

## Planned Next

The next backend transition should focus on service integration rather than adding unrelated generation features:

- add repository/adapter boundaries around evidence files, generation runs, cache entries, and artifacts
- add async resume-generation run creation/status/result endpoints on top of the synchronous v1 facade
- keep the current stage endpoints available as internal capabilities for the facade and tests
- defer database persistence until the adapter contract and product API shape are stable
- expand output formats only after the structured result and run lifecycle are service-ready

See:

- [docs/architecture-overview.md](/home/leon/Documents/proj/ResumeCR7/docs/architecture-overview.md)
- [docs/decisions/003-grounded-resume-evidence-pipeline.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/003-grounded-resume-evidence-pipeline.md)
- [docs/decisions/004-user-resume-evidence-root-and-projects-milestone.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/004-user-resume-evidence-root-and-projects-milestone.md)
- [docs/decisions/005-subsystem-package-organization.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/005-subsystem-package-organization.md)
- [docs/decisions/008-standalone-resume-evidence-and-generation-layers.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/008-standalone-resume-evidence-and-generation-layers.md)
- [docs/decisions/012-fastapi-resume-service-transition.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/012-fastapi-resume-service-transition.md)
- [docs/decisions/015-app-owned-resume-generation-api.md](/home/leon/Documents/proj/ResumeCR7/docs/decisions/015-app-owned-resume-generation-api.md)

## Current Limitations

- Full resume generation is synchronous in v1; async run lifecycle endpoints are still future work.
- The current output path is structured JSON plus LaTeX; additional export formats are still future work.
