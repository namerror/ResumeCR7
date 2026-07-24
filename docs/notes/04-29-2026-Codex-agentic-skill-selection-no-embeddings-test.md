# Agentic Skill Selection Test - 04/29/2026

This test used the agentic testing dataset to evaluate `/select-skills` without running the embeddings method. The session ran the two skill-selection input sets with three variants each: baseline, LLM without baseline filter, and LLM with baseline filter.

## Environment

- API base URL: `http://127.0.0.1:8000`
- Server command: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Runner command: `.venv/bin/python docs/agentic-testing/run_agentic_dataset.py --suite skill_selection --exclude-variant embeddings_with_filter --output /tmp/resumecr7-skill-no-embeddings-results.json --fail-on-error`
- Health response: `status=ok`, `version=0.2.0`, default `method=llm`, default `top_n=5`, default `baseline_filter=false`, `dev_mode=true`
- Dataset: `docs/agentic-testing/dataset.json`

## Summary

Overall verdict: **Pass with concerns**.

All six selected requests returned HTTP 200. The API did not invent skills, did not move skills across categories, included `details` because `dev_mode=true`, and did not report any fallbacks or warnings. The LLM variants were generally stronger than baseline because they used more of the job text and selected more of the explicit strong anchors.

The main concern is that baseline-filtered LLM can preserve baseline choices that are weaker than the full LLM ranking. In the backend case it kept `C#`; in the frontend case it kept `Java`. Both are request-provided skills and category-correct, but they are weaker than `SQL` for backend and weaker than a stricter frontend language set.

Token/API usage for the four LLM-backed requests:

- API calls: 4
- Total tokens: 5,772
- `skills_backend_platform` LLM no filter: 1,727 tokens
- `skills_backend_platform` LLM with filter: 1,013 tokens
- `skills_frontend_product` LLM no filter: 1,685 tokens
- `skills_frontend_product` LLM with filter: 1,347 tokens

The baseline filter reduced tokens for both LLM cases: about 41% fewer tokens for backend and about 20% fewer tokens for frontend.

## Results

### skills_backend_platform

Review focus: backend/platform relevance, synonym normalization, and rejection of UI/game/data distractions.

Baseline request:

```json
{
  "job_role": "Backend Platform Engineer",
  "job_text": "Build reliable Python and Java services with REST APIs, PostgreSQL, Redis caching, Docker, Kubernetes, observability, authentication, rate limiting, and CI/CD on AWS.",
  "technology": ["React", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS", "Figma", "PyTorch", "Unity"],
  "programming": ["Python", "Java", "TypeScript", "C#", "Rust", "SQL"],
  "concepts": ["REST", "API", "Authentication", "Rate Limiting", "Caching", "CI/CD", "Observability", "UI Design", "Machine Learning"],
  "top_n": 4,
  "dev_mode": true,
  "method": "baseline",
  "baseline_filter": false
}
```

Baseline response:

```json
{
  "technology": ["AWS", "Django", "Docker", "Kubernetes"],
  "programming": ["C#", "Java", "Python"],
  "concepts": ["API", "Authentication", "REST"]
}
```

The baseline response is useful but incomplete. It correctly selected backend/platform technologies and ignored the major technology distractors (`React`, `Figma`, `PyTorch`, `Unity`). It also selected the strong concepts `API`, `Authentication`, and `REST`. The weak point is `C#`, which was identified as a programming distractor in the dataset anchors and is less supported by the job text than `SQL`. Baseline also omitted `PostgreSQL`, `Redis`, `Caching`, `CI/CD`, `Observability`, and `Rate Limiting` despite those appearing directly in the job text.

LLM without baseline filter request:

