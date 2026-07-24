# 017. Desktop Packaging and Release Workflow

Date: 2026-07-24

## Status

Accepted

## Context

ADR 016 established ResumeCR7's first product surface as a local-first web
workbench over the existing FastAPI backend, with desktop distribution as the
first packaging target after the workflow is proven.

The repo now has the core pieces needed for that direction:

- FastAPI owns product-facing evidence CRUD and resume-generation facade
  endpoints.
- React/Vite owns the local workbench UI.
- Resume evidence and generated artifacts are file-backed.
- The project intentionally avoids early database, auth, hosted multi-user, and
  async queue dependencies.

Turning this into a proper distributable app requires a packaging strategy and
a repeatable CI/CD release path. That workflow needs to preserve current app
boundaries, keep user data outside the installed application bundle, and avoid
forcing a backend rewrite before the product workflow is stable.

## Decision

Package ResumeCR7 as a desktop app by wrapping the existing React/Vite frontend
and FastAPI backend rather than rewriting the application into a native UI.

Use Tauri v2 as the preferred desktop shell and package the Python backend as a
sidecar executable. The desktop app should launch the sidecar locally, wait for
the backend health endpoint, then let the bundled frontend call the backend
through a loopback address or equivalent local runtime bridge.

The target runtime shape is:

```text
ResumeCR7 desktop app
  -> Tauri shell
  -> bundled React/Vite frontend
  -> packaged Python FastAPI sidecar
  -> OS app data directory for evidence, config, logs, and artifacts
```

Electron remains an acceptable fallback if Tauri's Python sidecar and platform
signing flow become more expensive than expected, but it is not the preferred
first implementation path.

## Phased Workflow

Future packaging and release work should use these phases as the shared
reference plan.

### Phase 1: Package Hygiene

Make the Python backend and frontend build outputs cleanly packageable before
building installers.

- Add Python package metadata, preferably in `pyproject.toml`.
- Expose stable backend entrypoints, such as `resumecr7-api`,
  `resumecr7-resume-evidence`, and `resumecr7-resume-generation`.
- Keep runtime dependencies separate from development and test dependencies.
- Ensure `app.main` is importable and runnable consistently.
- Maintain a stable health endpoint for desktop startup checks.
- Route user evidence, generation config, artifacts, and logs through a single
  configurable data-root settings layer.

### Phase 2: Runtime Data Model

Move packaged-app writes out of the repository and out of the installed app
bundle.

- Introduce a desktop-safe app data root, configurable for development and
  resolved from OS-specific application data locations in packaged builds.
- Store source evidence, generation config, generated artifacts, and logs under
  that data root.
- Bootstrap missing evidence/config files from templates or defaults on first
  launch.
- Preserve strict schema validation and atomic YAML writes.
- Keep file-backed persistence as the first adapter; do not introduce database
  persistence for desktop packaging alone.

The packaged runtime should converge on a layout like:

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
  logs/
```

### Phase 3: Desktop Shell

Build the desktop runtime around the proven local web workbench.

- Add a Tauri app that bundles the frontend production build.
- Package the Python backend as a sidecar with PyInstaller, Nuitka, or another
  reproducible Python executable builder.
- Add a small backend launcher module for desktop runtime concerns instead of
  treating the development server command as the long-term packaging interface.
- Start the sidecar on an available loopback port.
- Make the frontend discover the backend URL from the desktop runtime.
- Wait for the backend health check before enabling API-dependent UI.
- Shut down the sidecar when the desktop app exits.
- Write runtime logs to the app data directory.

### Phase 4: CI Validation

Split CI into backend, frontend, and packaging-smoke validation so failures are
easy to diagnose.

On pull requests:

- Install Python dependencies.
- Run configured Python lint, format, type, and test checks.
- Install frontend dependencies with the package-manager lockfile.
- Run frontend tests.
- Build the frontend.
- Build at least one backend sidecar smoke artifact, initially on Linux.
- Start the sidecar and verify the health endpoint responds.

On the main branch:

- Run the same validation as pull requests.
- Optionally produce unpublished nightly desktop artifacts once packaging is
  stable enough to make those artifacts useful.

### Phase 5: Release Workflow

Use tag-based releases with GitHub Actions.

- Use SemVer tags such as `v0.1.0`, `v0.2.0`, and `v0.2.1`.
- Keep one canonical source for the application version.
- Update `docs/CHANGELOG.md` only for significant user-facing changes.
- Build Windows, macOS, and Linux desktop artifacts from release tags.
- Upload installers, archives, and checksums to a draft GitHub Release.
- Smoke test release artifacts before publishing the release.

Unsigned builds are acceptable for early internal testing. Before broad public
distribution, add:

- Windows code signing.
- macOS Developer ID signing and notarization.
- Linux checksums and a documented install path, such as AppImage and/or `.deb`.

### Phase 6: Update Strategy

Defer automatic updates until installers and signing are stable.

The update path should progress in this order:

- Manual downloads from GitHub Releases.
- In-app link or check that points users to the latest release.
- Tauri updater integration after signing, checksums, and release metadata are
  reliable.

## Consequences

### Positive

- Preserves the current FastAPI and React/Vite architecture.
- Avoids a premature native UI rewrite.
- Keeps sensitive resume data local by default.
- Gives future agents a shared, named phase model for packaging work.
- Creates a CI/CD path that can grow from smoke artifacts to signed releases.
- Keeps database-backed persistence and hosted multi-user concerns out of the
  desktop packaging milestone.

### Negative

- The desktop app must manage a local backend process.
- Packaging Python consistently across Windows, macOS, and Linux adds build
  complexity.
- Platform signing and notarization will become required before comfortable
  public distribution.
- Local PDF rendering may still require bundled or discoverable rendering tools
  unless a later renderer replaces the LaTeX dependency.

### Neutral

- This decision does not implement packaging, installers, signing, auto-update,
  or CI changes yet.
- This decision does not choose PyInstaller versus Nuitka permanently.
- This decision does not prevent a later hosted service, database adapter, or
  async run lifecycle.
- Electron remains a fallback if Tauri proves unsuitable for ResumeCR7's
  sidecar/runtime needs.

## Alternatives Considered

- Electron desktop shell: viable, but deferred because Tauri is lighter and
  works naturally with the existing Vite frontend. Electron remains the fallback
  if the sidecar lifecycle or release tooling is materially easier there.
- Native desktop rewrite: rejected because FastAPI and React/Vite already define
  useful product boundaries and rewriting would delay validation of the actual
  resume workflow.
- Hosted web app first: deferred for the same reasons as ADR 016: it requires
  auth, database persistence, artifact storage, rate limiting, and multi-user
  isolation before the local workflow is proven.
- Database-backed desktop persistence: rejected for this milestone because the
  existing YAML evidence layer is deterministic, testable, and sufficient for a
  local-first desktop app.
- Auto-update from the first release: rejected because it should come after
  stable installers, signing, release metadata, and checksum handling.
