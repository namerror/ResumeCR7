from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.bulletpoints_generation import llm_client as bullet_llm_client
from app.bulletpoints_generation.llm_client import (
    BulletPointLLMClientError,
    build_bulletpoint_instructions,
    build_bulletpoint_prompt_payload,
    build_bulletpoint_schema,
    generate_bulletpoints_with_llm,
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
    assert "mostly raw, human-written factual context" in exact
    assert "should not copy its logic, tone, or wording" in exact
    assert "recruiting-relevant information from the live evidence" in exact
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
    assert "links" not in payload["project"]
    assert "https://example.com/resumecr7" not in json.dumps(payload)


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
    assert "project" not in payload
    assert "links" not in payload["experience"]
    assert "https://example.com/company" not in json.dumps(payload)
    assert "experience evidence" in payload["grounding_rules"][0]


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
    monkeypatch.setattr(
        bullet_llm_client.settings,
        "BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS",
        444,
    )

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=2, max=4),
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert kwargs["max_output_tokens"] == 444
    assert kwargs["text"]["format"]["name"] == "project_bullet_points"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["text"]["format"]["schema"]["properties"]["bullet_points"]["minItems"] == 2
    assert json.loads(kwargs["input"])["project"]["id"] == "resumecr7"
    assert result.bullet_points[0].startswith("Built FastAPI")
    assert result.metadata["total_tokens"] == 30


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
    monkeypatch.setattr(
        bullet_llm_client.settings,
        "BULLETPOINTS_LLM_MAX_OUTPUT_TOKENS",
        444,
    )

    result = generate_bulletpoints_with_llm(
        context=BulletJobContext(title="Backend Engineer"),
        project=_project(),
        count_range=BulletCountRange(min=2, max=2),
    )

    assert [call["max_output_tokens"] for call in captured_calls] == [444, 3000]
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


def test_generate_bulletpoints_with_llm_requires_api_key(monkeypatch):
    monkeypatch.setattr(bullet_llm_client.settings, "OPENAI_API_KEY", "")

    with pytest.raises(BulletPointLLMClientError, match="OPENAI_API_KEY"):
        generate_bulletpoints_with_llm(
            context=BulletJobContext(title="Backend Engineer"),
            project=_project(),
            count_range=BulletCountRange(min=1, max=1),
        )
