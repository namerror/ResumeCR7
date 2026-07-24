# Agentic Resume Generation Test Report - 2026-07-08

## Environment

- Pipeline under test: `resume_generation.run_resume_generation_pipeline`
- Job target: `user/resume_generation/job_target.yaml`
- Evidence root: `user/resume_evidence/`
- API health: `version=0.2.0`, `service=resumecr7-resume-engine`, `dev_mode=true`
- Local API: `http://127.0.0.1:8765`
- Final artifact inspected: `user/resume_generation/resume_result.json`
- LaTeX output: intentionally not inspected

The default port `8000` was not bindable from the sandboxed session, so the API was started outside the sandbox on port `8765`. I used a temporary config at `/tmp/resumecr7-resume-generation-config.yaml` to avoid modifying `user/resume_generation/config.yaml`.

## Summary

- Overall verdict: **Pass with concerns**
- The full pipeline produced a schema-valid intermediate JSON artifact after temporary runtime tuning.
- The default/current runtime path was brittle: project bullet generation failed with malformed JSON at the effective 1200-token default, and the next run hit the 30-second HTTP timeout during experience bullet generation.
- The final artifact is not self-auditing. It contains the resume sections only, not stage metadata, method/fallback details, token usage, request payloads, or source cache keys.

## Run History

1. **Current config shape, alternate port/cache only**
   - Effective bullet max output tokens: API default `1200`
   - Result: failed during `project_bullet_points`
   - Error: `/generate-bulletpoints` returned 502 because the LLM response was malformed JSON: `Unterminated string starting at: line 1 column 535`

2. **Temporary bullet-token increase**
   - Changed only temp config bullet stages to `llm_max_output_tokens: 3000`
   - Result: passed project bullets, then failed during `experience_bullet_points`
   - Error: client read timeout at `timeout_seconds: 30`

3. **Temporary bullet-token increase plus longer HTTP timeout**
   - Changed temp config `timeout_seconds: 120`
   - Result: complete pipeline succeeded and wrote `user/resume_generation/resume_result.json`

## Artifact Shape

The artifact validates against `IntermediateResumeResult`.

- Top section: present
- Education items: 1
- Experience items: 6
- Project items: 5
- Skills section: present

Selected skills in the artifact:

```json
{
  "technology": ["Docker", "Git", "Google Cloud", "Linux", "PyTorch", "TensorFlow"],
  "programming": ["C", "C#", "C++", "Java", "JavaScript", "Python"],
  "concepts": ["Deep Learning"]
}
```

## Selection Assessment

Skill selection was requested as `llm`, but the stage fell back to `baseline` because the LLM response did not include `output_text`. The fallback was visible in the cache, not the final artifact.

The baseline result is weak for this target. It correctly includes `Python`, `Docker`, `Linux`, and `Git`, but misses `FastAPI`, `RestAPI`, `API`, `Caching`, and `Database Management` despite the job emphasizing Python MCP servers, APIs, Docker, Linux, configuration, and local testing. It also includes broad or distractor skills such as `C`, `C#`, `Java`, `PyTorch`, `TensorFlow`, and `Deep Learning`.

Project selection used `llm` successfully. Ranking:

1. `capital-ready-business-lending-tool` - score 1.0
2. `resume-generator` - score 1.0
3. `2d-slam-robot` - score 0.333
4. `hackproof-decentralized-reputation-system-for-hackers` - score 0.333
5. `kim-1-trivia-game` - score 0.333

The top two projects are defensible for a Python/API/backend target. Because `top_n` is `null`, all five active projects are included, including weak fits. That makes the resulting resume less targeted.

## Bullet Assessment

All generated project and experience sections contain exactly three bullets, matching the default bullet count. The output is generally readable and grounded in the supplied evidence, but several bullets polish beyond the literal evidence:

- Capital Ready says Docker deployment/configuration artifacts were created and workflows were validated. Docker and workflows are evidenced, but deployment/configuration artifact creation is not explicit.
- DATEV frontend says the app surfaced test logs and metrics. The LogReporter/testing context is evidenced, but metrics are not explicit in the source highlight.
- Resume Generator says the service exposes resume-generation APIs. That is consistent with the repo context, but the project evidence itself is sparse.
- Weak-fit projects such as HackProof and KIM-1 receive polished bullets even though the project-selection stage scored them low for this target.

The experience bullets are stronger overall. The Secunet, Krastanov Lab, DARoS, and UMass research bullets mostly preserve source claims while improving phrasing. Some wording is more polished than the evidence, but I did not see clear invented employers, tools, or metrics.

## Token And Runtime Notes

Successful cached stage totals:

- Project selection: 1 LLM call, 1,765 tokens
- Project bullet generation: 5 LLM calls, 9,256 tokens
- Experience bullet generation: 6 LLM calls, 11,035 tokens

This excludes failed calls and the failed skill-selection LLM attempt. The successful full run therefore used at least 22,056 successful response tokens across cached stages.

## Recommendations

Must fix:

- Make bullet generation robust to truncated or malformed JSON responses. Options: higher default output budget, retry on JSON parse failure, or use a response parser path that can detect incomplete model output before returning 502.
- Align pipeline `timeout_seconds` with expected model latency. A 30-second per-request timeout is too low for some current `gpt-5-mini` bullet calls.
- Include method/fallback metadata in `resume_result.json` or write a companion run manifest. The final artifact alone hides that skill selection fell back to baseline.

Should improve:

- Investigate why `gpt-5-mini` skill selection returned no `output_text`; project and bullet stages returned usable text under similar API usage.

Nice to have:

- Record cache keys and stage timings in the reportable artifact.
- Add an agentic runner for the resume-generation pipeline that saves config, raw stage responses, final JSON, and a short machine-readable verdict.
- While currently bullet point is exactly 3 per item, consider making it flexible. This would allow LLM to generate more bullets for projects with more evidence and fewer for those with less, improving the overall quality of the resume.
