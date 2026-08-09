import asyncio

import httpx

from app.bulletpoints_generation import service as bullet_service
from app.bulletpoints_generation.llm_client import (
    BulletPointLLMClientError,
    LLMBulletPointResult,
    LLMResumeSectionBulletPointResult,
)
from app.bulletpoints_generation.models import (
    ExperienceBulletPointSet,
    ProjectBulletPointSet,
)
from app.main import app


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


def _project_payload() -> dict:
    return {
        "id": "resumecr7",
        "name": "ResumeCR7",
        "summary": "FastAPI resume engine for grounded resume generation.",
        "highlights": [
            "Built project and skill selection APIs with deterministic fallbacks.",
            "Added strict resume evidence parsing for user-authored project data.",
            "Implemented HTTP orchestration for resume selection context.",
        ],
        "active": True,
        "skills": {
            "technology": ["FastAPI", "OpenAI"],
            "programming": ["Python"],
            "concepts": ["API", "Grounded Generation"],
        },
        "links": ["https://example.com/resumecr7"],
    }


def _experience_payload() -> dict:
    return {
        "id": "backend-engineer",
        "name": "Example Company",
        "role": "Backend Engineer",
        "summary": "Built backend services for internal platforms.",
        "highlights": [
            "Designed schema-validated APIs.",
            "Maintained automated tests for backend services.",
        ],
        "active": True,
        "skills": {
            "technology": ["FastAPI"],
            "programming": ["Python"],
            "concepts": ["API", "Testing"],
        },
        "location": "Example City, ST",
        "start": "2024",
        "end": None,
        "links": ["https://example.com/company"],
    }


def _request_payload(**overrides) -> dict:
    payload = {
        "context": {
            "title": "Backend Engineer",
            "description": "Build Python APIs with grounded AI workflows.",
        },
        "project": _project_payload(),
        "dev_mode": True,
    }
    payload.update(overrides)
    return payload


def _experience_request_payload(**overrides) -> dict:
    payload = {
        "context": {
            "title": "Backend Engineer",
            "description": "Build Python APIs with grounded AI workflows.",
        },
        "experience": _experience_payload(),
        "dev_mode": True,
    }
    payload.update(overrides)
    return payload


