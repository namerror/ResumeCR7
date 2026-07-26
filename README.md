# ResumeCR7

ResumeCR7 is a local-first resume workbench and FastAPI resume engine. It helps
maintain grounded resume evidence, select relevant skills and projects for a
target role, generate `.tex` resume output, and render a PDF without inventing
claims outside the user-authored evidence.

The current product shape is:

```text
Tauri desktop app or Vite web workbench
  -> local FastAPI backend
  -> YAML-backed evidence and generation config
  -> structured resume result
  -> local LaTeX/PDF artifacts
```

ResumeCR7 is intentionally local-first today. Hosted multi-user auth,
database-backed persistence, background queues, signing, and auto-update are
future work after the local workflow and adapter boundaries are stable.

## Features

- Desktop app shell with Tauri v2, bundled React/Vite frontend, and a
  PyInstaller-built FastAPI sidecar.
- Local web workbench for editing resume evidence, staging changes, generating
  `.tex`, downloading PDFs, and enriching project/experience links.
- File-backed evidence CRUD for user info, skills, projects, experience, and
  education.
- Grounded resume-generation facade under `/resume-generation`.
- Deterministic baseline skill and project selection, with optional LLM-backed
  selection and baseline fallback behavior.
- Local schema validation, first-launch runtime data bootstrap, atomic YAML
  writes, and structured runtime logs.

## Quick Start

### Desktop App

Build and run the desktop app from the frontend directory:

```bash
cd frontend
npm install
npm run desktop:build
./src-tauri/target/release/bundle/appimage/ResumeCR7_0.4.1_amd64.AppImage
```

During desktop startup, Tauri starts the bundled backend sidecar on an available
`127.0.0.1` port, waits for `/health`, then gives the frontend the backend URL.
Packaged runtime data is stored under the OS app-data directory, for example
`~/.local/share/com.resumecr7.desktop/` for the current Linux AppImage.

On Ubuntu, Tauri builds require native WebView/GTK dependencies:

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  pkg-config \
  libwebkit2gtk-4.1-dev \
  libgtk-3-dev \
  libayatana-appindicator3-dev \
  librsvg2-dev
```

### Local Web + Backend

Install backend and frontend dependencies:

```bash
uv sync --extra dev
cd frontend
npm install
```

Run the backend in one terminal:

```bash
uv run resumecr7-api --reload
```

Run the Vite workbench in another:

```bash
cd frontend
npm run dev
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8000` by default.
Set `VITE_BACKEND_PROXY_TARGET` to point at another local backend.

## Repository Structure

```text
app/
  main.py                    FastAPI app composition and public routes
  config.py                  environment-driven runtime settings
  data_paths.py              OS app-data resolution
  runtime_data.py            first-launch data bootstrap
  resume_evidence/           evidence schemas, loaders, services, REST API
  resume_generation/         generation orchestration and facade API
  skill_selection/           skill scoring and selection service
  project_selection/         project ranking service
  job_focus_generation/      job-focus derivation capability
  bulletpoints_generation/   grounded bullet generation capability
  link_scanning/             link enrichment capability

frontend/
  src/                       React/Vite workbench
  src-tauri/                 Tauri v2 desktop shell and sidecar lifecycle

resume_evidence/
resume_generation/           legacy compatibility shims and CLI entrypoints

user/
  resume_evidence/           local development evidence YAML
  resume_generation/         local generation config and artifacts

docs/
  decisions/                 ADRs
  devlog/                    agent session logs
  architecture-overview.md   subsystem map and runtime flows
