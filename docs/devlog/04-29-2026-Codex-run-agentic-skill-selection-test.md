### 2026-04-29 - Run Agentic Skill Selection Test

**Agent:** Codex (GPT-5)

**Changes:**
- `docs/agentic-testing/run_agentic_dataset.py` - Removed an accidental standalone usage docstring before the `from __future__` import so the runner can execute.
- `docs/notes/04-29-2026-Codex-agentic-skill-selection-no-embeddings-test.md` - Added the agentic skill-selection test report for the no-embeddings run.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The requested session tested skill selection without embeddings by using the reusable dataset runner against the local FastAPI app. The report captures method comparisons, baseline-filter behavior, token use, and qualitative relevance concerns.

**Tests:**
- `.venv/bin/python -m py_compile docs/agentic-testing/run_agentic_dataset.py`
- `.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --suite skill_selection --exclude-variant embeddings_with_filter --dry-run --output /tmp/resumecr7-skill-no-embeddings-dry-run.json`
- `.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --suite skill_selection --exclude-variant embeddings_with_filter --output /tmp/resumecr7-skill-no-embeddings-results.json --fail-on-error`

**Impact:**
The no-embeddings skill-selection dataset path has now been exercised end to end, and the results are documented for future comparison.
