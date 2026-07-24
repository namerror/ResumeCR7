from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
import yaml

from app.config import settings
from app.main import app
from app.resume_evidence import (
    EducationFile,
    ExperienceFile,
    ProjectsFile,
    SkillsFile,
    UserInfoFile,
    load_evidence_yaml,
)


def api_request(method: str, path: str, **kwargs):
    async def _request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())


@pytest.fixture
def evidence_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "resume_evidence"
    root.mkdir()
    _write_yaml(root / "education.yaml", _education_payload())
    _write_yaml(root / "experience.yaml", _experience_payload())
    _write_yaml(root / "projects.yaml", _projects_payload())
    _write_yaml(root / "skills.yaml", _skills_payload())
    _write_yaml(root / "user.yaml", _user_payload())
    monkeypatch.setattr(settings, "RESUME_EVIDENCE_ROOT", root)
    return root


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _skill_buckets() -> dict:
    return {
        "technology": ["FastAPI"],
        "programming": ["Python"],
        "concepts": ["API"],
    }


def _projects_payload() -> dict:
    return {
        "schema_version": 1,
        "projects": [
            {
                "id": "resumecr7",
                "name": "ResumeCR7",
                "summary": "Grounded resume tooling.",
                "highlights": ["Built deterministic evidence workflows."],
                "active": True,
                "skills": _skill_buckets(),
                "links": ["https://github.com/example/resumecr7"],
            }
        ],
    }


def _experience_payload() -> dict:
    return {
        "schema_version": 1,
        "experience": [
            {
                "id": "backend-engineer",
                "name": "Example Company",
                "role": "Backend Engineer",
                "summary": "Built backend services.",
                "highlights": ["Designed schema-validated APIs."],
                "active": True,
                "skills": _skill_buckets(),
                "location": "Example City, ST",
                "start": "2024",
                "end": None,
                "links": ["https://example.com/company"],
            }
        ],
    }


def _education_payload() -> dict:
    return {
        "schema_version": 1,
        "education": [
            {
                "id": "example-university",
                "name": "Example University",
                "degree": "Bachelor of Science in Computer Science",
                "grade": "3.8 GPA",
                "start": "2020",
                "end": "2024",
                "location": "Example City, ST",
                "relevant_coursework": ["Data Structures", "Algorithms"],
            }
        ],
    }


def _skills_payload() -> dict:
    return {
        "schema_version": 1,
        "skills": {
            "technology": ["FastAPI"],
            "programming": ["Python"],
            "concepts": ["Schema validation"],
        },
    }


def _user_payload() -> dict:
    return {
        "schema_version": 1,
        "name": "Example Candidate",
        "email": "candidate@example.com",
        "phone": "+1 555-0100",
        "linkedin": "https://www.linkedin.com/in/example-candidate",
        "github": "https://github.com/example-candidate",
        "website": None,
    }


def _project_input(name: str = "Portfolio API") -> dict:
    return {
        "name": name,
        "summary": "FastAPI portfolio service.",
        "highlights": ["Built CRUD workflows for resume evidence."],
        "active": True,
        "skills": _skill_buckets(),
        "links": ["https://example.com/portfolio"],
    }


def _experience_input(name: str = "Platform Team") -> dict:
    return {
        "name": name,
        "role": "Platform Engineer",
        "summary": "Built platform tooling.",
        "highlights": ["Shipped internal backend tools."],
        "active": True,
        "skills": _skill_buckets(),
        "location": "Remote",
        "start": "2025",
        "end": None,
        "links": None,
    }


def _education_input(name: str = "Example College") -> dict:
    return {
        "name": name,
        "degree": "Master of Science in Software Engineering",
        "grade": "4.0 GPA",
        "start": "2025",
        "end": None,
        "location": "Remote",
        "relevant_coursework": ["Distributed Systems"],
    }


def test_resume_evidence_api_lists_all_registered_evidence(evidence_root):
    response = api_request("GET", "/resume-evidence")

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"education", "experience", "projects", "skills", "user"}
    assert data["projects"]["projects"][0]["id"] == "resumecr7"
    assert data["education"]["education"][0]["id"] == "example-university"
    assert isinstance(app.state.resume_evidence["projects"], ProjectsFile)


def test_resume_evidence_api_reads_singletons(evidence_root):
    user_response = api_request("GET", "/resume-evidence/user")
    skills_response = api_request("GET", "/resume-evidence/skills")

    assert user_response.status_code == 200
    assert skills_response.status_code == 200
    assert user_response.json()["email"] == "candidate@example.com"
    assert skills_response.json()["skills"]["technology"] == ["FastAPI"]


def test_resume_evidence_api_updates_singletons_and_persists_yaml(evidence_root):
    skills_response = api_request(
        "PUT",
        "/resume-evidence/skills",
        json={
            "skills": {
                "technology": ["FastAPI", "Docker"],
                "programming": ["Python", "SQL"],
                "concepts": ["REST API"],
            }
        },
    )
    user_response = api_request(
        "PUT",
        "/resume-evidence/user",
        json={
            "name": "Example Candidate",
            "email": "updated@example.com",
            "phone": "+1 555-9999",
            "linkedin": None,
            "github": "https://github.com/example-candidate",
            "website": "https://example.com",
        },
    )

    assert skills_response.status_code == 200
    assert user_response.status_code == 200
    skills = load_evidence_yaml(evidence_root / "skills.yaml", "skills")
    user = load_evidence_yaml(evidence_root / "user.yaml", "user")
    assert isinstance(skills, SkillsFile)
    assert isinstance(user, UserInfoFile)
    assert skills.skills.technology == ["FastAPI", "Docker"]
    assert user.email == "updated@example.com"
    assert app.state.resume_evidence["skills"].skills.concepts == ["REST API"]


