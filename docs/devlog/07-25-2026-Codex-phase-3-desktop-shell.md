### 2026-07-25 - Phase 3 desktop shell

**Agent:** Codex (GPT-5)

**Changes:**
- `app/desktop_backend.py` - Added the desktop sidecar launcher that sets packaged runtime environment before starting FastAPI.
- `scripts/build_desktop_sidecar.py` - Added the PyInstaller sidecar build helper with target-triple output naming for Tauri.
- `frontend/src-tauri/` - Added the Tauri v2 shell, sidecar lifecycle management, backend health polling, and app-data sidecar logging.
- `frontend/src/runtime.ts` and `frontend/src/main.tsx` - Added desktop runtime backend URL discovery before rendering the React workbench.
- `pyproject.toml`, `uv.lock`, `frontend/package.json`, and `frontend/package-lock.json` - Added optional desktop dependencies and desktop npm scripts.
- `README.md`, `frontend/README.md`, `docs/CHANGELOG.md`, and `.gitignore` - Documented the desktop workflow and ignored generated sidecar/build outputs.
- `frontend/src/runtime.ts` - Updated backend URL discovery to try the Tauri command first and fall back to `/api` only when unavailable, fixing direct AppImage launches that displayed the backend as offline.

**Rationale:**
ADR 017 Phase 3 calls for a desktop shell around the proven local web workbench.
Keeping Rust responsible for the sidecar lifecycle gives the frontend one stable
runtime command for API discovery while preserving the existing FastAPI route
contracts and file-backed persistence.

**Tests:**
- `tests/test_packaging.py` validates desktop console script metadata, launcher environment setup, and sidecar executable naming.
- `frontend/src/runtime.test.ts` validates browser fallback and mocked Tauri backend URL discovery.
- `frontend/src-tauri/src/lib.rs` includes unit coverage for health response parsing and loopback port reservation.
- `uv run pytest tests/test_packaging.py tests/test_runtime_data.py tests/test_health.py -q`: 23 passed.
- `npm test`: 18 passed.
- `npm run build`: passed.
- `npm run sidecar:build`: produced a Linux sidecar binary, and the frozen binary returned `status: ok` from `/health` with a temp data directory.
- `cargo fmt --check`: passed.
- `cargo test`: 4 Rust unit tests passed after installing Ubuntu Tauri native dependencies.
- `npm run desktop:build`: produced `frontend/src-tauri/target/release/bundle/appimage/ResumeCR7_0.3.0_amd64.AppImage`.

**Impact:**
ResumeCR7 can now be run as a local desktop app that starts its own backend
sidecar, waits for health, and stores packaged runtime data under the OS app-data
directory.