```

Start new architecture work by reading [docs/agent-context-index.md](docs/agent-context-index.md)
and [docs/architecture-overview.md](docs/architecture-overview.md).

## Runtime Data

ResumeCR7 stores user-authored evidence, generation config, generated `.tex`,
generated `.pdf`, and logs under `RESUMECR7_DATA_DIR`. The location depends on
how the app is launched.

Local web/backend development defaults to the repository `user/` directory:

```text
user/
```

That means local development evidence files live in `user/resume_evidence/`,
and generated artifacts live in `user/resume_generation/artifacts/`.

Packaged desktop runs through Tauri. Tauri resolves the OS app-data directory
with the bundle identifier `com.resumecr7.desktop`, then passes that directory
to the packaged FastAPI sidecar as `RESUMECR7_DATA_DIR`. Typical default
locations are:

```text
Linux:   $XDG_DATA_HOME/com.resumecr7.desktop
         or ~/.local/share/com.resumecr7.desktop
macOS:   ~/Library/Application Support/com.resumecr7.desktop
Windows: %APPDATA%\com.resumecr7.desktop
```

For the current Linux AppImage, the default is usually:

```text
~/.local/share/com.resumecr7.desktop/
```

### In short

An explicit `RESUMECR7_DATA_DIR` environment variable still overrides the local
development default for non-desktop backend launches. In the Tauri desktop app,
the Rust shell explicitly supplies the Tauri app-data directory to the sidecar.

Local development defaults to `RESUMECR7_DATA_DIR=user`. Packaged desktop runs
set `RESUMECR7_PACKAGED=true` and use an OS app-data root unless
`RESUMECR7_DATA_DIR` is explicitly supplied.

The runtime layout is:

```text
RESUMECR7_DATA_DIR/
  resume_evidence/
    user.yaml
    skills.yaml
    projects.yaml
    education.yaml
    experience.yaml
  resume_generation/
    config.yaml
    job_target.yaml
    artifacts/
      resume_result.json
      resume_run_manifest.json
      resume.tex
      resume.pdf
  logs/
    resumecr7.log
    desktop-sidecar.log
```

Startup creates missing directories and schema-valid placeholder YAML files. It
does not overwrite existing user-authored runtime files.

To retrieve or back up your data, copy these paths from the active
`RESUMECR7_DATA_DIR`:

- Evidence YAML files: `resume_evidence/user.yaml`,
  `resume_evidence/skills.yaml`, `resume_evidence/projects.yaml`,
  `resume_evidence/education.yaml`, and `resume_evidence/experience.yaml`.
- Generated LaTeX file: `resume_generation/artifacts/resume.tex`.
- Generated PDF file: `resume_generation/artifacts/resume.pdf`.
- Runtime logs: `logs/resumecr7.log` and, for desktop launches,
  `logs/desktop-sidecar.log`.

## Evidence Model

Resume evidence is the source of truth. Job descriptions can influence
selection and phrasing, but they are not evidence.

Implemented evidence files:

- `user.yaml` - contact/header fields: `name`, `email`, `phone`, optional
  `linkedin`, `github`, `website`.
- `skills.yaml` - categorized skill lists under `technology`, `programming`,
  and `concepts`.
- `projects.yaml` - project records with `id`, `name`, `summary`,
  `highlights`, `active`, categorized `skills`, and optional `links`.
- `experience.yaml` - experience records with `id`, `name`, `role`,
  `summary`, `highlights`, `active`, categorized `skills`, `location`,
  `start`, optional `end`, and optional `links`.
- `education.yaml` - education records with `id`, `name`, `degree`, `grade`,
  `start`, optional `end`, `location`, and `relevant_coursework`.

The workbench stages edits in browser state. The backend applies writes through
validated REST endpoints and atomic YAML replacement.

## Resume Generation

Resume generation lives under `app/resume_generation/` and is exposed through
the `/resume-generation` facade.

The pipeline:

1. Loads `resume_generation/config.yaml` and `job_target.yaml`.
2. Loads and validates all registered resume-evidence YAML files.
3. Selects relevant skills and active projects.
4. Derives compact job focus for the target role.
5. Generates grounded project and active-experience bullets.
6. Assembles an intermediate structured resume result.
7. Writes JSON manifest/result and `.tex`; PDF rendering is optional.

Generated artifacts are derived runtime state, not source evidence.

Run the local generation command:

```bash
uv run resumecr7-resume-generation
```

Render an existing `.tex` artifact to PDF:

```bash
PYTHONPATH=. python -m resume_generation.pdf
```

PDF rendering requires local `latexmk` and a working TeX installation.

## CLI

The evidence CLI provides staged local CRUD over evidence YAML:

```bash
uv run resumecr7-resume-evidence
uv run resumecr7-resume-evidence --schema projects
uv run resumecr7-resume-evidence --schema skills
uv run resumecr7-resume-evidence --schema education
uv run resumecr7-resume-evidence --schema experience
uv run resumecr7-resume-evidence --schema user
```

Collection schemas support list/show/create/edit/delete/apply/reload/quit style
workflows. Singleton schemas support inspection, edit, apply, reload, and quit.

## Configuration

ResumeCR7 reads settings from environment variables through `app/config.py`.

```bash
RESUMECR7_DATA_DIR=user
RESUMECR7_PACKAGED=false
# RESUME_EVIDENCE_ROOT=user/resume_evidence
# RESUME_GENERATION_ROOT=user/resume_generation
# RESUMECR7_LOG_DIR=user/logs

