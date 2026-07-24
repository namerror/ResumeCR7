# 008. Standalone Resume Evidence And Generation Layers

Date: 2026-06-02

## Status

Accepted

## Context

ResumeCR7 has grown from a skill-selection microservice into a resume engine with separate selection services and a grounded evidence foundation. ADR 005 organized `app/resume_evidence/` as a peer runtime subsystem under the FastAPI app, which was appropriate while evidence loading was only a startup hook and local CLI.

The next resume-generation layer needs to load user evidence, adapt it into skill-selection and project-selection requests, call those services, and combine their outputs into structured resume fill data. Keeping that orchestration inside `app/resume_evidence/` would make evidence management depend conceptually on the FastAPI services that also import evidence. That weakens the boundary between user-authored source data, service capabilities, and downstream resume assembly.

## Decision

Move resume evidence code out of the FastAPI `app/` package and make it a top-level package:

- `resume_evidence/` owns strict evidence schemas, deterministic YAML loading, staged CRUD/session logic, and the evidence CLI.
- `resume_generation/` is the top-level package reserved for orchestration code that consumes evidence, calls selection services or clients, and prepares structured resume fill data.
- `app/skill_selection/` remains the FastAPI-backed skill-selection service capability.
- `app/project_selection/` remains the FastAPI-backed project-selection service capability.
- `user/resume_evidence/` remains the canonical root for user-authored evidence files.
- `app/main.py` may import `resume_evidence.load_registered_evidence()` during startup for current runtime validation, but evidence management itself no longer lives under `app/`.
- The evidence CLI entrypoint is now `python -m resume_evidence.cli`.

The intended dependency direction is:

```text
resume_generation
  -> resume_evidence
  -> app skill/project selection clients or service contracts

app.main
  -> app.skill_selection
  -> app.project_selection
  -> resume_evidence
```

The generation layer should not silently mutate source evidence files. Generated artifacts remain derived state.

## Consequences

### Positive

- Separates user evidence management from the FastAPI service package.
- Gives resume-generation orchestration a clear home before full synthesis and assembly are implemented.
- Avoids placing API-calling orchestration inside the same evidence package that the API imports at startup.
- Keeps selection services focused on ranking capabilities while evidence and generation remain higher-level workflow layers.

### Negative

- Existing imports and CLI docs must move from `app.resume_evidence` to `resume_evidence`.
- `app.project_selection` still shares the `ProjectSkills` schema from `resume_evidence.models`; a later contracts extraction may be useful if this coupling grows.
- Startup validation still means the FastAPI app depends on the evidence package until a dedicated runtime evidence adapter is introduced.

### Neutral

- This decision supersedes the `app/resume_evidence/` package location from ADR 005, but it does not change the skill-selection or project-selection service boundaries.
- ADR 003 and ADR 004 remain valid for the grounded, file-based evidence model and the `user/resume_evidence/` source-of-truth root.
- Full resume synthesis, prose generation, and deterministic assembly remain future work.

## Alternatives Considered

- Keep orchestration under `app/resume_evidence/`: rejected because evidence would become both an app dependency and an app-calling workflow layer.
- Move all selection services out of `app/`: rejected because skill and project selection are already public FastAPI-backed capabilities with established tests and routes.
- Create only `app/resume_generation/`: rejected for this migration because the core concern is making evidence and generation separate from the service package rather than adding another app subsystem.
- Extract a shared contracts package immediately: deferred because the only current shared type is `ProjectSkills`, and a larger contracts split should be driven by the next concrete generation interface.
