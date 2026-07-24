# 006 - Scoped Selection Runtime Config

## Context

ResumeCR7 now has both skill selection and project selection. The older runtime settings
`METHOD`, `TOP_N`, and `BASELINE_FILTER` were created when skill selection was the only
selection subsystem, so their names now imply application-wide behavior even though their
semantics are skill-specific.

Project selection also needs configurable defaults for its method and result count. Its
LLM path should be tunable separately from skill-selection LLM scoring because the two
prompts, schemas, and cost profiles can evolve independently.

## Decision

Use subsystem-scoped runtime settings:

- `SKILL_METHOD`, `SKILL_TOP_N`, and `SKILL_BASELINE_FILTER` control skill selection.
- `PROJ_METHOD` and `PROJ_TOP_N` control project selection.
- `SKILL_LLM_MODEL` and `SKILL_LLM_MAX_OUTPUT_TOKENS` control skill-selection LLM calls.
- `PROJ_LLM_MODEL` and `PROJ_LLM_MAX_OUTPUT_TOKENS` control project-selection LLM calls.
- `OPENAI_API_KEY` remains shared.

Legacy generic env vars are removed as configuration inputs. `METHOD`, `TOP_N`,
`BASELINE_FILTER`, `LLM_MODEL`, and `LLM_MAX_OUTPUT_TOKENS` are ignored rather than
treated as aliases.

Endpoint request payloads keep local field names such as `method` and `top_n` because the
route already scopes the request. Skill selection keeps `baseline_filter` as a request
field. Project selection does not add `PROJ_BASELINE_FILTER` because it has no defined
two-pass baseline-filter algorithm yet.

## Consequences

- `/health` reports scoped config under `skill_selection` and `project_selection`.
- Operators can tune skill and project defaults independently.
- Existing deployments must rename generic environment variables to scoped names.
- Metrics stay shape-compatible; subsystem buckets continue to attribute request counts,
  errors, token use, latency, and effective method usage.

## Alternatives Considered

- Keep generic env vars indefinitely as aliases: rejected because it preserves the
  ambiguity that caused the refactor.
- Prefix API request fields too: rejected because endpoint paths already scope request
  meaning and changing payload fields would create avoidable API churn.
- Add `PROJ_BASELINE_FILTER` as a no-op: rejected because a no-op setting would imply
  unsupported behavior and make project selection appear more mature than it is.