SKILL_METHOD=baseline        # baseline, embeddings, llm
SKILL_TOP_N=10
SKILL_BASELINE_FILTER=false

PROJ_METHOD=llm              # baseline, llm
# PROJ_TOP_N=2

DEV_MODE=true
LOG_LEVEL=INFO
OPENAI_API_KEY=your_key_here

EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=100

SKILL_LLM_MODEL=gpt-5-mini
SKILL_LLM_MAX_OUTPUT_TOKENS=1200
PROJ_LLM_MODEL=gpt-5-mini
JOB_FOCUS_LLM_MODEL=gpt-5-mini
JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS=1200
BULLETPOINTS_LLM_MODEL=gpt-5-mini
LINK_SCANNING_ENABLED=false
LINK_SCANNING_LLM_MODEL=gpt-5-mini
LINK_SCANNING_LLM_MAX_OUTPUT_TOKENS=1200
```

`OPENAI_API_KEY` is only required for embeddings, LLM-backed selection, job
focus generation, bullet generation, and enabled link scanning. Deterministic
baseline paths remain functional without it.

### Resume Generation Token Budgets

`user/resume_generation/config.yaml` controls per-run resume generation. Project
selection and project/experience bullet generation use dynamic output token
budgets by default instead of fixed `llm_max_output_tokens` values.

- Project selection sizes its budget from active project count and prompt size.
- Bullet generation sizes each request from the requested bullet count,
  highlight count, and evidence payload size.
- `max: null` means no app-level cap; set `max` in the relevant
  `llm_output_token_budget` block to enforce one.
- Direct API callers may still send `llm_max_output_tokens` as a hard override
  for debugging or one-off runs.

## API Surface

Start the backend:

```bash
uv run resumecr7-api --reload
```

OpenAPI docs are available at `http://127.0.0.1:8000/docs`.

### Health And Metrics

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service liveness, version, effective config, and runtime paths |
| `GET` | `/metrics-lite` | Aggregate request/error/latency/token counters |

