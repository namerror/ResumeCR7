### 2026-07-26 - Phase 4 CI validation

**Agent:** Codex (GPT-5)

**Changes:**
- `.github/workflows/ci.yml:61-87` - Added a separate Ubuntu packaging-smoke job that installs desktop dependencies, sets up Rust for target-triple detection, builds the PyInstaller backend sidecar, and verifies `/health`.
- `scripts/smoke_desktop_sidecar.py:27-188` - Added a standard-library sidecar smoke helper that builds or accepts a sidecar binary, launches it in packaged mode with a temporary data directory, waits for `/health`, and terminates the process.
- `tests/test_packaging.py:125-237` - Added packaging smoke unit coverage for loopback port reservation, health retry behavior, packaged sidecar launch arguments/environment, process termination, and early startup failure reporting.

**Rationale:**
ADR 017 phase 4 calls for backend, frontend, and packaging-smoke validation to be diagnosed independently in CI. The repo already had Python and frontend jobs, so this change adds the missing Linux sidecar artifact check without introducing new Python lint/type tools that are not yet configured in `pyproject.toml`.

**Tests:**
- `test_smoke_sidecar_reserves_bindable_loopback_port`: validates the helper selects a loopback port that can be rebound after reservation.
- `test_smoke_wait_for_health_retries_until_ready`: validates readiness polling retries before success.
- `test_smoke_sidecar_launches_packaged_backend_and_terminates`: validates packaged mode arguments, environment variables, and cleanup.
- `test_smoke_sidecar_reports_early_process_exit`: validates failed sidecar startup includes process output.
- `uv run pytest`: 551 passed, 4 skipped.
- `npm test`: 18 passed.
- `npm run build`: passed.
- `uv run --extra desktop python scripts/smoke_desktop_sidecar.py --timeout-seconds 30`: built the PyInstaller sidecar and verified `/health`.

**Impact:**
Pull requests and main-branch pushes now catch Linux backend sidecar packaging regressions before desktop release work moves to full installers and tag-based artifacts.
