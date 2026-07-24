# 012. FastAPI Resume Service Transition

Date: 2026-07-16

## Status

Accepted

## Context

ResumeCR7 started as a skill-selection API and has since grown into a grounded resume engine. The repo now has three important layers:

- `app/` exposes FastAPI-backed selection, focus derivation, bullet generation, link enrichment, health, and metrics capabilities.
- `resume_evidence/` owns strict user-authored evidence schemas, deterministic loading, staged CRUD/session logic, and the local evidence CLI.
- `resume_generation/` owns orchestration that loads evidence and job targets, calls FastAPI capabilities, caches stage responses, assembles an intermediate resume result, and writes local artifacts.

The current local `user/` tree is useful for prototype evidence, run config, caches, and generated artifacts. It is not enough by itself for a multi-user product. At the same time, adding a database before the service boundary is stable would add avoidable complexity and violate the repo's current guardrail against early persistence dependencies.

The next architecture needs to support a future web app while preserving the implemented local pipeline and current FastAPI capabilities.

## Decision

Continue using FastAPI as the backend service foundation and introduce a product-facing facade over evidence and resume generation.

- Keep `app/` as the backend capability layer for selection, focus derivation, bullet generation, link enrichment, health, and metrics.
- Keep `resume_evidence/` as the evidence domain layer for schema contracts, validation, deterministic loading, and local staged CRUD behavior.
- Keep `resume_generation/` as the orchestration layer that decides which evidence is sent to which backend capability and assembles returned data.
- Treat current stage endpoints such as `/select-skills`, `/select-projects`, `/derive-job-focus`, `/generate-bulletpoints`, `/scan-link`, and `/enrich-link-evidence` as internal capability APIs as the product API matures.
- Add future product-facing APIs for evidence CRUD, generation-run creation, generation-run status, structured resume result retrieval, and rendered artifact retrieval.
- Use async generation runs for the product API: create a run, poll status, then fetch result/artifacts.
- Keep file-backed `user/` storage for local mode, but introduce repository/adapter interfaces before adding database-backed persistence.

## Consequences

### Positive

- Preserves the working local pipeline while giving a clear path toward a web-app backend.
- Prevents product clients from depending on low-level stage orchestration details.
- Keeps FastAPI as the integration point instead of splitting product and prototype backends.
- Allows database persistence to be added later behind adapters instead of forcing an early schema commitment.
- Makes long-running LLM-backed generation safer for web clients through async run lifecycle APIs.

### Negative

- Requires an additional facade/API layer instead of exposing existing routes directly as the final product API.
- Requires a storage adapter abstraction before durable multi-user persistence is introduced.
- Keeps two modes in the near term: local file-backed orchestration and planned service-backed product flows.

### Neutral

- Existing stage endpoints remain useful for tests, internal orchestration, and development.
- This decision does not remove or rename any current endpoint.
- This decision does not introduce auth, user accounts, queues, workers, or database dependencies yet.

## Alternatives Considered

- Expose all current stage endpoints as the product API: rejected because clients would need to coordinate prompt-stage payloads, retries, cache behavior, and assembly order.
- Rewrite around a database now: rejected because the product boundary is still evolving and the repo explicitly avoids early database dependencies.
- Keep the project CLI/local-only for longer: rejected because the repo is now moving toward an actual backend service for a resume-generation product.
- Make full generation a synchronous HTTP request: rejected for product use because multiple LLM-backed stages can exceed comfortable request lifetimes and need run status, retries, and artifact retrieval.
