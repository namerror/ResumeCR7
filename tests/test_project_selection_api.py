import asyncio

import httpx

from app.main import app
from app.project_selection import llm as project_llm
from app.project_selection import service as project_service
from app.project_selection.llm_client import LLMProjectScoreResult, ProjectLLMClientError


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


def _project_payload(project_id: str, name: str, *, programming: list[str] | None = None) -> dict:
    return {
        "id": project_id,
        "name": name,
        "summary": f"{name} backend API project.",
        "skills": {
            "technology": ["Django"],
            "programming": programming or ["Python"],
            "concepts": ["API"],
        },
    }


def _request_payload(**overrides) -> dict:
    payload = {
        "context": {
            "title": "Backend Engineer",
            "description": "Build Python Django APIs.",
        },
        "candidates": [
            _project_payload("resumecr7", "ResumeCR7"),
            _project_payload("portfolio", "Portfolio", programming=["JavaScript"]),
        ],
        "method": "baseline",
        "top_n": 1,
        "dev_mode": True,
    }
    payload.update(overrides)
    return payload


def test_select_projects_api_baseline_success_with_top_n_and_details():
    response = api_request("POST", "/select-projects", json=_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["selected_project_ids"] == ["resumecr7"]
    assert [project["project_id"] for project in data["ranked_projects"]] == ["resumecr7"]
    assert data["details"]["method"] == "baseline"
    assert "resumecr7" in data["details"]["projects"]


def test_select_projects_api_uses_scoped_settings_when_request_omits_overrides(monkeypatch):
    monkeypatch.setattr(project_service.settings, "PROJ_METHOD", "baseline")
    monkeypatch.setattr(project_service.settings, "PROJ_TOP_N", 1)
    payload = _request_payload()
    payload.pop("method")
    payload.pop("top_n")

    response = api_request("POST", "/select-projects", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["selected_project_ids"] == ["resumecr7"]
    assert len(data["ranked_projects"]) == 1
    assert data["ranked_projects"][0]["method"] == "baseline"


def test_select_projects_api_request_overrides_scoped_settings(monkeypatch):
    monkeypatch.setattr(project_service.settings, "PROJ_METHOD", "llm")
    monkeypatch.setattr(project_service.settings, "PROJ_TOP_N", None)

    response = api_request("POST", "/select-projects", json=_request_payload(method="baseline", top_n=1))

    assert response.status_code == 200
    data = response.json()
    assert len(data["ranked_projects"]) == 1
    assert data["ranked_projects"][0]["method"] == "baseline"


def test_select_projects_api_rejects_duplicate_project_ids():
    duplicate = _project_payload("same-id", "Duplicate")
    response = api_request(
        "POST",
        "/select-projects",
        json=_request_payload(candidates=[duplicate, duplicate]),
    )

    assert response.status_code == 400
    assert "Duplicate project ids" in response.json()["detail"]


def test_select_projects_api_rejects_unsupported_method():
    response = api_request("POST", "/select-projects", json=_request_payload(method="embeddings"))

    assert response.status_code == 400
    assert "method" in response.json()["detail"]


def test_select_projects_api_llm_fallback_returns_baseline(monkeypatch):
    def raise_client_error(**_kwargs):
        raise ProjectLLMClientError("network down")

    monkeypatch.setattr(project_llm, "score_projects_with_llm", raise_client_error)

    response = api_request("POST", "/select-projects", json=_request_payload(method="llm"))

    assert response.status_code == 200
    data = response.json()
    assert data["ranked_projects"][0]["method"] == "baseline"
    assert data["details"]["_fallback_method"] == "baseline"
    assert data["details"]["_project_llm"]["fallback"] == "baseline"


def test_select_projects_api_records_project_metrics_and_tokens(monkeypatch):
    before = api_request("GET", "/metrics-lite").json()

    monkeypatch.setattr(
        project_llm,
        "score_projects_with_llm",
        lambda **_kwargs: LLMProjectScoreResult(
            scores={"resumecr7": 3, "portfolio": 1},
            metadata={
                "model": "test-model",
                "api_calls": 1,
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
                "latency_ms": 1.2,
            },
        ),
    )

    response = api_request("POST", "/select-projects", json=_request_payload(method="llm"))

    assert response.status_code == 200
    after = api_request("GET", "/metrics-lite").json()
    project_metrics = after["subsystems"]["project_selection"]
    before_project_metrics = before["subsystems"]["project_selection"]

    assert after["requests_total"] == before["requests_total"] + 1
    assert after["total_tokens"] == before["total_tokens"] + 13
    assert project_metrics["requests_total"] == before_project_metrics["requests_total"] + 1
    assert project_metrics["total_tokens"] == before_project_metrics["total_tokens"] + 13
    assert project_metrics["method_usage"].get("llm", 0) == before_project_metrics["method_usage"].get("llm", 0) + 1


def test_select_projects_api_passes_output_token_budget(monkeypatch):
    captured = {}

    def fake_score_projects_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMProjectScoreResult(
            scores={"resumecr7": 3, "portfolio": 1},
            metadata={
                "model": "test-model",
                "total_tokens": 0,
                "resolved_llm_max_output_tokens": 1800,
                "llm_output_token_budget_mode": "dynamic",
            },
        )

    monkeypatch.setattr(project_llm, "score_projects_with_llm", fake_score_projects_with_llm)

    response = api_request(
        "POST",
        "/select-projects",
        json=_request_payload(
            method="llm",
            llm_output_token_budget={
                "base": 800,
                "per_candidate": 50,
                "per_prompt_1k_chars": 25,
                "min": 1100,
                "max": None,
            },
        ),
    )

    assert response.status_code == 200
    assert captured["output_token_budget"].base == 800
    assert captured["output_token_budget"].max is None
    assert response.json()["details"]["_project_llm"][
        "resolved_llm_max_output_tokens"
    ] == 1800


def test_select_projects_api_records_project_errors():
    before = api_request("GET", "/metrics-lite").json()

    response = api_request("POST", "/select-projects", json=_request_payload(method="embeddings"))

    assert response.status_code == 400
    after = api_request("GET", "/metrics-lite").json()
    project_metrics = after["subsystems"]["project_selection"]
    before_project_metrics = before["subsystems"]["project_selection"]

    assert after["errors_total"] == before["errors_total"] + 1
    assert project_metrics["errors_total"] == before_project_metrics["errors_total"] + 1
