### 2026-07-26 - Document Token Budgeting In README

**Agent:** Codex (GPT-5)

**Changes:**
- `README.md:318-330` - Added a brief note explaining dynamic resume-generation output token budgets, optional `max` caps, and direct `llm_max_output_tokens` overrides.

**Rationale:**
The backend now uses per-request dynamic output token sizing for project selection and bullet generation. The README needed a concise user-facing explanation near the configuration section so users understand where defaults live and when to use overrides.

**Tests:**
- Not run; documentation-only change.

**Impact:**
Users can see how token budgeting behaves without reading backend implementation details.
