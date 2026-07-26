### 2026-07-26 - Config Page and OpenAI Setup

**Agent:** Codex (GPT-5)

**Changes:**
- `app/resume_generation/api.py:117-241` - Added masked config response and patch models plus `GET`/`PATCH /resume-generation/config`.
- `app/resume_generation/api.py:289-407` - Added config patch application, default/null display metadata, API-key source reporting, and loopback/HTTPS enforcement for key updates.
- `app/resume_generation/config.py:36-139` - Added full default config payload generation, deep default filling, validation-before-write, and atomic config YAML writes.
- `app/resume_generation/models.py` and `app/config.py` - Aligned backend defaults to `user/resume_generation/config.yaml` and added `openai.api_key` support.
- `app/*/llm_client.py` and `app/skill_selection/embedding_client.py` - Switched OpenAI clients to environment-first, config-YAML fallback key resolution.
- `frontend/src/App.tsx:102-250` - Loaded config beside evidence, tracked config dirty state, and applied config patches through the same staged workflow.
- `frontend/src/App.tsx:957-1125` - Added the Config page with exposed count controls, shared bullet range controls, and a password-style OpenAI key field.
- `frontend/src/api.ts`, `frontend/src/types.ts`, and `frontend/src/validation.ts` - Added config API client methods, TypeScript contracts, and frontend integer/range validation.
- `user/resume_generation/config.yaml` - Added the `openai.api_key` key with a `null` default.
- `docs/decisions/018-local-generation-config-api.md` and `docs/CHANGELOG.md` - Documented the local config API decision and user-facing addition.

**Rationale:**
The implementation mirrors the existing evidence YAML pattern: the backend owns validation and atomic writes, while the frontend stages edits and applies them intentionally. Only selected config fields are exposed in the UI, but patching starts from the current YAML payload so advanced hidden settings survive frontend saves. The OpenAI key is stored locally when requested, redacted from reads, and only sent in JSON over HTTPS or local loopback requests.

**Tests:**
- `test_resume_generation_config_get_redacts_openai_key`: validates config reads expose status without returning the secret.
- `test_resume_generation_config_patch_preserves_hidden_yaml_values`: verifies exposed frontend edits preserve hidden YAML fields and update both bullet count sections.
- `test_resume_generation_config_patch_replaces_and_clears_openai_key`: covers key replacement, redaction, and clearing.
- `test_resume_generation_config_rejects_api_key_update_over_remote_http`: enforces secure transport for key writes.
- Frontend App tests cover default/null labels, password input behavior, config patch generation, and invalid bullet range blocking.

**Impact:**
New users get a complete default `config.yaml` and a local UI for common generation settings and OpenAI setup. Existing users keep manual YAML control for advanced options, and older partial config files are filled with current defaults without replacing their chosen values.
