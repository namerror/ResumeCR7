from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.bulletpoints_generation import llm_client as bullet_llm_client
from app.bulletpoints_generation.llm_client import (
    BulletPointLLMClientError,
    build_bulletpoint_instructions,
    build_bulletpoint_prompt_payload,
    build_bulletpoint_schema,
    build_resume_section_bulletpoint_instructions,
    build_resume_section_bulletpoint_prompt_payload,
    build_resume_section_bulletpoint_schema,
    generate_bulletpoints_with_llm,
    generate_bulletpoints_with_llm_async,
    generate_resume_section_bulletpoints_with_llm,
    resolve_bulletpoint_max_output_tokens,
)
from app.bulletpoints_generation.models import BulletCountRange, BulletJobContext
from app.job_focus_generation.models import JobFocus
from resume_evidence.models import ExperienceRecord, ProjectRecord, ProjectSkills


def _project() -> ProjectRecord:
    return ProjectRecord(
        id="resumecr7",
        name="ResumeCR7",
        summary="FastAPI resume engine for grounded resume generation.",
        highlights=[
            "Built project and skill selection APIs with deterministic fallbacks.",
            "Added strict resume evidence parsing for user-authored project data.",
        ],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI", "OpenAI"],
            programming=["Python"],
            concepts=["API", "Grounded Generation"],
        ),
        links=["https://example.com/resumecr7"],
    )


def _experience() -> ExperienceRecord:
    return ExperienceRecord(
        id="backend-engineer",
        name="Example Company",
        role="Backend Engineer",
        summary="Built backend services for internal platforms.",
        highlights=[
            "Designed schema-validated APIs.",
            "Maintained automated tests for backend services.",
        ],
        active=True,
        skills=ProjectSkills(
            technology=["FastAPI"],
            programming=["Python"],
            concepts=["API", "Testing"],
        ),
        location="Example City, ST",
        start="2024",
        end=None,
        links=["https://example.com/company"],
    )


def test_build_bulletpoint_schema_uses_strict_count_range():
    schema = build_bulletpoint_schema(BulletCountRange(min=2, max=4))

    bullet_schema = schema["properties"]["bullet_points"]
    assert bullet_schema["minItems"] == 2
    assert bullet_schema["maxItems"] == 4
    assert schema["required"] == ["bullet_points"]
    assert schema["additionalProperties"] is False


def test_build_bulletpoint_instructions_distinguishes_exact_and_flexible_counts():
    exact = build_bulletpoint_instructions(BulletCountRange(min=3, max=3))
    flexible = build_bulletpoint_instructions(BulletCountRange(min=2, max=4))
    experience = build_bulletpoint_instructions(
        BulletCountRange(min=1, max=1),
        evidence_type="experience",
    )

    assert "Return exactly 3 bullet point strings." in exact
    assert "Return between 2 and 4 bullet point strings" in flexible
    assert "raw factual notes" in exact
    assert "do not copy the evidence wording, structure, or tone" in exact
    assert "past-tense action verb" in exact
    assert "Use past-tense action verbs for all bullets" in exact
    assert "action + purpose/context + method/tool + supported impact" in exact
    assert "Target 18 to 26 words and never exceed 32 words" in exact
    assert "Prefer quantified impact when the evidence supports it" in exact
    assert "Never invent percentages, speedups, uptime, counts" in exact
    assert "Treat numeric_evidence as high-value source material" in exact
    assert "make the first bullet explain what the project/system does" in exact
    assert "Do not use semicolons" in exact
    assert "Do not use internal dash separators" in exact
    assert "Vary the opening verbs across bullets" in exact
    assert "Use plain ASCII text only" in exact
    assert "pdfLaTeX" in exact
    assert "approximation signs" in exact
    assert "present-tense verbs for active/current work" not in exact
    assert "completed work when the evidence makes timing clear" not in exact
    assert "experience evidence" in experience


