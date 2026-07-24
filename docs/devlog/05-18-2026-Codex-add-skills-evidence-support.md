### 2026-05-18 - Add skills evidence support

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_evidence/models.py` - Added `SkillsFile` as the strict runtime schema for `user/resume_evidence/skills.yaml`, reusing the existing three-bucket taxonomy model.
- `.gitignore`, `app/resume_evidence/loader.py`, `app/resume_evidence/__init__.py`, `user/resume_evidence/skills.yaml` - Registered the new `skills` evidence schema, exposed it through the package surface, added a starter file, and carved out a narrow ignore exception so `skills.yaml` can be tracked without unignoring the rest of `user/resume_evidence/`.
- `app/resume_evidence/session.py`, `app/resume_evidence/cli.py` - Added `SkillsEvidenceSession`, pending-change reporting for skills, and a `--schema skills` CLI flow with staged edit/apply/reload/quit behavior while preserving the existing projects workflow.
- `tests/test_resume_evidence.py`, `tests/test_resume_evidence_cli.py` - Added schema/load, session, startup, and CLI coverage for `skills.yaml`.
- `README.md`, `docs/architecture-overview.md`, `docs/branch-03-grounded-resume-generation.md`, `docs/agent-context-index.md`, `docs/CHANGELOG.md`, `docs/decisions/007-skills-evidence-bucketed-schema.md` - Documented the implemented `skills.yaml` contract, CLI usage, and architecture decision.

**Rationale:**
The request was to add skills evidence with minimal scope, so I kept the schema intentionally small: one strict file with categorized string lists and no per-skill metadata. The session and CLI mirror the existing staged-edit pattern because that already matches the repo’s safety model, but I avoided a broader generic abstraction pass so the diff stays focused and the existing projects flow remains stable.

**Tests:**
- `test_load_skills_yaml_returns_typed_runtime_object`: validates typed parsing for the new schema.
- `test_load_skills_yaml_rejects_*`: validates missing categories, extra fields, wrong bucket types, and unsupported schema versions.
- `test_load_registered_evidence_loads_registered_schemas`, `test_app_startup_loads_resume_evidence`: validate that both evidence files load into the runtime registry.
- `test_skills_session_*`: validate staged edit behavior, invalid edit rollback, apply persistence, and reload restoration.
- `test_skills_cli_*`: validate category listing, staged edit/apply flow, confirmation before write, reload discard flow, and quit warnings.
- Verification note: `python3 -m py_compile ...` passed for the touched Python files, but `pytest` collection is blocked locally because `pydantic` is not installed in this environment.

**Impact:**
ResumeCR7 now has a grounded, validated source of truth for resume skills in addition to projects. Future synthesis work can consume `resume_evidence["skills"]` without inventing a schema on the fly, and users can manage skills through the same staged CLI entrypoint they already use for projects.
