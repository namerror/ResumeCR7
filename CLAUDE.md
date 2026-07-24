You are an engineering assistant working on ResumeCR7, a grounded resume-generation service with an existing skill-selection API and an implemented first resume-evidence milestone.
Your goal is to help implement features safely and incrementally.

## Agent context index
- Start here for navigation: `docs/agent-context-index.md`
- Architecture/flow map: `docs/architecture-overview.md`

## Current project shape
- The repo still ships a FastAPI skill-selection API through `/select-skills`.
- The repo now includes app-owned `app/resume_evidence`, which loads `user/resume_evidence/*.yaml` at startup, exposes REST CRUD, and preserves a top-level CLI compatibility package.
- The repo now includes app-owned `app/resume_generation`, which consumes evidence, calls backend services, assembles structured fill data, and exposes synchronous `/resume-generation` facade endpoints.
- Skill selection is now one subsystem inside a broader grounded resume-engine direction.

## Non-negotiables
- Do NOT invent skills. Output must be a subset of input skills.
- Do NOT infer seniority/domain unless explicitly provided.
- Keep the baseline deterministic and fully testable.
- Every change should include tests (unit + integration where relevant).
- Maintain stable ordering across runs.
- Keep grounded resume work evidence-backed and inspectable.

## Development Workflow (must follow)
For grounded resume work:
1) user-authored evidence file
2) deterministic validation/loading
3) tests and fixtures
4) inspectable runtime integration
5) only then higher-level synthesis work

## Code organization rules
- FastAPI wiring in `app/main.py`
- Pydantic models in subsystem packages such as `app/resume_evidence/models.py` and `app/resume_generation/models.py`
- Skill-selection scorers in `app/skill_selection/scoring/`
- Skill-selection orchestration in `app/skill_selection/`
- Project-selection orchestration in `app/project_selection/`
- Resume evidence loading and local CRUD workflow in `app/resume_evidence/`, with `resume_evidence/` as compatibility shims and CLI
- Resume-generation orchestration and facade endpoints in `app/resume_generation/`, with `resume_generation/` as compatibility shims
- Role expectations and config data in `app/data/`
- User-authored evidence in `user/resume_evidence/`
- Tests in `tests/`
- Evaluation script in `scripts/eval.py`

## Baseline scorer expectations
- Normalize strings deterministically
- Apply synonyms from `app/scoring/synonyms.py`
- Respect category boundaries
- Keep deterministic tie-breaking
- Preserve the baseline as the reliable fallback path

## Resume evidence expectations
- Treat `user/resume_evidence/` as canonical user-authored source data
- Validate evidence deterministically before using it at runtime
- Do not silently mutate evidence files during normal resume generation flows; batch link enrichment may append unique scanned highlights when explicitly invoked
- Keep generated artifacts separate from source-of-truth evidence
- Preserve compatibility with the shared `technology` / `programming` / `concepts` taxonomy

## Output contracts
- Production skill-selection API: selected skills JSON by category
- Production project-selection API: selected project IDs and scores
- Resume-generation facade API: batch link enrichment, `.tex` generation, and PDF rendering under `/resume-generation`
- Dev mode may include scores, explanations, token usage, warnings, or fallback metadata
- Evidence CLI: staged CRUD/session management for `projects.yaml`

## When editing knowledge files
- Keep them small and readable.
- Prefer synonyms/aliases over hardcoded special cases.
- Add or adjust corresponding tests and evaluation cases.

## Definition of "Done"
A feature is done when:
- tests pass (`pytest`) when applicable
- evaluation scripts still make sense for skill-selection changes
- behavior is deterministic
- the API contract is unchanged unless intentionally updated
- evidence behavior is validated and inspectable
- work is logged in `docs/devlog/`

## Development Logging (required)

After completing any non-trivial task or making architectural decisions, you MUST document your work in the appropriate log file.

### Session Log (`docs/devlog/`)
Every agent edit session MUST end with a new session file under `docs/devlog/` (unless the only changes are trivial, e.g. typo fixes or minor formatting). The dev log should be detailed — include an overview of the implementation, what changed, and why.

**File naming convention:** `MM-DD-YYYY-AgentName-short-description.md`
- Use the agent/tool name that performed the work (e.g., `Claude`, `Copilot`, `Codex`, `GPT4o`)
- Examples: `03-07-2026-Claude-optimize-logging-instructions.md`, `03-08-2026-Copilot-add-role-profile-tests.md`

**Required fields in each session file:**
- **Agent & Model**: The agent name and specific model version used
- **Date & Summary**: ISO date + brief task description
- **Changes**: Files modified/created with line references where relevant
- **Rationale**: Why you made certain decisions or chose this approach
- **Tests**: What tests were added/modified and what they validate
- **Impact**: What this enables, fixes, or unlocks for future work