def test_build_bulletpoint_prompt_payload_excludes_links():
    payload = json.loads(
        build_bulletpoint_prompt_payload(
            context=BulletJobContext(title="Backend Engineer", description="Build APIs."),
            project=_project(),
            count_range=BulletCountRange(min=2, max=4),
        )
    )

    assert payload["job"]["title"] == "Backend Engineer"
    assert payload["project"]["highlights"][0].startswith("Built project")
    assert payload["project"]["skills"]["programming"] == ["Python"]
    assert "active" not in payload["project"]
    assert "links" not in payload["project"]
    assert "https://example.com/resumecr7" not in json.dumps(payload)


def test_build_bulletpoint_prompt_payload_extracts_numeric_evidence():
    project = _project().model_copy(
        update={
            "highlights": [
                "Maintained 97% uptime for content workflows.",
                "Increased online engagement by 400% after launch.",
            ]
        }
    )
    payload = json.loads(
        build_bulletpoint_prompt_payload(
            context=BulletJobContext(title="AI Engineer"),
            project=project,
            count_range=BulletCountRange(min=2, max=2),
        )
    )

    assert payload["project"]["numeric_evidence"] == [
        "Maintained 97% uptime for content workflows.",
        "Increased online engagement by 400% after launch.",
    ]
    assert any(
        "Preserve exact metrics from numeric_evidence" in rule
        for rule in payload["grounding_rules"]
    )
    assert any("Do not invent percentages" in rule for rule in payload["grounding_rules"])


def test_build_bulletpoint_prompt_payload_prefers_job_focus_over_description():
    payload = json.loads(
        build_bulletpoint_prompt_payload(
            context=BulletJobContext(
                title="Backend Engineer",
                description="Full posting with benefits and culture.",
                job_focus=JobFocus(
                    summary="Python API role.",
                    required_skills=["Python", "FastAPI"],
                    preferred_skills=["Docker"],
                    responsibilities=["Build REST APIs"],
                    domain_emphasis=["Backend platforms"],
                    resume_relevant_constraints=["Remote collaboration"],
                    excluded_context=["Benefits and culture"],
                ),
            ),
            project=_project(),
            count_range=BulletCountRange(min=2, max=4),
        )
    )

    assert payload["job"]["title"] == "Backend Engineer"
    assert payload["job"]["focus"]["required_skills"] == ["Python", "FastAPI"]
    assert "description" not in payload["job"]
    assert "Full posting" not in json.dumps(payload)


def test_build_bulletpoint_prompt_payload_supports_experience_evidence():
    payload = json.loads(
        build_bulletpoint_prompt_payload(
            context=BulletJobContext(title="Backend Engineer", description="Build APIs."),
            experience=_experience(),
            count_range=BulletCountRange(min=1, max=2),
        )
    )

    assert payload["job"]["title"] == "Backend Engineer"
    assert payload["experience"]["id"] == "backend-engineer"
    assert payload["experience"]["role"] == "Backend Engineer"
    assert payload["experience"]["location"] == "Example City, ST"
    assert payload["experience"]["skills"]["concepts"] == ["API", "Testing"]
    assert "active" not in payload["experience"]
    assert "start" not in payload["experience"]
    assert "end" not in payload["experience"]
    assert "project" not in payload
    assert "links" not in payload["experience"]
    assert "https://example.com/company" not in json.dumps(payload)
    assert "experience evidence" in payload["grounding_rules"][0]


def test_build_resume_section_bulletpoint_prompt_payload_includes_all_selected_records():
    project_range = BulletCountRange(min=2, max=3)
    experience_range = BulletCountRange(min=1, max=2)
    payload = json.loads(
        build_resume_section_bulletpoint_prompt_payload(
            context=BulletJobContext(title="Backend Engineer", description="Build APIs."),
            projects=[_project()],
            experiences=[_experience()],
            project_count_range=project_range,
            experience_count_range=experience_range,
        )
    )

    assert payload["job"]["title"] == "Backend Engineer"
    assert payload["projects"][0]["id"] == "resumecr7"
    assert payload["experiences"][0]["id"] == "backend-engineer"
    assert payload["bullet_count_ranges"]["projects"] == {"min": 2, "max": 3}
    assert payload["bullet_count_ranges"]["experiences"] == {"min": 1, "max": 2}
    assert "active" not in payload["projects"][0]
    assert "active" not in payload["experiences"][0]
    assert "start" not in payload["experiences"][0]
    assert "end" not in payload["experiences"][0]
    assert "links" not in payload["projects"][0]
    assert "links" not in payload["experiences"][0]


