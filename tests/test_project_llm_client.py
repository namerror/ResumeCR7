from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.project_selection import ProjectCandidate, ProjectJobContext
from resume_evidence.models import ProjectSkills
from app.project_selection import llm_client as project_llm_client
from app.project_selection.llm_client import (
    ProjectLLMClientError,
    resolve_project_max_output_tokens,
    score_projects_with_llm,
)


def _candidate(project_id: str, name: str) -> ProjectCandidate:
    return ProjectCandidate(
        id=project_id,
        name=name,
        summary=f"{name} summary",
        skills=ProjectSkills(
            technology=["Django"],
            programming=["Python"],
            concepts=["API"],
        ),
    )


def test_score_projects_with_llm_sends_strict_project_schema(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"resumecr7":3,"portfolio":1}',
                usage=SimpleNamespace(input_tokens=12, output_tokens=5, total_tokens=17),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(project_llm_client.settings, "PROJ_LLM_MODEL", "test-model")

    result = score_projects_with_llm(
        context=ProjectJobContext(title="Backend Engineer", description="Build APIs."),
        candidates=[_candidate("resumecr7", "ResumeCR7"), _candidate("portfolio", "Portfolio")],
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert "max_output_tokens" not in kwargs
    assert kwargs["text"]["format"]["name"] == "project_scores"
    assert kwargs["text"]["format"]["strict"] is True
    schema = kwargs["text"]["format"]["schema"]
    assert schema["required"] == ["resumecr7", "portfolio"]
    assert schema["properties"]["resumecr7"]["minimum"] == 0
    assert schema["properties"]["resumecr7"]["maximum"] == 3
    payload = json.loads(kwargs["input"])
    assert payload["job"]["title"] == "Backend Engineer"
    assert payload["projects"][0]["id"] == "resumecr7"
    assert payload["projects"][0]["skills"]["programming"] == ["Python"]
    assert result.scores == {"resumecr7": 3, "portfolio": 1}
    assert result.metadata["total_tokens"] == 17
    assert result.metadata["model"] == "test-model"
    assert result.metadata["resolved_llm_max_output_tokens"] is None
    assert result.metadata["llm_output_token_budget_mode"] == "uncapped"
    assert result.metadata["llm_output_token_budget"] is None


def test_resolve_project_max_output_tokens_scales_and_caps():
    resolved = resolve_project_max_output_tokens(
        prompt_payload="x" * 2500,
        candidate_count=20,
        output_token_budget={
            "base": 900,
            "per_candidate": 40,
            "per_prompt_1k_chars": 40,
            "min": 1200,
            "max": None,
        },
    )

    assert resolved["resolved_llm_max_output_tokens"] == 1820
    assert resolved["mode"] == "dynamic"
    assert resolved["inputs"]["candidate_count"] == 20

    capped = resolve_project_max_output_tokens(
        prompt_payload="x" * 2500,
        candidate_count=20,
        output_token_budget={
            "base": 900,
            "per_candidate": 40,
            "per_prompt_1k_chars": 40,
            "min": 1200,
            "max": 1500,
        },
    )

    assert capped["resolved_llm_max_output_tokens"] == 1500


def test_score_projects_with_llm_accepts_explicit_max_output_override(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(output_text='{"resumecr7":3}', usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = score_projects_with_llm(
        context=ProjectJobContext(title="Backend Engineer"),
        candidates=[_candidate("resumecr7", "ResumeCR7")],
        max_output_tokens=333,
    )

    assert captured["kwargs"]["max_output_tokens"] == 333
    assert result.metadata["requested_llm_max_output_tokens"] == 333
    assert result.metadata["resolved_llm_max_output_tokens"] == 333
    assert result.metadata["llm_output_token_budget_mode"] == "override"


def test_score_projects_with_llm_uses_explicit_output_token_budget(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(output_text='{"resumecr7":3}', usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = score_projects_with_llm(
        context=ProjectJobContext(title="Backend Engineer"),
        candidates=[_candidate("resumecr7", "ResumeCR7")],
        output_token_budget={
            "base": 800,
            "per_candidate": 50,
            "per_prompt_1k_chars": 25,
            "min": 1100,
            "max": None,
        },
    )

    assert captured["kwargs"]["max_output_tokens"] == 1100
    assert result.metadata["resolved_llm_max_output_tokens"] == 1100
    assert result.metadata["llm_output_token_budget_mode"] == "dynamic"


def test_score_projects_with_llm_reads_structured_output_when_output_text_missing(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        content=[
                            SimpleNamespace(text='{"resumecr7":3}'),
                        ]
                    )
                ],
                usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = score_projects_with_llm(
        context=ProjectJobContext(title="Backend Engineer"),
        candidates=[_candidate("resumecr7", "ResumeCR7")],
    )

    assert result.scores == {"resumecr7": 3}
    assert result.metadata["total_tokens"] == 20


def test_score_projects_with_llm_omits_temperature_for_gpt_5_mini(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(output_text='{"resumecr7":3}', usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(project_llm_client.settings, "PROJ_LLM_MODEL", "gpt-5-mini")

    score_projects_with_llm(
        context=ProjectJobContext(title="Backend Engineer"),
        candidates=[_candidate("resumecr7", "ResumeCR7")],
    )

    assert "temperature" not in captured["kwargs"]


def test_score_projects_with_llm_rejects_invalid_json(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text="{not-json", usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(project_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(ProjectLLMClientError, match="valid JSON"):
        score_projects_with_llm(
            context=ProjectJobContext(title="Backend Engineer"),
            candidates=[_candidate("resumecr7", "ResumeCR7")],
        )


def test_score_projects_with_llm_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(project_llm_client.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(project_llm_client.settings, "RESUME_GENERATION_ROOT", tmp_path)

    with pytest.raises(ProjectLLMClientError, match="OPENAI_API_KEY"):
        score_projects_with_llm(
            context=ProjectJobContext(title="Backend Engineer"),
            candidates=[_candidate("resumecr7", "ResumeCR7")],
        )
