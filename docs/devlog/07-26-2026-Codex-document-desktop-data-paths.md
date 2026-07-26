### 2026-07-26 - Document desktop data paths

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md` - Expanded the runtime data section with local development vs. packaged desktop storage behavior, platform-specific Tauri app-data paths, and artifact retrieval locations.
- `frontend/README.md` - Added a concise desktop data storage note for frontend/Tauri developers.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The desktop app stores user data outside the repository, while local web/backend development uses the repo-local `user/` directory. Documenting both modes prevents confusion when looking for YAML evidence files, generated `.tex`, generated `.pdf`, and logs.

**Tests:**
- Not run; documentation-only change.

**Impact:**
Users can now locate and back up resume evidence, generation artifacts, and logs across Linux, macOS, Windows, and local development workflows.