```json
{
  "job_role": "Backend Platform Engineer",
  "job_text": "Build reliable Python and Java services with REST APIs, PostgreSQL, Redis caching, Docker, Kubernetes, observability, authentication, rate limiting, and CI/CD on AWS.",
  "technology": ["React", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS", "Figma", "PyTorch", "Unity"],
  "programming": ["Python", "Java", "TypeScript", "C#", "Rust", "SQL"],
  "concepts": ["REST", "API", "Authentication", "Rate Limiting", "Caching", "CI/CD", "Observability", "UI Design", "Machine Learning"],
  "top_n": 4,
  "dev_mode": true,
  "method": "llm",
  "baseline_filter": false
}
```

LLM without baseline filter response:

```json
{
  "technology": ["AWS", "Docker", "Kubernetes", "PostgreSQL"],
  "programming": ["Java", "Python", "SQL", "TypeScript"],
  "concepts": ["API", "Authentication", "Caching", "CI/CD"]
}
```

This was the best backend result. It selected the core platform stack and included `SQL`, `Caching`, and `CI/CD`, all of which are directly grounded in the job text. It correctly left out the visual/game/data distractors. `TypeScript` is a weaker fourth programming choice, but it is more defensible than `C#` for service/API ecosystems when the candidate list is limited.

LLM with baseline filter request:

```json
{
  "job_role": "Backend Platform Engineer",
  "job_text": "Build reliable Python and Java services with REST APIs, PostgreSQL, Redis caching, Docker, Kubernetes, observability, authentication, rate limiting, and CI/CD on AWS.",
  "technology": ["React", "Django", "PostgreSQL", "Redis", "Docker", "Kubernetes", "AWS", "Figma", "PyTorch", "Unity"],
  "programming": ["Python", "Java", "TypeScript", "C#", "Rust", "SQL"],
  "concepts": ["REST", "API", "Authentication", "Rate Limiting", "Caching", "CI/CD", "Observability", "UI Design", "Machine Learning"],
  "top_n": 4,
  "dev_mode": true,
  "method": "llm",
  "baseline_filter": true
}
```

LLM with baseline filter response:

```json
{
  "technology": ["AWS", "Django", "Docker", "Kubernetes"],
  "programming": ["C#", "Java", "Python", "SQL"],
  "concepts": ["API", "Authentication", "Caching", "CI/CD"]
}
```

This result improved over baseline by adding `SQL`, `Caching`, and `CI/CD`, and it used fewer tokens than the unfiltered LLM. The downside is that baseline-filtered output preserved `C#` as a baseline-sourced high-score item even though the unfiltered LLM scored `C#` as not relevant. The filter details showed no fallback: technology recognized 6 and second-pass scored 4; programming recognized 3 and second-pass scored 3; concepts recognized 3 and second-pass scored 6.

### skills_frontend_product

Review focus: frontend/product relevance, category boundaries, and whether backend/cloud skills are deprioritized.

Baseline request:

```json
{
  "job_role": "Frontend Product Engineer",
  "job_text": "Create accessible TypeScript React interfaces with design systems, state management, performance profiling, GraphQL integration, testing, and close collaboration with designers.",
  "technology": ["React", "Next.js", "TailwindCSS", "Figma", "GraphQL", "Django", "Kubernetes", "AWS", "Pandas", "PostgreSQL"],
  "programming": ["TypeScript", "JavaScript", "Python", "Java", "SQL", "Go"],
  "concepts": ["Accessibility", "Design Systems", "State Management", "Performance Optimization", "Testing", "API", "Database Management", "Distributed Computing"],
  "top_n": 4,
  "dev_mode": true,
  "method": "baseline",
  "baseline_filter": false
}
```

Baseline response:

```json
{
  "technology": ["React", "TailwindCSS"],
  "programming": ["JavaScript", "TypeScript", "Java"],
  "concepts": ["Accessibility", "Design Systems", "State Management"]
}
```

The baseline response is category-correct and selects several strong frontend anchors, but it returned only two technology skills despite `top_n=4`. It omitted strong job-text technologies such as `Next.js`, `Figma`, and `GraphQL`, and included `Java`, which is a weak programming choice for this role.

LLM without baseline filter request:

