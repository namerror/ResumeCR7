# AGENTS.md — Agent Playbook

This repo is designed to be edited by coding agents (Claude Code, Codex, etc.) safely. ResumeCR7 now spans both the legacy skill-selection API and a newer grounded resume-evidence foundation.

## Agent context index
- Start here for navigation: `docs/agent-context-index.md`
- Architecture/flow map: `docs/architecture-overview.md`

## Organization
- Tests in `tests/`
- Skill scoring logic in `app/skill_selection/scoring/`
- Resume evidence logic in `app/resume_evidence/` with `resume_evidence/` compatibility shims and CLI
- Resume generation orchestration and facade endpoints in `app/resume_generation/` with `resume_generation/` compatibility shims
- User-authored evidence files in `user/resume_evidence/`

## Repository invariants
- Never add skills that weren't provided in the request.
- Category boundaries are respected: Technology / Programming / Concepts.
- Stable deterministic ordering is required.
- Baseline method must remain functional even if embeddings/hybrid fails.

## How agents should work in this repo
### Make small, runnable changes
- Prefer small PR-style diffs.
- Each change includes tests.
- Add a new ADR under `docs/decisions/` when making architectural choices.

### Avoid accidental scope creep
- This repo ships a synchronous app-owned resume generation facade, but async run lifecycle, database-backed persistence, and richer format management are still future work.
- Do not add database dependencies early.
- Do not add LLM dependencies without:
  1) baseline success
  2) evaluation harness dataset
  3) measured improvement

## Common tasks
### Add a new role profile
1. Create a new profile file in `app/skill_selection/data/role_profiles/` with relevant keywords
2. Ensure `app/skill_selection/scoring/role_profiles.py` loads it and the baseline scorer uses it deterministically

### Add tests
1. Add test cases in `tests/test_role_profiles.py` for new profiles or edge cases
2. Test function logic directly with controlled inputs to ensure deterministic outputs

## Don'ts
- Don't add new features without tests.
- Don't modify existing role profiles without a clear reason and corresponding test updates.
- Don't introduce non-determinism in the baseline method.
- Don't make changes without logging them in `docs/devlog/` unless trivial (typo fixes, formatting).

## Development Logging (required)

After completing any non-trivial task or making architectural decisions, you MUST document your work in the appropriate log file.

### Session Log (`docs/devlog/`)
Every agent edit session MUST end with a new session file under `docs/devlog/` (unless the only changes are trivial, e.g. typo fixes or minor formatting). The dev log should be detailed — include an overview of the implementation, what changed, and why.

**File naming convention:** `MM-DD-YYYY-AgentName-short-description.md`
- Use the agent/tool name that performed the work (e.g., `Claude`, `Copilot`, `Codex`, `GPT4o`)
- Examples: `03-07-2026-Claude-optimize-logging-instructions.md`, `03-08-2026-Copilot-add-role-profile-tests.md`

**Required fields in each session file:**
- **Agent & Model**: The agent name and specific model version used (e.g., Claude Sonnet 4.5, GPT-4o, Copilot with claude-sonnet-4-5)
- **Date & Summary**: ISO date + brief task description (1 line)
- **Changes**: Files modified/created with line references where relevant
- **Rationale**: Why you made certain decisions or chose this approach
- **Tests**: What tests were added/modified and what they validate
- **Impact**: What this enables, fixes, or unlocks for future work

**Format:**
```markdown
### YYYY-MM-DD - [Brief Summary]

**Agent:** [Agent name] ([Model version, e.g. Claude Sonnet 4.5])

**Changes:**
- `path/to/file.py:10-25` - Description of change
- `tests/test_file.py` - Added tests for X

**Rationale:**
Explain why these changes were made and key decisions...

**Tests:**
- test_name: what it validates
- test_edge_case: what scenario it covers

**Impact:**
What this enables or fixes...
```

**Note: After adding a session file, update `docs/devlog/Index.md` to add an entry for it.** 

### Changelog (`docs/CHANGELOG.md`)
The CHANGELOG is reserved for **significant, user-facing changes only** — primarily new features and major breaking changes.

**Do NOT add to CHANGELOG for:**
- Bug fixes
- Adding or updating tests
- Internal refactors or implementation tweaks
- Documentation updates

These belong in a dev log session file instead.

For user-facing additions, update using [Keep a Changelog](https://keepachangelog.com/) format:
- **Added**: new features

Keep entries in the `[Unreleased]` section until a version is tagged.

### Decision Records (`docs/decisions/`)
For significant architectural choices, create numbered ADRs (Architectural Decision Records):
- Format: `NNN-short-title.md` (e.g., `001-baseline-scoring.md`)
- Include: Context, Decision, Consequences, Alternatives Considered
- These are permanent records - don't modify old ADRs, create new ones instead

### When NOT to log
- Trivial changes (typo fixes, minor formatting)
- Exploratory work that gets reverted
- Changes explicitly marked as temporary experiments