def test_generate_bulletpoints_api_success_with_default_count_and_details(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured["count_range"] = kwargs["count_range"]
        return LLMBulletPointResult(
            bullet_points=[
                "Built FastAPI services for grounded resume selection workflows.",
                "Validated project evidence to keep generated content traceable.",
                "Integrated OpenAI-backed refinement behind strict service contracts.",
            ],
            metadata={
                "model": "test-model",
                "api_calls": 1,
                "prompt_tokens": 30,
                "completion_tokens": 12,
                "total_tokens": 42,
                "latency_ms": 1.5,
            },
        )

    before = api_request("GET", "/metrics-lite").json()
    monkeypatch.setattr(bullet_service, "generate_bulletpoints_with_llm_async", fake_generate)
    monkeypatch.setattr(bullet_service.settings, "BULLETPOINTS_DEFAULT_COUNT", 3)

    response = api_request("POST", "/generate-bulletpoints", json=_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert len(data["bullet_points"]) == 3
    assert captured["count_range"].min == 3
    assert captured["count_range"].max == 3
    assert data["details"]["method"] == "llm"
    assert data["details"]["requested_count_range"] is None
    assert data["details"]["effective_count_range"] == {"min": 3, "max": 3}
    assert data["details"]["evidence_type"] == "project"
    assert data["details"]["_bulletpoints_llm"]["total_tokens"] == 42

    after = api_request("GET", "/metrics-lite").json()
    before_bucket = before["subsystems"]["bulletpoints_generation"]
    after_bucket = after["subsystems"]["bulletpoints_generation"]
    assert after["requests_total"] == before["requests_total"] + 1
    assert after["total_tokens"] == before["total_tokens"] + 42
    assert after_bucket["requests_total"] == before_bucket["requests_total"] + 1
    assert after_bucket["total_tokens"] == before_bucket["total_tokens"] + 42
    assert after_bucket["method_usage"].get("llm", 0) == (
        before_bucket["method_usage"].get("llm", 0) + 1
    )


def test_generate_bulletpoints_api_uses_request_count_range(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured["count_range"] = kwargs["count_range"]
        return LLMBulletPointResult(
            bullet_points=["Built APIs.", "Validated evidence."],
            metadata={"model": "test-model", "total_tokens": 0},
        )

    monkeypatch.setattr(bullet_service, "generate_bulletpoints_with_llm_async", fake_generate)

    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_request_payload(bullet_count_range={"min": 2, "max": 4}),
    )

    assert response.status_code == 200
    assert captured["count_range"].min == 2
    assert captured["count_range"].max == 4


def test_generate_bulletpoints_api_passes_output_token_budget(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return LLMBulletPointResult(
            bullet_points=["Built APIs."],
            metadata={
                "model": "test-model",
                "total_tokens": 0,
                "resolved_llm_max_output_tokens": 2222,
                "llm_output_token_budget_mode": "dynamic",
            },
        )

    monkeypatch.setattr(bullet_service, "generate_bulletpoints_with_llm_async", fake_generate)

    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_request_payload(
            bullet_count_range={"min": 1, "max": 1},
            llm_output_token_budget={
                "base": 1000,
                "per_bullet": 400,
                "per_highlight": 25,
                "per_evidence_1k_chars": 60,
                "min": 1500,
                "max": None,
            },
        ),
    )

    assert response.status_code == 200
    assert captured["output_token_budget"].base == 1000
    assert captured["output_token_budget"].max is None
    assert response.json()["details"]["_bulletpoints_llm"][
        "resolved_llm_max_output_tokens"
    ] == 2222


def test_generate_bulletpoints_api_accepts_experience_record(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return LLMBulletPointResult(
            bullet_points=["Designed schema-validated APIs for backend platforms."],
            metadata={"model": "test-model", "total_tokens": 0},
        )

    monkeypatch.setattr(bullet_service, "generate_bulletpoints_with_llm_async", fake_generate)

    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_experience_request_payload(bullet_count_range={"min": 1, "max": 1}),
    )

    assert response.status_code == 200
    assert captured["project"] is None
    assert captured["experience"].id == "backend-engineer"
    assert response.json()["details"]["evidence_type"] == "experience"
    assert response.json()["bullet_points"] == [
        "Designed schema-validated APIs for backend platforms."
    ]


def test_generate_resume_section_bulletpoints_api_success(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return LLMResumeSectionBulletPointResult(
            project_bullet_points=[
                ProjectBulletPointSet(
                    project_id="resumecr7",
                    bullet_points=["Built coordinated project bullet."],
                )
            ],
            experience_bullet_points=[
                ExperienceBulletPointSet(
                    experience_id="backend-engineer",
                    bullet_points=["Designed coordinated experience bullet."],
                )
            ],
            metadata={
                "model": "test-model",
                "api_calls": 1,
                "prompt_tokens": 50,
                "completion_tokens": 20,
                "total_tokens": 70,
                "latency_ms": 2.0,
            },
        )

    monkeypatch.setattr(
        bullet_service,
        "generate_resume_section_bulletpoints_with_llm_async",
        fake_generate,
    )

    response = api_request(
        "POST",
        "/generate-resume-section-bulletpoints",
        json={
            "context": {
                "title": "Backend Engineer",
                "description": "Build Python APIs.",
            },
            "projects": [_project_payload()],
            "experiences": [_experience_payload()],
            "project_bullet_count_range": {"min": 1, "max": 2},
            "experience_bullet_count_range": {"min": 1, "max": 1},
            "dev_mode": True,
        },
    )

    assert response.status_code == 200
    assert captured["project_count_range"].min == 1
    assert captured["project_count_range"].max == 2
    assert captured["experience_count_range"].min == 1
    data = response.json()
    assert data["project_bullet_points"][0]["project_id"] == "resumecr7"
    assert data["experience_bullet_points"][0]["experience_id"] == "backend-engineer"
    assert data["details"]["effective_count_ranges"]["projects"] == {"min": 1, "max": 2}
    assert data["details"]["_bulletpoints_llm"]["total_tokens"] == 70


def test_generate_bulletpoints_api_rejects_missing_or_ambiguous_evidence():
    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json={
            "context": {
                "title": "Backend Engineer",
                "description": "Build Python APIs.",
            },
        },
    )

    assert response.status_code == 422
    assert "Exactly one of project or experience" in response.text

    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_request_payload(experience=_experience_payload()),
    )

    assert response.status_code == 422
    assert "Exactly one of project or experience" in response.text


def test_generate_bulletpoints_api_returns_502_on_llm_failure(monkeypatch):
    async def raise_client_error(**_kwargs):
        raise BulletPointLLMClientError("network down")

    monkeypatch.setattr(
        bullet_service,
        "generate_bulletpoints_with_llm_async",
        raise_client_error,
    )

    response = api_request("POST", "/generate-bulletpoints", json=_request_payload())

    assert response.status_code == 502
    assert "network down" in response.json()["detail"]


def test_generate_bulletpoints_api_rejects_link_scanning_field():
    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_request_payload(link_scanning=True),
    )

    assert response.status_code == 422
    assert "link_scanning" in response.text


def test_generate_bulletpoints_api_rejects_invalid_count_range():
    response = api_request(
        "POST",
        "/generate-bulletpoints",
        json=_request_payload(bullet_count_range={"min": 0, "max": 4}),
    )

    assert response.status_code == 422
    assert "bullet_count_range.min" in response.text
