import json
from types import SimpleNamespace

import pytest

from app.skill_selection import llm_client
from app.skill_selection.llm_client import (
    LLMClientError,
    _extract_output_text,
    score_skills_with_llm,
)


def test_score_skills_with_llm_sends_responses_schema(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"technology":{"React":3},"programming":{},"concepts":{}}',
                usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.settings, "SKILL_LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_client.settings, "SKILL_LLM_MAX_OUTPUT_TOKENS", 321)

    result = score_skills_with_llm(
        job_role="Frontend Engineer",
        job_text=None,
        technology=["React"],
        programming=[],
        concepts=[],
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert kwargs["max_output_tokens"] == 321
    assert kwargs["tools"] == []
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    schema = kwargs["text"]["format"]["schema"]
    assert schema["required"] == ["technology", "programming", "concepts"]
    assert schema["properties"]["technology"]["required"] == ["React"]
    assert result.scores["technology"]["React"] == 3
    assert result.metadata["prompt_tokens"] == 12
    assert result.metadata["completion_tokens"] == 8
    assert result.metadata["total_tokens"] == 20
    assert result.metadata["api_calls"] == 1
    assert result.metadata["model"] == "test-model"


def test_score_skills_with_llm_omits_temperature_for_gpt_5_mini(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text='{"technology":{"React":3},"programming":{},"concepts":{}}',
                usage=SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.settings, "SKILL_LLM_MODEL", "gpt-5-mini")

    score_skills_with_llm(
        job_role="Frontend Engineer",
        job_text=None,
        technology=["React"],
        programming=[],
        concepts=[],
    )

    assert "temperature" not in captured["kwargs"]


def test_supports_temperature_returns_false_for_gpt_5_6_terra():
    assert llm_client.supports_temperature("gpt-5.6-terra") is False


def test_score_skills_with_llm_reads_structured_output_when_output_text_missing(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        content=[
                            SimpleNamespace(
                                text='{"technology":{"FastAPI":3},"programming":{},"concepts":{}}'
                            )
                        ]
                    )
                ],
                usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = score_skills_with_llm(
        job_role="Backend Engineer",
        job_text="Build FastAPI services.",
        technology=["FastAPI"],
        programming=[],
        concepts=[],
    )

    assert result.scores["technology"]["FastAPI"] == 3
    assert result.metadata["total_tokens"] == 20


def test_extract_output_text_skips_cyclic_response_parts():
    cyclic_part = SimpleNamespace()
    cyclic_part.content = cyclic_part
    output_text = '{"technology":{"FastAPI":3},"programming":{},"concepts":{}}'
    response = SimpleNamespace(
        output=[
            cyclic_part,
            SimpleNamespace(content=[SimpleNamespace(text=output_text)]),
        ]
    )

    assert _extract_output_text(response) == output_text

    cyclic_response = SimpleNamespace()
    cyclic_response.output = cyclic_response

    assert _extract_output_text(cyclic_response) is None


def test_score_skills_with_llm_rejects_invalid_json(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text="{not-json", usage=None)

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LLMClientError, match="valid JSON"):
        score_skills_with_llm(
            job_role="Backend Engineer",
            job_text=None,
            technology=[],
            programming=[],
            concepts=[],
        )


def test_score_skills_with_llm_retries_malformed_json(monkeypatch):
    captured_calls: list[dict] = []

    class DummyResponses:
        def create(self, **kwargs):
            captured_calls.append(kwargs)
            if len(captured_calls) == 1:
                return SimpleNamespace(
                    output_text='{"technology":{"FastAPI":3}',
                    usage=SimpleNamespace(input_tokens=20, output_tokens=120, total_tokens=140),
                )
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "technology": {"FastAPI": 3},
                        "programming": {"Python": 3},
                        "concepts": {"API": 3},
                    }
                ),
                usage=SimpleNamespace(input_tokens=21, output_tokens=30, total_tokens=51),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")

    result = score_skills_with_llm(
        job_role="Backend Engineer",
        job_text="Build FastAPI APIs.",
        technology=["FastAPI"],
        programming=["Python"],
        concepts=["API"],
        max_output_tokens=444,
    )

    assert [call["max_output_tokens"] for call in captured_calls] == [444, 3000]
    assert result.scores["technology"]["FastAPI"] == 3
    assert result.metadata["api_calls"] == 2
    assert result.metadata["prompt_tokens"] == 41
    assert result.metadata["completion_tokens"] == 150
    assert result.metadata["total_tokens"] == 191
    assert "valid JSON" in result.metadata["retry_reason"]
    assert result.metadata["attempts"][0]["max_output_tokens"] == 444
    assert result.metadata["attempts"][0]["error"].startswith(
        "LLM response was not valid JSON"
    )


def test_score_skills_with_llm_error_carries_failed_attempt_metadata(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text="{not-json",
                usage=SimpleNamespace(input_tokens=5, output_tokens=7, total_tokens=12),
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LLMClientError, match="valid JSON") as exc_info:
        score_skills_with_llm(
            job_role="Backend Engineer",
            job_text=None,
            technology=[],
            programming=[],
            concepts=[],
            max_output_tokens=200,
        )

    assert exc_info.value.metadata["api_calls"] == 2
    assert exc_info.value.metadata["total_tokens"] == 24
    assert [attempt["max_output_tokens"] for attempt in exc_info.value.metadata["attempts"]] == [
        200,
        3000,
    ]


def test_score_skills_with_llm_computes_default_output_cap(monkeypatch):
    captured = {}
    skills = [f"Candidate Skill {index}" for index in range(80)]

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=json.dumps(
                    {"technology": {}, "programming": {}, "concepts": {}}
                ),
                usage=None,
            )

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm_client.settings, "SKILL_LLM_MAX_OUTPUT_TOKENS", 321)

    score_skills_with_llm(
        job_role="Backend Engineer",
        job_text=None,
        technology=skills,
        programming=[],
        concepts=[],
    )

    assert captured["kwargs"]["max_output_tokens"] > 321


def test_score_skills_with_llm_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_client.settings, "RESUME_GENERATION_ROOT", tmp_path)

    with pytest.raises(LLMClientError, match="OPENAI_API_KEY"):
        score_skills_with_llm(
            job_role="Backend Engineer",
            job_text=None,
            technology=[],
            programming=[],
            concepts=[],
        )


def test_score_skills_with_llm_wraps_openai_errors(monkeypatch):
    class DummyResponses:
        def create(self, **_kwargs):
            raise TimeoutError("network timeout")

    class DummyOpenAI:
        def __init__(self, **_kwargs):
            self.responses = DummyResponses()

    monkeypatch.setattr(llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(llm_client.settings, "OPENAI_API_KEY", "test-key")

    with pytest.raises(LLMClientError, match="LLM request failed"):
        score_skills_with_llm(
            job_role="Backend Engineer",
            job_text=None,
            technology=[],
            programming=[],
            concepts=[],
        )
