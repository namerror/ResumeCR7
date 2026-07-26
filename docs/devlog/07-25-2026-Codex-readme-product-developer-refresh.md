### 2026-07-25 - README product and developer refresh

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md` - Reworked the README into a user/developer guide covering product purpose, desktop and web setup, repository structure, runtime data, evidence schemas, generation flow, CLI usage, configuration, API endpoints, tests, development rules, and roadmap.
- `docs/CHANGELOG.md` - Expanded the Unreleased desktop entry and added the direct AppImage backend URL fix.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The prior README still read like a transition document and made users assemble current behavior from historical sections. The new structure leads with the runnable product surfaces and gives developers one place to understand setup, storage, endpoint contracts, and verification commands.

**Tests:**
- `git diff --check`: validates the documentation diff has no whitespace errors.

**Impact:**
Users can now find the desktop and local web startup path quickly, while developers get a current map of the app structure, runtime data model, and exposed API surface.
