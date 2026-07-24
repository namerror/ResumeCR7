import asyncio

import httpx

from app.link_scanning.llm_client import LLMLinkScanResult, LinkScanningLLMClientError
from app.link_scanning.models import LinkScanHighlight
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
        "highlights": ["Built project and skill selection APIs."],
        "active": True,
        "skills": {
            "technology": ["FastAPI"],
            "programming": ["Python"],
            "concepts": ["API"],
        },
        "links": ["https://example.com/resumecr7", "https://docs.example.com/resumecr7"],
    }


def _experience_payload() -> dict:
    return {
        "id": "backend-engineer",
        "name": "Example Company",
        "role": "Backend Engineer",
        "summary": "Built backend services for internal platforms.",
        "highlights": ["Designed schema-validated APIs."],
        "active": True,
        "skills": {
            "technology": ["FastAPI"],
            "programming": ["Python"],
            "concepts": ["API"],
        },
        "location": "Example City, ST",
        "start": "2024",
        "end": None,
        "links": ["https://example.com/company"],
    }


def _request_payload(**overrides) -> dict:
    payload = {
        "evidence_type": "project",
        "evidence": _project_payload(),
        "requested_highlight_count": 4,
        "dev_mode": True,
    }
    payload.update(overrides)
    return payload


def test_enrich_link_evidence_api_returns_llm_highlight_patch_with_details(monkeypatch):
    captured = {}

    def fake_scan_evidence_links_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMLinkScanResult(
            highlights=[
                LinkScanHighlight(
                    text="Scanned page confirms grounded resume orchestration.",
                    source_url="https://example.com/resumecr7",
                )
            ],
            metadata={
                "model": kwargs["model"],
                "api_calls": 1,
                "scanned_links": kwargs["evidence"].links,
                "source_urls": ["https://example.com/resumecr7"],
                "total_tokens": 42,
            },
        )

    monkeypatch.setattr(
        "app.link_scanning.service.scan_evidence_links_with_llm",
        fake_scan_evidence_links_with_llm,
    )

    response = api_request("POST", "/enrich-link-evidence", json=_request_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["evidence_type"] == "project"
    assert data["evidence_id"] == "resumecr7"
    assert data["added_highlights"] == [
        {
            "text": "Scanned page confirms grounded resume orchestration.",
            "source_url": "https://example.com/resumecr7",
        }
    ]
    assert "added_skills" not in data
    assert data["details"]["method"] == "llm"
    assert data["details"]["scanned_links"] == [
        "https://example.com/resumecr7",
        "https://docs.example.com/resumecr7",
    ]
    assert data["details"]["requested_highlight_count"] == 4
    assert data["details"]["_link_scanning_llm"]["total_tokens"] == 42
    assert captured["evidence_type"] == "project"
    assert captured["evidence"].id == "resumecr7"
    assert captured["requested_highlight_count"] == 4


def test_enrich_link_evidence_api_accepts_experience_records(monkeypatch):
    captured = {}

    def fake_scan_evidence_links_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMLinkScanResult(
            highlights=[],
            metadata={"model": "test-model", "api_calls": 1, "total_tokens": 0},
        )

    monkeypatch.setattr(
        "app.link_scanning.service.scan_evidence_links_with_llm",
        fake_scan_evidence_links_with_llm,
    )

    response = api_request(
        "POST",
        "/enrich-link-evidence",
        json=_request_payload(evidence_type="experience", evidence=_experience_payload()),
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == "backend-engineer"
    assert captured["evidence_type"] == "experience"
    assert captured["evidence"].role == "Backend Engineer"


def test_scan_link_api_is_removed():
    response = api_request("POST", "/scan-link", json=_request_payload())

    assert response.status_code == 404


def test_enrich_link_evidence_api_rejects_legacy_project_payload():
    response = api_request(
        "POST",
        "/enrich-link-evidence",
        json={
            "context": {"title": "Backend Engineer"},
            "project": _project_payload(),
            "dev_mode": True,
        },
    )

    assert response.status_code == 422
    assert "evidence_type" in response.text
    assert "evidence" in response.text


def test_enrich_link_evidence_api_omits_details_when_dev_mode_false(monkeypatch):
    def fake_scan_evidence_links_with_llm(**_kwargs):
        return LLMLinkScanResult(
            highlights=[],
            metadata={"model": "test-model", "api_calls": 1, "total_tokens": 0},
        )

    monkeypatch.setattr(
        "app.link_scanning.service.scan_evidence_links_with_llm",
        fake_scan_evidence_links_with_llm,
    )

    response = api_request("POST", "/enrich-link-evidence", json=_request_payload(dev_mode=False))

    assert response.status_code == 200
    assert response.json()["details"] is None


def test_enrich_link_evidence_api_passes_llm_overrides(monkeypatch):
    captured = {}

    def fake_scan_evidence_links_with_llm(**kwargs):
        captured.update(kwargs)
        return LLMLinkScanResult(
            highlights=[],
            metadata={"model": kwargs["model"], "api_calls": 1, "total_tokens": 0},
        )

    monkeypatch.setattr(
        "app.link_scanning.service.scan_evidence_links_with_llm",
        fake_scan_evidence_links_with_llm,
    )

    response = api_request(
        "POST",
        "/enrich-link-evidence",
        json=_request_payload(
            llm_model="request-link-model",
            llm_max_output_tokens=333,
            requested_highlight_count=8,
            max_tokens_per_highlight=90,
        ),
    )

    assert response.status_code == 200
    assert captured["model"] == "request-link-model"
    assert captured["max_output_tokens"] == 333
    assert captured["requested_highlight_count"] == 8
    assert captured["max_tokens_per_highlight"] == 90


def test_enrich_link_evidence_api_returns_502_when_llm_fails(monkeypatch):
    def fake_scan_evidence_links_with_llm(**_kwargs):
        raise LinkScanningLLMClientError("web scan failed")

    monkeypatch.setattr(
        "app.link_scanning.service.scan_evidence_links_with_llm",
        fake_scan_evidence_links_with_llm,
    )

    response = api_request("POST", "/enrich-link-evidence", json=_request_payload())

    assert response.status_code == 502
    assert "web scan failed" in response.text


def test_enrich_link_evidence_api_rejects_unknown_project_skill_category():
    project = _project_payload()
    project["skills"]["design"] = ["UX"]

    response = api_request(
        "POST",
        "/enrich-link-evidence",
        json=_request_payload(evidence=project),
    )

    assert response.status_code == 422
    assert "design" in response.text
