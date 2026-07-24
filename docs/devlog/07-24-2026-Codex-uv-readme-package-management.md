### 2026-07-24 - Document uv Package Management

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md` - Switched local package setup, command execution, and test examples to `uv sync --extra dev` and `uv run ...`.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The project now has `pyproject.toml` package metadata and console scripts, so uv can manage the editable development environment directly. The README should point contributors at the package-manager flow that matches the package hygiene work.

**Tests:**
- Not run; documentation-only change.

**Impact:**
Contributors can use uv as the documented default package management workflow while legacy commands remain noted as supported.