def test_build_resume_section_bulletpoint_schema_uses_record_ids_and_ranges():
    schema = build_resume_section_bulletpoint_schema(
        project_ids=["resumecr7"],
        experience_ids=["backend-engineer"],
        project_count_range=BulletCountRange(min=2, max=3),
        experience_count_range=BulletCountRange(min=1, max=2),
    )

    project_items = schema["properties"]["project_bullet_points"]
    experience_items = schema["properties"]["experience_bullet_points"]
    assert project_items["minItems"] == 1
    assert project_items["items"]["properties"]["project_id"]["enum"] == ["resumecr7"]
    assert project_items["items"]["properties"]["bullet_points"]["maxItems"] == 3
    assert experience_items["items"]["properties"]["experience_id"]["enum"] == [
        "backend-engineer"
    ]
    assert experience_items["items"]["properties"]["bullet_points"]["minItems"] == 1


def test_build_resume_section_bulletpoint_instructions_set_global_style_rules():
    instructions = build_resume_section_bulletpoint_instructions(
        project_count_range=BulletCountRange(min=2, max=3),
        experience_count_range=BulletCountRange(min=1, max=2),
    )

    assert "past-tense action verb" in instructions
    assert "Do not infer tense from eligibility, dates, or record status" in instructions
    assert "active or current roles" not in instructions
    assert "Every bullet must end with terminal punctuation" in instructions
    assert "vary opening verbs across all bullets" in instructions
    assert "avoid overusing develop, implement, build" in instructions
    assert "avoid repeating ', enabling ...'" in instructions
    assert "Prefer quantified impact when the evidence supports it" in instructions
    assert "Never invent percentages, speedups, uptime, counts" in instructions


def test_generate_bulletpoints_with_llm_sends_strict_schema(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "bullet_points": [
                            "Built FastAPI APIs for grounded resume generation.",
                            "Validated user-authored project evidence for tailored resumes.",
                        ]
                    }
                ),
                usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(bullet_llm_client.settings, "BULLETPOINTS_LLM_MODEL", "test-model")

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=2, max=4),
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert kwargs["max_output_tokens"] > 3000
    assert kwargs["text"]["format"]["name"] == "project_bullet_points"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["schema"]["properties"]["bullet_points"]["minItems"] == 2
    assert json.loads(kwargs["input"])["project"]["id"] == "resumecr7"
    assert result.bullet_points[0].startswith("Built FastAPI")
    assert result.metadata["total_tokens"] == 30
    assert result.metadata["resolved_llm_max_output_tokens"] == kwargs["max_output_tokens"]
    assert result.metadata["llm_output_token_budget_mode"] == "dynamic"


def test_generate_bulletpoints_with_llm_adds_missing_terminal_period(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text=json.dumps({"bullet_points": ["Built FastAPI services"]}),
                usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=1, max=1),
    )

    assert result.bullet_points == ["Built FastAPI services."]


