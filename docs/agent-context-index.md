# Agent Context Index

Use this file as a compact navigation index for coding agents and contributors.

## Canonical Guides

1. `AGENTS.md`
   - repository invariants, scope guardrails, validation commands, and common tasks
2. `README.md`
   - product framing, setup, runtime data, API summary, and contribution steps
3. `docs/development.md`
   - local development workflow, tests, documentation, and release checks
4. `docs/architecture-overview.md`
   - subsystem map, startup flow, runtime flows, and architecture boundaries

## Recommended Read Order

1. `AGENTS.md`
2. `README.md`
3. `docs/development.md`
4. `docs/architecture-overview.md`
5. `app/main.py`
6. `app/config.py`
7. `app/runtime_data.py`
8. `app/resume_evidence/api.py`
9. `app/resume_evidence/service.py`
10. `app/resume_evidence/loader.py`
11. `app/resume_evidence/session.py`
12. `app/resume_generation/api.py`
13. `app/resume_generation/main.py`
14. `app/resume_generation/selection.py`
15. `app/resume_generation/bullet_points.py`
16. `app/resume_generation/assembly.py`
17. `app/skill_selection/selector.py`
18. `app/skill_selection/scoring/baseline.py`
19. `app/project_selection/service.py`
20. `app/project_selection/selector.py`

## Runtime Data

Local runtime data defaults to the ignored `user/` directory. The backend
bootstraps schema-valid defaults when files are missing. Safe fictional starter
files live under `examples/`.

## Entry Points

- FastAPI app composition: `app/main.py`
- Runtime settings and data roots: `app/config.py`, `app/data_paths.py`
- Runtime bootstrap defaults: `app/runtime_data.py`
- Resume evidence API and local YAML services: `app/resume_evidence/`
- Resume generation facade and orchestration: `app/resume_generation/`
- Skill selection services and scoring: `app/skill_selection/`
- Project selection services and scoring: `app/project_selection/`
- Frontend workbench: `frontend/src/`
- Tauri desktop shell: `frontend/src-tauri/`
