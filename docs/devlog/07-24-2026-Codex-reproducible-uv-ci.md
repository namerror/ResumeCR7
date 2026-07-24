### 2026-07-24 - Reproducible uv CI

**Agent:** Codex (GPT-5)

**Changes:**
- `.github/workflows/ci.yml` - Replaced pip-based Python setup with pinned uv, `uv sync --locked --extra dev`, and `uv run pytest`; added a lockfile-backed frontend job with `npm ci`, `npm test`, and `npm run build`.
- `uv.lock` - Added a committed uv lockfile for reproducible Python dependency resolution.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The repository now has package metadata and documents uv as the default Python package workflow. CI should install from the same locked dependency graph and also validate the frontend build with the existing npm lockfile.

**Tests:**
- `uv sync --locked --extra dev`
- `uv run pytest`: 536 passed, 4 skipped
- `npm ci`
- `npm test`: 15 passed
- `npm run build`

**Impact:**
Pull request CI now exercises reproducible backend dependency installs from `uv.lock` and verifies both backend tests and frontend lockfile/build health.