def test_generate_resume_section_bulletpoints_with_llm_validates_ids_and_punctuation(
    monkeypatch,
):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "project_bullet_points": [
                            {
                                "project_id": "resumecr7",
                                "bullet_points": [
                                    "Built FastAPI APIs for grounded resume workflows"
                                ],
                            }
                        ],
                        "experience_bullet_points": [
                            {
                                "experience_id": "backend-engineer",
                                "bullet_points": [
                                    "Designed backend APIs for internal platforms"
                                ],
                            }
                        ],
                    }
                ),
                usage=SimpleNamespace(input_tokens=40, output_tokens=20, total_tokens=60),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(bullet_llm_client.settings, "BULLETPOINTS_LLM_MODEL", "test-model")

    result = generate_resume_section_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        projects=[_project()],
        experiences=[_experience()],
        project_count_range=BulletCountRange(min=1, max=1),
        experience_count_range=BulletCountRange(min=1, max=1),
    )

    assert captured["kwargs"]["text"]["format"]["name"] == "resume_section_bullet_points"
    assert json.loads(captured["kwargs"]["input"])["projects"][0]["id"] == "resumecr7"
    assert result.project_bullet_points[0].project_id == "resumecr7"
    assert result.project_bullet_points[0].bullet_points == [
        "Built FastAPI APIs for grounded resume workflows."
    ]
    assert result.experience_bullet_points[0].experience_id == "backend-engineer"
    assert result.experience_bullet_points[0].bullet_points == [
        "Designed backend APIs for internal platforms."
    ]
    assert result.metadata["total_tokens"] == 60


def test_generate_resume_section_bulletpoints_with_llm_rejects_unknown_ids(
    monkeypatch,
):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "project_bullet_points": [
                            {
                                "project_id": "invented-project",
                                "bullet_points": ["Invented unsupported project."],
                            }
                        ],
                        "experience_bullet_points": [
                            {
                                "experience_id": "backend-engineer",
                                "bullet_points": ["Designed backend APIs."],
                            }
                        ],
                    }
                ),
                usage=SimpleNamespace(input_tokens=40, output_tokens=20, total_tokens=60),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(BulletPointLLMClientError, match="Unknown project id"):
        generate_resume_section_bulletpoints_with_llm(
            context=BulletJobContext(title="Backend Engineer"),
            projects=[_project()],
            experiences=[_experience()],
            project_count_range=BulletCountRange(min=1, max=1),
            experience_count_range=BulletCountRange(min=1, max=1),
        )


def test_generate_bulletpoints_with_llm_async_uses_async_openai(monkeypatch):
    captured = {}

    class DummyResponses:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "bullet_points": [
                            "Built FastAPI APIs for grounded resume generation.",
                            "Validated user-authored project evidence for tailored resumes.",
                        ]
                    }
                ),
                usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            )

    class DummyAsyncOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            captured["closed"] = False
            self.responses = DummyResponses()

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(bullet_llm_client, "AsyncOpenAI", DummyAsyncOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(bullet_llm_client.settings, "BULLETPOINTS_LLM_MODEL", "test-model")

    result = asyncio.run(
        generate_bulletpoints_with_llm_async(
            context=BulletJobContext(title="Backend Engineer"),
            project=_project(),
            count_range=BulletCountRange(min=2, max=4),
        )
    )

    assert captured["init"]["api_key"] == "test-key"
    assert captured["kwargs"]["model"] == "test-model"
    assert captured["kwargs"]["text"]["format"]["name"] == "project_bullet_points"
    assert captured["closed"] is True
    assert result.bullet_points[0].startswith("Built FastAPI")
    assert result.metadata["total_tokens"] == 30


def test_resolve_bulletpoint_max_output_tokens_scales_and_caps():
    resolved = resolve_bulletpoint_max_output_tokens(
        prompt_payload="x" * 2100,
        count_range=BulletCountRange(min=2, max=4),
        highlight_count=6,
        output_token_budget={
            "base": 900,
            "per_bullet": 550,
            "per_highlight": 35,
            "per_evidence_1k_chars": 80,
            "min": 1800,
            "max": None,
        },
    )

    assert resolved["resolved_llm_max_output_tokens"] == 3550
    assert resolved["mode"] == "dynamic"
    assert resolved["inputs"]["highlight_count"] == 6

    capped = resolve_bulletpoint_max_output_tokens(
        prompt_payload="x" * 2100,
        count_range=BulletCountRange(min=2, max=4),
        highlight_count=6,
        output_token_budget={
            "base": 900,
            "per_bullet": 550,
            "per_highlight": 35,
            "per_evidence_1k_chars": 80,
            "min": 1800,
            "max": 2500,
        },
    )

    assert capped["resolved_llm_max_output_tokens"] == 2500


def test_generate_bulletpoints_with_llm_accepts_explicit_max_output_override(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"bullet_points":["Built grounded resume APIs."]}',
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=1, max=1),
        max_output_tokens=444,
    )

    assert captured["kwargs"]["max_output_tokens"] == 444
    assert result.metadata["requested_llm_max_output_tokens"] == 444
    assert result.metadata["resolved_llm_max_output_tokens"] == 444
    assert result.metadata["llm_output_token_budget_mode"] == "override"