```json
{
  "job_role": "Frontend Product Engineer",
  "job_text": "Create accessible TypeScript React interfaces with design systems, state management, performance profiling, GraphQL integration, testing, and close collaboration with designers.",
  "technology": ["React", "Next.js", "TailwindCSS", "Figma", "GraphQL", "Django", "Kubernetes", "AWS", "Pandas", "PostgreSQL"],
  "programming": ["TypeScript", "JavaScript", "Python", "Java", "SQL", "Go"],
  "concepts": ["Accessibility", "Design Systems", "State Management", "Performance Optimization", "Testing", "API", "Database Management", "Distributed Computing"],
  "top_n": 4,
  "dev_mode": true,
  "method": "llm",
  "baseline_filter": false
}
```

LLM without baseline filter response:

```json
{
  "technology": ["Figma", "GraphQL", "React", "Next.js"],
  "programming": ["JavaScript", "TypeScript", "SQL", "Go"],
  "concepts": ["Accessibility", "API", "Design Systems", "Performance Optimization"]
}
```

This was the best frontend result. It selected strong frontend/product technologies and concepts, avoided backend/cloud technology distractors (`Django`, `Kubernetes`, `AWS`, `Pandas`), and correctly prioritized `JavaScript` and `TypeScript`. `SQL` and `Go` are weaker programming selections, but they appear after the two core frontend languages and do not crowd them out.

LLM with baseline filter request:

```json
{
  "job_role": "Frontend Product Engineer",
  "job_text": "Create accessible TypeScript React interfaces with design systems, state management, performance profiling, GraphQL integration, testing, and close collaboration with designers.",
  "technology": ["React", "Next.js", "TailwindCSS", "Figma", "GraphQL", "Django", "Kubernetes", "AWS", "Pandas", "PostgreSQL"],
  "programming": ["TypeScript", "JavaScript", "Python", "Java", "SQL", "Go"],
  "concepts": ["Accessibility", "Design Systems", "State Management", "Performance Optimization", "Testing", "API", "Database Management", "Distributed Computing"],
  "top_n": 4,
  "dev_mode": true,
  "method": "llm",
  "baseline_filter": true
}
```

LLM with baseline filter response:

```json
{
  "technology": ["Figma", "GraphQL", "Next.js", "React"],
  "programming": ["JavaScript", "TypeScript", "Java", "SQL"],
  "concepts": ["Accessibility", "API", "Design Systems", "Performance Optimization"]
}
```

This result was strong overall and used fewer tokens than the unfiltered LLM. It selected the right frontend technologies and concepts. The concern is that baseline filtering preserved `Java`, while the unfiltered LLM scored `Java` as not relevant. The filter details showed no fallback: technology recognized 2 and second-pass scored 8; programming recognized 3 and second-pass scored 3; concepts recognized 3 and second-pass scored 5.

## Recommendations

- Treat unfiltered LLM as the best qualitative result for this no-embeddings skill-selection run.
- Keep baseline filter as a token-saving option, but review whether baseline-recognized weak programming skills such as `C#` for backend and `Java` for frontend should be allowed to bypass second-pass scoring.
- Improve the baseline method's coverage for exact job-text matches such as `PostgreSQL`, `Redis`, `Caching`, `CI/CD`, `Observability`, `Rate Limiting`, `Next.js`, `Figma`, and `GraphQL`.
- Keep the runner workflow. It produced a clean, reproducible result JSON at `/tmp/resumecr7-skill-no-embeddings-results.json`.

## Raw Result Excerpts

All six requests returned status code `200`.

```json
{
  "selected_count": 6,
  "skill_variants": [
    "skills_backend_platform/baseline",
    "skills_backend_platform/llm_no_filter",
    "skills_backend_platform/llm_with_filter",
    "skills_frontend_product/baseline",
    "skills_frontend_product/llm_no_filter",
    "skills_frontend_product/llm_with_filter"
  ],
  "warnings": [],
  "fallbacks": []
}
```
