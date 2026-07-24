### 2026-07-16 - Document FastAPI Resume Service Transition

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md:1-11` - Reframed ResumeCR7 as a resume-generation prototype transitioning into a FastAPI-backed resume service.
- `README.md:147-206` - Added the recommended service architecture: product-facing facade, internal capability APIs, file-backed storage adapter transition, and async generation runs.
- `README.md:208-239` - Updated local resume-generation usage to include job-focus generation and standalone link enrichment.
- `README.md:499-515` - Replaced the stale planned-next list with service-integration next steps and linked ADR 012.
- `docs/architecture-overview.md:1-193` - Updated subsystem maps, startup flow, and local generation flow for the current evidence and generation implementation.
- `docs/architecture-overview.md:327-423` - Replaced future-only pipeline wording with current pipeline behavior and the planned service facade direction.
- `docs/agent-context-index.md:12-113` - Refreshed the recommended agent read path and marked archived branch planning docs as historical background.
- `docs/decisions/012-fastapi-resume-service-transition.md:1-60` - Added an ADR for continuing with FastAPI, adding facade APIs, treating stage routes as internal capabilities, keeping file-backed storage behind adapters, and using async generation runs.
- `docs/decisions/README.md:65` - Indexed ADR 012.

**Rationale:**
The docs still mixed early skill-selection framing, standalone prototype language, and current resume-generation implementation details. The update makes the current architecture explicit while recommending a conservative path to an actual backend service: keep the working FastAPI capability layer, add a product-facing facade, preserve file-backed local mode behind adapters, and avoid early database dependencies.

**Tests:**
- `rg` stale-doc check: verified README, architecture overview, and agent index no longer reference removed top-level branch plan paths or obsolete future-only generation wording.
- `rg` service-transition check: verified README, architecture overview, agent index, decisions README, and ADR 012 all reference the new service-transition guidance.

**Impact:**
Future work has a clearer target architecture for integrating `resume_evidence/` and `resume_generation/` into the FastAPI backend without prematurely committing to database persistence or exposing low-level generation stages as the final product API.
