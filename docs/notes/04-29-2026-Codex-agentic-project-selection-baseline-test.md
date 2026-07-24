# Agentic Project Selection Baseline Test - 04/29/2026

This test used the agentic testing dataset to evaluate the deterministic baseline method for `/select-projects`.

## Environment

- API base URL: `http://127.0.0.1:8001`
- Server command: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Runner command: `.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --base-url http://127.0.0.1:8001 --suite project_selection --variant baseline --output /tmp/resumecr7-project-baseline-agentic-results.json --fail-on-error`
- Health response: `status=ok`, `version=0.2.0`, `dev_mode=true`, skill config `method=baseline`, project config `method=llm`, project `top_n=null`
- Dataset: `docs/agentic-testing/dataset.json`

## Summary

Overall verdict: **Pass with concerns**.

Both baseline project-selection requests returned HTTP 200 with valid schema, grounded project IDs, `baseline` method labels, and no generated resume claims. The expected best-fit project ranked first in both dataset cases.

The main concern is score calibration. In the backend case, `resumecr7` and `vision-lab` tied at `0.75` even though `resumecr7` matched seven relevant skills and `vision-lab` matched only `Python`. The tie happens because the baseline skill score averages the strongest non-zero matches, so a single perfect match can receive the same normalized skill score as a project with many perfect matches. The deterministic tie-breaker still put `resumecr7` first, but the score does not communicate the much stronger evidence density.

The frontend case ranked `design-system` first correctly. The second slot was chosen by deterministic ordering between two zero-score projects, so `analytics-pipeline` ranked ahead of `resumecr7` only because both had no recognized baseline evidence and the name sorted first. That is acceptable for a weak runner-up slot, but the API should make zero-score ties easier to interpret.

## Results

### projects_backend_api

Review focus: select backend API evidence over visually impressive but less relevant frontend or ML projects.

Baseline request:

```json
{
  "context": {
    "title": "Backend Engineer",
    "description": "Build Python APIs with Django, PostgreSQL, Redis caching, authentication, Docker, Kubernetes, and AWS deployment."
  },
  "candidates": ["resumecr7", "design-system", "vision-lab"],
  "top_n": 2,
  "dev_mode": true,
  "method": "baseline"
}
```

Baseline response:

```json
{
  "selected_project_ids": ["resumecr7", "vision-lab"],
  "ranked_projects": [
    {"project_id": "resumecr7", "score": 0.75, "method": "baseline"},
    {"project_id": "vision-lab", "score": 0.75, "method": "baseline"}
  ]
}
```

`resumecr7` is the correct top match. Its details show strong backend/API evidence: `FastAPI`, `PostgreSQL`, `Docker`, `AWS`, `Python`, `API`, and `Authentication` matched, with seven matched skills and five considered top matches.

`vision-lab` is a weak but allowed runner-up because the dataset marks it as acceptable for the second slot. The concern is not the selected ID itself; it is the equal score. `vision-lab` matched only `Python`, yet received `skill_score=1.0` and final `score=0.75`, exactly like `resumecr7`. This makes a thin match look as strong as a dense match.

`design-system` scored `0.0`, which is appropriate for the backend job because the baseline found no backend-relevant matches in its React/Figma/accessibility evidence.

### projects_frontend_product

Review focus: select frontend/product evidence over backend infrastructure and ML projects.

Baseline request:

```json
{
  "context": {
    "title": "Frontend Product Engineer",
    "description": "Build accessible React and TypeScript product flows, integrate GraphQL APIs, improve performance, maintain design systems, and write UI tests."
  },
  "candidates": ["design-system", "resumecr7", "analytics-pipeline"],
  "top_n": 2,
  "dev_mode": true,
  "method": "baseline"
}
```

Baseline response:

```json
{
  "selected_project_ids": ["design-system", "analytics-pipeline"],
  "ranked_projects": [
    {"project_id": "design-system", "score": 0.78125, "method": "baseline"},
    {"project_id": "analytics-pipeline", "score": 0.0, "method": "baseline"}
  ]
}
```

`design-system` is the correct top match. It matched `React`, `TailwindCSS`, `JavaScript`, `TypeScript`, `Accessibility`, and `Design Systems`, with a small text-overlap boost from the project summary. The result is grounded and relevant to a frontend product role.

The runner-up is much weaker. `analytics-pipeline` and `resumecr7` both scored `0.0`, so the chosen second project comes from deterministic tie-breaking by normalized project name. This is schema-valid and predictable, but it means the second selected project carries no positive baseline evidence. The response details make that clear, which helps reviewability.

## Recommendations

- Must fix: none for schema, grounding, or method honesty.
- Should improve: adjust baseline project score calibration so one perfect skill match cannot tie a project with many strong matches. Include matched-skill density or considered-count coverage in the final score.
- Should improve: expose tie reasons more explicitly in `details`, especially when selected projects have zero scores.
- Nice to have: give job-text overlap a chance to recognize useful API-adjacent summary terms, or document that summary overlap is intentionally conservative.

## Raw Results Appendix

Raw run output was saved to `/tmp/resumecr7-project-baseline-agentic-results.json`.

Compact score details:

```json
{
  "projects_backend_api": {
    "selected_project_ids": ["resumecr7", "vision-lab"],
    "scores": {
      "resumecr7": {"score": 0.75, "skill_score": 1.0, "text_overlap_score": 0.0, "matched_skill_count": 7},
      "vision-lab": {"score": 0.75, "skill_score": 1.0, "text_overlap_score": 0.0, "matched_skill_count": 1},
      "design-system": {"score": 0.0, "skill_score": 0.0, "text_overlap_score": 0.0, "matched_skill_count": 0}
    }
  },
  "projects_frontend_product": {
    "selected_project_ids": ["design-system", "analytics-pipeline"],
    "scores": {
      "design-system": {"score": 0.78125, "skill_score": 1.0, "text_overlap_score": 0.125, "matched_skill_count": 6},
      "analytics-pipeline": {"score": 0.0, "skill_score": 0.0, "text_overlap_score": 0.0, "matched_skill_count": 0},
      "resumecr7": {"score": 0.0, "skill_score": 0.0, "text_overlap_score": 0.0, "matched_skill_count": 0}
    }
  }
}
```
