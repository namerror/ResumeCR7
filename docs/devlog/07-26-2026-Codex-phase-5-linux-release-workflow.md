### 2026-07-26 - Phase 5 Linux release workflow

**Agent:** Codex (GPT-5)

**Changes:**
- `.github/workflows/release-linux.yml:1-102` - Added a tag-triggered Linux AppImage release workflow that validates metadata, runs backend/frontend tests, builds the desktop app, smokes the built sidecar, generates SHA256 checksum files, and creates a draft GitHub Release.
- `scripts/validate_release.py:30-156` - Added strict SemVer tag validation, app/Tauri/Cargo version checks, latest changelog release validation, and changelog-derived release notes output.
- `tests/test_release_validation.py:49-91` - Added release validation tests for matching metadata, invalid tags, version drift, latest changelog extraction, and notes-file output.
- `app/__init__.py:1`, `frontend/src-tauri/tauri.conf.json:4`, `frontend/src-tauri/Cargo.toml:3`, and `frontend/src-tauri/Cargo.lock` - Aligned current release metadata to `0.4.0`.
- `README.md:42-46` and `README.md:477-483` - Updated the Linux AppImage example path and removed completed CI/release items from the near-term roadmap.

**Rationale:**
ADR 017 phase 5 calls for tag-based releases, one canonical version, draft GitHub Releases, checksums, and release smoke testing. ResumeCR7 currently supports Linux AppImage packaging, so this implements the Linux slice first and keeps Windows/macOS signing and artifacts deferred.

**Tests:**
- `python scripts/validate_release.py --tag v0.4.0 --notes-out /tmp/resumecr7-release-notes.md`: validates current release metadata and changelog-derived notes.
- `uv run pytest tests/test_release_validation.py tests/test_version.py tests/test_packaging.py`: 21 passed.
- `uv run pytest`: 557 passed, 4 skipped.
- `npm test`: 18 passed.
- `npm run build`: passed.
- `npm run desktop:build`: produced `frontend/src-tauri/target/release/bundle/appimage/ResumeCR7_0.4.0_amd64.AppImage`.
- `cargo test`: 4 passed after rerunning outside the sandbox because the loopback-port test needs socket binding.
- `uv run --extra desktop python scripts/smoke_desktop_sidecar.py --binary frontend/src-tauri/binaries/resumecr7-backend-x86_64-unknown-linux-gnu --timeout-seconds 30`: sidecar `/health` smoke passed.
- `sha256sum frontend/src-tauri/target/release/bundle/appimage/ResumeCR7_0.4.0_amd64.AppImage`: `1b6d3f7e60dcf71064b6ce81a213a1ca019128697061ee8864216403c3d7b83d`.

**Impact:**
Pushing a `vX.Y.Z` tag can now produce an unsigned Linux AppImage draft release with checksum assets and changelog-backed release notes, while strict guards prevent publishing artifacts with mismatched version metadata.
