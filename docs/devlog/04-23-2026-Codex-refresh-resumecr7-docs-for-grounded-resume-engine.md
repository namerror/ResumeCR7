### 2026-04-23 - Refresh ResumeCR7 docs around the grounded resume engine

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md` - Reframed the repo as ResumeCR7’s grounded resume engine, documented current capabilities across both skill selection and resume evidence, and split shipped behavior from planned next stages.
- `docs/architecture-overview.md` - Updated the architecture map to include `app.resume_evidence`, startup evidence loading into `app.state.resume_evidence`, the implemented `projects.yaml` schema, and the future resume pipeline boundary.
- `docs/agent-context-index.md`, `CLAUDE.md`, and `AGENTS.md` - Refreshed agent-facing guidance so the repo is described as a broader resume-engine codebase rather than only a skill-selector service.
- `docs/branch-03-grounded-resume-generation.md` - Revised Branch 03 to reflect the implemented first evidence milestone: `projects.yaml` parsing, startup loading, and staged CLI-based CRUD/session management.
- `docs/decisions/004-user-resume-evidence-root-and-projects-milestone.md` and `docs/decisions/README.md` - Added a superseding ADR that records `user/resume_evidence/` as the canonical evidence root and captures the current implemented milestone without rewriting ADR 003.
- `docs/devlog/Index.md` - Added this session entry.

**Rationale:**
The repo narrative had fallen behind the codebase. Top-level docs and agent-facing guidance still presented the project primarily as a skill-selection microservice even though the code now includes a real grounded resume-evidence package, startup evidence loading, and a staged project-evidence CLI. I refreshed the active docs around the current truth: ResumeCR7 is becoming a grounded resume-generation service, the skill-selection API is still a shipped subsystem, and `projects.yaml` is the first implemented source-of-truth evidence milestone.

I also kept ADR 003 intact as historical record and captured the path correction plus milestone state in a new ADR, since the implementation now uses `user/resume_evidence/` rather than the earlier `data/resume_evidence/` convention.

**Tests:**
- Attempted `python3 -m app.resume_evidence.cli --help`, but the local environment is missing `pydantic`, so runtime verification was blocked by unavailable dependencies.
- Repo-wide search review for `data/resume_evidence` across active docs to ensure refreshed project docs now point to `user/resume_evidence/`.
- Documentation-only change; no code behavior changed and no automated test files were modified.

**Impact:**
The repo now has a coherent, current story for contributors and agents. New readers can understand that ResumeCR7 already ships skill selection, already has a grounded projects-evidence layer, and is intentionally building toward a full evidence-based resume engine without overstating the current runtime surface.
