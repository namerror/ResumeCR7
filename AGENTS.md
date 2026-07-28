# AGENTS.md - Contributor And Agent Guide

ResumeCR7 is a local-first career evidence workbench. It stores structured,
user-authored work evidence and produces tailored resume artifacts from that
evidence.

## Start Here

- Product and setup overview: `README.md`
- Architecture map: `docs/architecture-overview.md`
- Development guide: `docs/development.md`

## Repository Layout

- `app/` - FastAPI backend and product services
- `frontend/` - React/Vite workbench and Tauri desktop shell
- `resume_evidence/` - compatibility shims and CLI entrypoints
- `resume_generation/` - compatibility shims and CLI entrypoints
- `data/` - durable evaluation and skill-pool assets
- `examples/` - fictional starter evidence and generation config
- `tests/` - backend tests
- `scripts/` - build, evaluation, and release helpers

## Invariants

- Never invent resume claims or skills. Generated output must be grounded in
  user-authored or explicitly enriched evidence.
- Skill category boundaries are strict: `technology`, `programming`, and
  `concepts`.
- Stable deterministic ordering is required for baseline behavior.
- Baseline selection must remain functional when embeddings or LLM-backed paths
  fail.
- User-authored evidence and generated artifacts must stay separate.
- Do not add database-backed persistence, async run lifecycle, or broad format
  management unless the architecture is intentionally updated.
- Do not add new LLM dependencies without baseline success, an evaluation
  dataset, and measured improvement.

## Development Rules

- Prefer small, runnable PR-style diffs.
- Add focused tests for non-trivial changes.
- Use existing subsystem patterns before adding new abstractions.
- Update `docs/CHANGELOG.md` only for significant user-facing additions or
  breaking changes.
- Keep local runtime data out of git. The ignored `user/` directory is for local
  development and desktop runtime state.

## Common Tasks

### Add A Role Profile

1. Create a profile file in `app/skill_selection/data/role_profiles/`.
2. Ensure `app/skill_selection/scoring/role_profiles.py` loads it
   deterministically.
3. Add or update tests in `tests/test_role_profiles.py`.

### Change Evidence Behavior

1. Update the schema or service under `app/resume_evidence/`.
2. Preserve compatibility shims under `resume_evidence/` when public imports or
   CLI behavior are affected.
3. Add tests for validation, loading, API behavior, and atomic writes where
   relevant.

### Change Resume Generation

1. Work inside `app/resume_generation/` unless touching a lower-level capability.
2. Keep selection, job-focus, bullet generation, assembly, and artifact writing
   inspectable as separate stages.
3. Preserve deterministic fallback behavior and generated-artifact separation.

## Validation

Backend:

```bash
uv run pytest
```

Frontend:

```bash
cd frontend
npm test
npm run build
```

Release metadata:

```bash
uv run python scripts/validate_release.py --tag vX.Y.Z
```
