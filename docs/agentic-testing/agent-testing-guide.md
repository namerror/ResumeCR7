# Agentic API Testing Guide

Use this guide when an agent runs the testing dataset against the local ResumeCR7 API and writes a human-style review report. The goal is not to prove the API is perfect. The goal is to make a careful, reproducible judgment about whether the returned selections are useful for a resume reviewer.

## Scope

Evaluate these endpoints:

- `POST /select-skills`
- `POST /select-projects`

Use `docs/agentic-testing/dataset.json` as the source of truth. The dataset is intentionally small: two skill-selection input sets and two project-selection input sets. Within each set, variants change only the method/options so an agent can compare behavior on the same underlying request.

## How To Run

1. Activate the repo virtual environment with `source .venv/bin/activate`, or call tools through `.venv/bin/...`.
2. Start the local API with `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.
3. Confirm `GET /health` returns `status: ok`.
4. Run the dataset with `docs/agentic-testing/run_agentic_dataset.py`.
5. Save the generated JSON output, then write a review report in the style of `docs/notes/`, with more explicit scoring and critique than the earlier human notes.

Examples:

```bash
.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --suite skill_selection --exclude-variant embeddings_with_filter --output /tmp/resumecr7-skill-results.json
```

```bash
.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --suite skill_selection --input-set skills_backend_platform --variant baseline --dry-run
```

The runner reads `dataset.json`, combines each input set's `base_payload` with the selected variant fields, posts to the suite `endpoint`, and records status codes, response bodies, and request payloads.

Manual REST clients can still use this sequence:

1. Start the local API.
2. Confirm `GET /health` returns `status: ok`.
3. For every dataset input set, run each listed variant.
4. Save the full request payload, response body, status code, and any runtime error.
5. Write the review report.

For model-backed variants, record whether the response used the requested method or fell back to baseline. A fallback is acceptable if it is clearly reported in `details`, but it should be called out because it changes what was actually tested.

In the report body, include the request payload next to each response being evaluated. The request can be compact, but it should show enough fields to make the method, options, candidate inputs, and job context readable without opening the raw JSON result file.

## Skill-Selection Review Criteria

For each skill-selection response, check:

- **Schema validity:** response has `technology`, `programming`, and `concepts` arrays; `details` appears when `dev_mode` is true.
- **No invented skills:** every selected skill must come from the request payload for its own category.
- **Category boundaries:** technology selections stay in `technology`, languages stay in `programming`, and ideas/practices stay in `concepts`.
- **Job relevance:** selected skills are defensible for the job role and job text.
- **Distractor handling:** obvious weak skills from `expected_review_anchors.weak_or_distractor` should not crowd out stronger matches.
- **Ordering quality:** higher-ranked selected skills should generally be more central to the job than lower-ranked selected skills.
- **Baseline-filter behavior:** when `baseline_filter` is true for model-backed methods, inspect `details` for a mix of baseline/model sources and note whether the final selection improves, degrades, or stays similar.
- **Fallback transparency:** if `llm` or `embeddings` falls back to baseline, the report must say so and evaluate the returned baseline result separately.

Do not require exact equality with `expected_review_anchors.strong`. Those anchors are review aids, not golden outputs.

## Project-Selection Review Criteria

For each project-selection response, check:

- **Schema validity:** response has `selected_project_ids`, `ranked_projects`, and optional `details`.
- **No invented project IDs:** every selected or ranked ID must exist in the request candidates.
- **Top match quality:** the expected `best_fit` project should normally rank first.
- **Runner-up rationale:** when `top_n` is greater than one, explain whether the second project is a reasonable weaker fit.
- **Method honesty:** each ranked project has a method of `baseline` or `llm`; if an LLM request falls back, the ranked method should show the effective scorer.
- **Content discipline:** the endpoint should return project IDs and scores, not generated resume claims.
- **Tie and score sanity:** if scores are equal or surprising, use `details` to explain whether deterministic ordering or scorer limitations caused the result.

## Report Template

```markdown
# Agentic API Test Report - YYYY-MM-DD

## Environment
- API base URL:
- App version and scoped selection config from `/health`:
- Model-related environment, if known:
- Dataset file and revision:

## Summary
- Overall verdict:
- Main strengths:
- Main concerns:
- Fallbacks observed:

## Skill Selection
### skills_backend_platform
- Variants run:
- Request/response pairs:
- Best response:
- Issues:
- Notes on baseline filter:

### skills_frontend_product
- Variants run:
- Request/response pairs:
- Best response:
- Issues:
- Notes on baseline filter:

## Project Selection
### projects_backend_api
- Variants run:
- Request/response pairs:
- Best response:
- Issues:
- Ranking rationale:

### projects_frontend_product
- Variants run:
- Request/response pairs:
- Best response:
- Issues:
- Ranking rationale:

## Recommendations
- Must fix:
- Should improve:
- Nice to have:

## Raw Results Appendix
Include compact JSON excerpts or links to saved result files. The main report sections should still contain readable request/response pairs for each evaluated case.
```

## Suggested Verdict Scale

- **Pass:** selections are relevant, grounded in request data, and method/fallback behavior is transparent.
- **Pass with concerns:** core output is usable, but there are questionable rankings, weak distractor handling, or unclear details.
- **Fail:** invented items, wrong categories, unusable rankings, hidden fallback, invalid schema, or repeated runtime failures.

## Review Style

Be critical but concrete. Prefer statements like "React ranked above Django for the backend case even though the job text emphasizes Python APIs and Kubernetes" over vague judgments like "ranking looks bad." When a result is acceptable, explain why using the job text and candidate evidence.
