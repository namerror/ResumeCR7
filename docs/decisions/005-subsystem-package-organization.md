# 005. Subsystem Package Organization

Date: 2026-04-26

## Status

Accepted

## Context

ResumeCR7 is expanding from a skill-selection microservice into a resume engine with multiple subsystems. Skill-selection code was previously spread across root-level `app/models.py`, `app/scoring/`, `app/services/`, and `app/data/`, while project selection already lived under `app/project_selection/`.

That layout made skill selection look like the whole application and left future resume subsystems without a consistent package boundary.

## Decision

Organize runtime code under peer subsystem packages:

- `app/skill_selection/` owns skill-selection models, orchestration, scoring, OpenAI clients, baseline filtering, role profiles, synonym data, and embedding caches.
- `app/project_selection/` owns project-selection models, API service orchestration, selector logic, baseline/LLM rankers, and the project LLM client.
- `app/resume_evidence/` remains the evidence loading and local CRUD subsystem.
- `app/main.py`, `app/config.py`, `app/metrics.py`, and `app/logging_config.py` remain app-level shared modules.
- Legacy imports under `app.models`, `app.scoring.*`, and `app.services.*` remain as thin compatibility shims.

Project selection is also exposed through `POST /select-projects` so API callers can use it as a first-class capability without reaching into internal Python modules.

## Consequences

### Positive

- The package tree now reflects ResumeCR7's resume-engine shape.
- Skill-specific code and data move together, reducing accidental cross-subsystem coupling.
- Project selection has the same API/service/metrics shape as skill selection.
- Existing external imports keep working through shims while new code can use canonical subsystem paths.

### Negative

- Compatibility shims add a small amount of indirection.
- Tests and docs must avoid drifting back to legacy paths.

### Neutral

- Project selection still ranks explicit candidates only; loading candidates from `app.state.resume_evidence` remains future work.
- Future shared resume data can still live under root-level `app/data/` if it is not owned by skill selection.

## Alternatives Considered

- Keep root-level `app/scoring/` and `app/services/`: rejected because it preserves the misleading skill-selector-centered architecture.
- Delete legacy imports immediately: rejected to avoid breaking external callers during a structural refactor.
- Move all data under root-level `app/data/`: rejected for current skill-specific role profiles, synonyms, and embedding caches because they are owned by skill selection today.