def test_generate_bulletpoints_with_llm_retries_malformed_json(monkeypatch):
    captured_calls: list[dict] = []

    class DummyResponses:
        def create(self, **kwargs):
            captured_calls.append(kwargs)
            if len(captured_calls) == 1:
                return SimpleNamespace(
                    output_text='{"bullet_points":["Built an API"',
                    usage=SimpleNamespace(
                        input_tokens=20,
                        output_tokens=120,
                        total_tokens=140,
                    ),
                )
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "bullet_points": [
                            "Built FastAPI APIs for grounded resume generation.",
                            "Validated user-authored evidence for tailored resumes.",
                        ]
                    }
                ),
                usage=SimpleNamespace(input_tokens=21, output_tokens=30, total_tokens=51),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=2, max=2),
    )

    first_budget = captured_calls[0]["max_output_tokens"]
    assert [call["max_output_tokens"] for call in captured_calls] == [
        first_budget,
        first_budget * 2,
    ]
    assert result.bullet_points == [
        "Built FastAPI APIs for grounded resume generation.",
        "Validated user-authored evidence for tailored resumes.",
    ]
    assert result.metadata["api_calls"] == 2
    assert result.metadata["prompt_tokens"] == 41
    assert result.metadata["completion_tokens"] == 150
    assert result.metadata["total_tokens"] == 191
    assert "valid JSON" in result.metadata["retry_reason"]
    assert result.metadata["attempts"][0]["error"].startswith(
        "Bullet-point LLM response was not valid JSON"
    )


def test_generate_bulletpoints_with_llm_uses_experience_schema_name(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "bullet_points": [
                            "Designed schema-validated APIs for backend platforms."
                        ]
                    }
                ),
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        experience=_experience(),
        count_range=BulletCountRange(min=1, max=1),
    )

    kwargs = captured["kwargs"]
    assert kwargs["text"]["format"]["name"] == "experience_bullet_points"
    assert json.loads(kwargs["input"])["experience"]["id"] == "backend-engineer"
    assert "experience evidence" in kwargs["instructions"]


def test_generate_bulletpoints_with_llm_omits_temperature_for_gpt_5_mini(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"bullet_points":["Built grounded resume APIs."]}',
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(bullet_llm_client.settings, "BULLETPOINTS_LLM_MODEL", "gpt-5-mini")

    generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=1, max=1),
    )

    assert "temperature" not in captured["kwargs"]


def test_generate_bulletpoints_with_llm_rejects_invalid_json(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text="{not-json", usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(BulletPointLLMClientError, match="valid JSON"):
        generate_bulletpoints_with_llm(
            context=BulletJobContext(title="Backend Engineer"),
            project=_project(),
            count_range=BulletCountRange(min=1, max=1),
        )


def test_generate_bulletpoints_with_llm_rejects_wrong_count(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text='{"bullet_points":["One bullet only."]}',
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(bullet_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(BulletPointLLMClientError, match="outside the requested range"):
        generate_bulletpoints_with_llm(
            context=BulletJobContext(title="Backend Engineer"),
            project=_project(),
            count_range=BulletCountRange(min=2, max=2),
        )


def test_generate_bulletpoints_with_llm_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(bullet_llm_client.settings, "RESUME_GENERATION_ROOT", tmp_path)

    with pytest.raises(BulletPointLLMClientError, match="OPENAI_API_KEY"):
        generate_bulletpoints_with_llm(
            context=BulletJobContext(title="Backend Engineer"),
            project=_project(),
            count_range=BulletCountRange(min=1, max=1),
        )
