# 009. Bullet Point Generation API Boundary

Date: 2026-06-05

## Status

Accepted

## Context

ResumeCR7 already has FastAPI-backed skill and project selection capabilities plus a top-level
`resume_generation/` orchestration package. The next grounded resume milestone needs a
minimal prose-generation capability that can refine a selected project into tailored resume
bullet points without turning the whole system into full resume synthesis.

This is the first model-backed writer in the service. It must stay grounded in user-authored
project evidence, expose a small API contract, and avoid unsupported link scanning or broad
resume assembly concerns.

## Decision

Add `app/bulletpoints_generation/` as a FastAPI service subsystem for project bullet-point
generation.

- The public endpoint is `POST /generate-bulletpoints`.
- Requests include a job target, a full `ProjectRecord`, an optional bullet-count range, and
  optional LLM/runtime overrides.
- Responses return plain bullet strings plus optional dev metadata.
- The OpenAI Responses API call uses strict JSON schema output and local validation for count
  range and bullet shape.
- If the LLM call or response cannot be used, the endpoint returns an HTTP error instead of a
  deterministic prose fallback.
- Link scanning is represented as config and request surface area, but v1 rejects enabled
  scanning because fetching external link contents is not implemented.

## Consequences

### Positive

- Establishes a narrow, testable boundary for the first grounded prose-generation feature.
- Keeps bullet writing separate from selection scoring and full resume assembly.
- Preserves observability through subsystem metrics, token tracking, health output, and dev
  metadata.

### Negative

- Generation requests need an OpenAI API key and have no deterministic fallback.
- Grounding is enforced through prompt design and local response-shape validation, not through
  semantic claim verification.
- The API exposes link-scanning controls before the scanning implementation exists.

### Neutral

- `ProjectRecord` remains the evidence contract for project-level generation.
- The top-level `resume_generation/` package can call this API later, but this decision does
  not wire it into orchestration yet.

## Alternatives Considered

- Put bullet generation directly in `resume_generation/`: rejected for v1 because the existing
  service pattern exposes reusable API capabilities first.
- Fall back to original highlights on LLM failure: rejected because unchanged highlights could
  hide generation failure and may not satisfy the requested target/count.
- Fetch project links in v1: deferred because network scanning needs separate timeout,
  extraction, security, and provenance decisions.