def test_resume_evidence_api_cruds_projects_by_id_and_persists_yaml(evidence_root):
    created = api_request("POST", "/resume-evidence/projects", json=_project_input())

    assert created.status_code == 201
    assert created.json()["id"] == "portfolio-api"

    fetched = api_request("GET", "/resume-evidence/projects/portfolio-api")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Portfolio API"

    update_payload = _project_input()
    update_payload["summary"] = "Updated FastAPI portfolio service."
    updated = api_request(
        "PUT",
        "/resume-evidence/projects/portfolio-api",
        json=update_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == "portfolio-api"
    assert updated.json()["summary"] == "Updated FastAPI portfolio service."

    deleted = api_request("DELETE", "/resume-evidence/projects/portfolio-api")
    assert deleted.status_code == 200
    assert deleted.json()["id"] == "portfolio-api"
    assert api_request("GET", "/resume-evidence/projects/portfolio-api").status_code == 404

    projects = load_evidence_yaml(evidence_root / "projects.yaml", "projects")
    assert isinstance(projects, ProjectsFile)
    assert [project.id for project in projects.projects] == ["resumecr7"]


def test_resume_evidence_api_generates_unique_project_ids(evidence_root):
    first = api_request("POST", "/resume-evidence/projects", json=_project_input("Duplicate"))
    second = api_request("POST", "/resume-evidence/projects", json=_project_input("Duplicate"))

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == "duplicate"
    assert second.json()["id"] == "duplicate-2"


def test_resume_evidence_api_cruds_experience_by_id_and_persists_yaml(evidence_root):
    created = api_request("POST", "/resume-evidence/experience", json=_experience_input())

    assert created.status_code == 201
    assert created.json()["id"] == "platform-team"

    fetched = api_request("GET", "/resume-evidence/experience/platform-team")
    assert fetched.status_code == 200
    assert fetched.json()["role"] == "Platform Engineer"

    update_payload = _experience_input()
    update_payload["role"] = "Senior Platform Engineer"
    updated = api_request(
        "PUT",
        "/resume-evidence/experience/platform-team",
        json=update_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == "platform-team"
    assert updated.json()["role"] == "Senior Platform Engineer"

    deleted = api_request("DELETE", "/resume-evidence/experience/platform-team")
    assert deleted.status_code == 200
    assert api_request("GET", "/resume-evidence/experience/platform-team").status_code == 404

    experience = load_evidence_yaml(evidence_root / "experience.yaml", "experience")
    assert isinstance(experience, ExperienceFile)
    assert [item.id for item in experience.experience] == ["backend-engineer"]


def test_resume_evidence_api_cruds_education_by_id_and_persists_yaml(evidence_root):
    created = api_request("POST", "/resume-evidence/education", json=_education_input())

    assert created.status_code == 201
    assert created.json()["id"] == "example-college"

    fetched = api_request("GET", "/resume-evidence/education/example-college")
    assert fetched.status_code == 200
    assert fetched.json()["degree"] == "Master of Science in Software Engineering"

    update_payload = _education_input()
    update_payload["grade"] = "3.9 GPA"
    updated = api_request(
        "PUT",
        "/resume-evidence/education/example-college",
        json=update_payload,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == "example-college"
    assert updated.json()["grade"] == "3.9 GPA"

    deleted = api_request("DELETE", "/resume-evidence/education/example-college")
    assert deleted.status_code == 200
    assert api_request("GET", "/resume-evidence/education/example-college").status_code == 404

    education = load_evidence_yaml(evidence_root / "education.yaml", "education")
    assert isinstance(education, EducationFile)
    assert [item.id for item in education.education] == ["example-university"]


@pytest.mark.parametrize(
    ("path", "missing_id"),
    [
        ("/resume-evidence/projects/missing", "project 'missing' was not found"),
        ("/resume-evidence/experience/missing", "experience 'missing' was not found"),
        ("/resume-evidence/education/missing", "education 'missing' was not found"),
    ],
)
def test_resume_evidence_api_returns_404_for_missing_ids(evidence_root, path, missing_id):
    response = api_request("GET", path)

    assert response.status_code == 404
    assert missing_id in response.json()["detail"]


def test_resume_evidence_api_rejects_invalid_mutation_payloads(evidence_root):
    missing_required = _project_input()
    del missing_required["summary"]
    with_extra_id = _project_input()
    with_extra_id["id"] = "client-owned"

    missing_response = api_request("POST", "/resume-evidence/projects", json=missing_required)
    extra_response = api_request("POST", "/resume-evidence/projects", json=with_extra_id)

    assert missing_response.status_code == 422
    assert extra_response.status_code == 422
