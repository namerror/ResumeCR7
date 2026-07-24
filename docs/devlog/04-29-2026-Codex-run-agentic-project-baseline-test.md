### 2026-04-29 - Run Agentic Project Baseline Test

**Agent:** Codex (GPT-5)

**Changes:**
- `docs/notes/04-29-2026-Codex-agentic-project-selection-baseline-test.md:1-129` - Added an agentic test report for `/select-projects` baseline results, including request/response excerpts, ranking rationale, and recommendations.
- `docs/devlog/Index.md:16` - Added this session to the devlog index.

**Rationale:**
The project-selection baseline needed a focused agentic review using the local dataset. The report keeps the run scoped to deterministic baseline behavior, confirms schema and grounding requirements, and records observed ranking concerns without changing scoring behavior in the same evaluation session.

**Tests:**
- `.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --base-url http://127.0.0.1:8001 --suite project_selection --variant baseline --output /tmp/resumecr7-project-baseline-agentic-results.json --fail-on-error`: ran the two project-selection baseline dataset requests against the local API and received HTTP 200 for both.

**Impact:**
Documents that baseline project selection picks the expected best-fit projects but has score-calibration concerns when sparse and dense matches receive equal normalized scores. This gives future scoring work a concrete regression target.