### Resume Evidence API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/resume-evidence` | Load the full evidence registry |
| `GET` | `/resume-evidence/projects` | List projects |
| `POST` | `/resume-evidence/projects` | Create a project |
| `GET` | `/resume-evidence/projects/{id}` | Read a project |
| `PUT` | `/resume-evidence/projects/{id}` | Replace a project |
| `DELETE` | `/resume-evidence/projects/{id}` | Delete a project |
| `GET` | `/resume-evidence/experience` | List experience records |
| `POST` | `/resume-evidence/experience` | Create an experience record |
| `GET` | `/resume-evidence/experience/{id}` | Read an experience record |
| `PUT` | `/resume-evidence/experience/{id}` | Replace an experience record |
| `DELETE` | `/resume-evidence/experience/{id}` | Delete an experience record |
| `GET` | `/resume-evidence/education` | List education records |
| `POST` | `/resume-evidence/education` | Create an education record |
| `GET` | `/resume-evidence/education/{id}` | Read an education record |
| `PUT` | `/resume-evidence/education/{id}` | Replace an education record |
| `DELETE` | `/resume-evidence/education/{id}` | Delete an education record |
| `GET` | `/resume-evidence/skills` | Read skills |
| `PUT` | `/resume-evidence/skills` | Replace skills |
| `GET` | `/resume-evidence/user` | Read user info |
| `PUT` | `/resume-evidence/user` | Replace user info |

### Product Resume Generation API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/resume-generation/enrich-link-evidence` | Batch-enrich project/experience links and optionally write new highlights |
| `POST` | `/resume-generation/tex` | Run the full resume pipeline and return `.tex` output |
| `POST` | `/resume-generation/pdf` | Render the current `.tex` artifact and return PDF bytes |

`POST /resume-generation/tex` accepts an optional request-scoped `job_target`
override:

```json
{
  "job_target": {
    "schema_version": 1,
    "title": "Backend Engineer",
    "description": "Build Python APIs with PostgreSQL."
  }
}
```

### Capability APIs

These routes are useful backend capabilities and test surfaces. Product clients
should prefer the evidence and `/resume-generation` facade routes.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/select-skills` | Rank user-provided skills by category for a target role |
| `POST` | `/select-projects` | Rank explicit project candidates for a target role |
| `POST` | `/derive-job-focus` | Derive compact job-focus context from a job target |
| `POST` | `/generate-bulletpoints` | Generate grounded bullets for one project/experience record |
| `POST` | `/enrich-link-evidence` | Scan one link target and return grounded highlights |

Example `POST /select-skills` request:

```json
{
  "job_role": "AI/ML Engineer",
  "job_text": "Build model-serving APIs.",
  "technology": ["FastAPI", "Docker", "TensorFlow"],
  "programming": ["Python", "TypeScript"],
  "concepts": ["Machine Learning", "Distributed Systems"],
  "top_n": 5,
  "method": "baseline",
  "dev_mode": true
}
```

Example `POST /select-projects` request:

```json
{
  "context": {
    "title": "Backend Engineer",
    "description": "Build Python APIs with PostgreSQL."
  },
  "candidates": [
    {
      "id": "resumecr7",
      "name": "ResumeCR7",
      "summary": "FastAPI resume engine with grounded evidence.",
      "skills": {
        "technology": ["FastAPI", "PostgreSQL"],
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

## Testing

Backend:

```bash
uv run pytest
uv run pytest tests/test_packaging.py tests/test_runtime_data.py tests/test_health.py -q
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

Desktop:

```bash
cd frontend/src-tauri
cargo test
cargo fmt --check

cd ..
npm run desktop:build
```

## Development Rules

- Do not add skills that were not provided in the request.
- Respect `technology` / `programming` / `concepts` category boundaries.
- Keep deterministic baseline behavior functional even when embeddings or LLM
  paths fail.
- Keep user-authored evidence separate from generated artifacts.
- Add focused tests for non-trivial changes.
- Add a session log under `docs/devlog/` for non-trivial edit sessions and
  update `docs/devlog/Index.md`.
- Reserve `docs/CHANGELOG.md` for significant user-facing changes.

## Roadmap

Near-term planned work:

- Signed installers before broad public distribution.
- Manual release downloads before automatic updater integration.
- Async generation-run lifecycle once the local facade shape stabilizes.

See [docs/decisions/017-desktop-packaging-and-release-workflow.md](docs/decisions/017-desktop-packaging-and-release-workflow.md)
for the packaging and release phase model.
