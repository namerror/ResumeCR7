from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.job_focus_generation import llm_client as job_focus_llm_client
from app.job_focus_generation import service as job_focus_service
from app.job_focus_generation.llm_client import (
    JobFocusLLMClientError,
    LLMJobFocusResult,
    build_job_focus_instructions,
    build_job_focus_prompt_payload,
    build_job_focus_schema,
    derive_job_focus_with_llm,
)
from app.job_focus_generation.models import JobFocus, JobFocusRequest
from app.main import app


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


def _job_focus(**overrides) -> JobFocus:
    payload = {
        "summary": "Backend API role focused on Python services and integrations.",
        "required_skills": ["Python", "FastAPI"],
        "preferred_skills": ["Docker"],
        "responsibilities": ["Build and maintain REST APIs"],
        "domain_emphasis": ["Backend platforms"],
        "resume_relevant_constraints": ["Remote collaboration"],
        "excluded_context": ["Benefits and culture language"],
    }
    payload.update(overrides)
    return JobFocus.model_validate(payload)


def test_job_focus_model_trims_and_dedupes_lists():
    focus = _job_focus(required_skills=[" Python ", "Python", " FastAPI "])

    assert focus.required_skills == ["Python", "FastAPI"]


def test_job_focus_request_rejects_empty_title():
    with pytest.raises(ValidationError, match="title"):
        JobFocusRequest(title="  ")


def test_build_job_focus_schema_is_strict():
    schema = build_job_focus_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "summary",
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "domain_emphasis",
        "resume_relevant_constraints",
        "excluded_context",
    ]
    assert schema["properties"]["required_skills"]["maxItems"] == 12


def test_build_job_focus_prompt_and_instructions_exclude_irrelevant_sections():
    payload = json.loads(
        build_job_focus_prompt_payload(
            title="Backend Engineer",
            description="Build APIs. We offer great benefits and a warm culture.",
        )
    )
    instructions = build_job_focus_instructions()

    assert payload["job"]["title"] == "Backend Engineer"
    assert "benefits" in payload["exclude"]
    assert "company culture" in payload["exclude"]
    assert "legal boilerplate" in instructions
    assert "important skills" not in payload["exclude"]


def test_derive_job_focus_with_llm_sends_strict_schema(monkeypatch):
    captured = {}

    class DummyResponses:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                output_text=_job_focus().model_dump_json(),
                usage=SimpleNamespace(input_tokens=20, output_tokens=10, total_tokens=30),
            )

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured["init"] = kwargs
            self.responses = DummyResponses()

    monkeypatch.setattr(job_focus_llm_client, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(job_focus_llm_client.settings, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(job_focus_llm_client.settings, "JOB_FOCUS_LLM_MODEL", "test-model")
    monkeypatch.setattr(
        job_focus_llm_client.settings,
        "JOB_FOCUS_LLM_MAX_OUTPUT_TOKENS",
        444,
    )

    result = derive_job_focus_with_llm(
        title="Backend Engineer",
        description="Build Python APIs.",
    )

    assert captured["init"]["api_key"] == "test-key"
    kwargs = captured["kwargs"]
    assert kwargs["model"] == "test-model"
    assert kwargs["temperature"] == 0
    assert kwargs["max_output_tokens"] == 444
    assert kwargs["text"]["format"]["name"] == "job_focus"
    assert kwargs["text"]["format"]["strict"] is True
    assert json.loads(kwargs["input"])["job"]["description"] == "Build Python APIs."
    assert result.job_focus.required_skills == ["Python", "FastAPI"]
    assert result.metadata["total_tokens"] == 30


def test_derive_job_focus_with_llm_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.setattr(job_focus_llm_client.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(job_focus_llm_client.settings, "RESUME_GENERATION_ROOT", tmp_path)

    with pytest.raises(JobFocusLLMClientError, match="OPENAI_API_KEY"):
        derive_job_focus_with_llm(
            title="Backend Engineer",
            description="Build APIs.",
        )


def test_derive_job_focus_api_success_with_details(monkeypatch):
    def fake_generate(**_kwargs):
        return LLMJobFocusResult(
            job_focus=_job_focus(),
            metadata={
                "model": "test-model",
                "api_calls": 1,
                "prompt_tokens": 30,
                "completion_tokens": 12,
                "total_tokens": 42,
                "latency_ms": 1.5,
            },
        )

    monkeypatch.setattr(job_focus_service, "derive_job_focus_with_llm", fake_generate)

    response = api_request(
        "POST",
        "/derive-job-focus",
        json={
            "title": "Backend Engineer",
            "description": "Build Python APIs.",
            "dev_mode": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["job_focus"]["required_skills"] == ["Python", "FastAPI"]
    assert data["details"]["method"] == "llm"
    assert data["details"]["_job_focus_llm"]["total_tokens"] == 42


def test_derive_job_focus_api_returns_502_on_llm_failure(monkeypatch):
    def raise_client_error(**_kwargs):
        raise JobFocusLLMClientError("network down")

    monkeypatch.setattr(
        job_focus_service,
        "derive_job_focus_with_llm",
        raise_client_error,
    )

    response = api_request(
        "POST",
        "/derive-job-focus",
        json={"title": "Backend Engineer", "description": "Build APIs."},
    )

    assert response.status_code == 502
    assert "network down" in response.json()["detail"]
